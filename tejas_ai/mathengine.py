"""Exact maths for Tejas, powered by SymPy.

Small language models are bad at arithmetic. Tejas never trusts its own
mental maths: every number it gives comes from this engine.

Input is untrusted (it comes from a child or from the model), so it is
cleaned, checked against an allow-list of names, and evaluated in a separate
worker process with a time limit that can be killed if SymPy gets stuck.
"""
from __future__ import annotations

import concurrent.futures as cf
import multiprocessing as mp
import re
import threading

FUNCS = {
    "sin", "cos", "tan", "cot", "sec", "csc", "asin", "acos", "atan", "sinh", "cosh", "tanh",
    "exp", "log", "ln", "sqrt", "cbrt", "root", "Abs", "abs", "factorial", "binomial", "gcd", "lcm",
    "floor", "ceiling", "round", "pi", "E", "I", "oo", "mod", "Mod", "isprime", "factorint", "prime",
    "degree",
}
GREEK = {"alpha", "beta", "gamma", "theta", "phi", "lam", "mu", "sigma", "omega", "delta"}
ALLOWED_CHARS = re.compile(r"^[0-9a-zA-Z_+\-*/().,=<>\s!%]*$")
IDENT = re.compile(r"[A-Za-z_][A-Za-z_0-9]*")
OPS = ("auto", "evaluate", "solve", "simplify", "factor", "expand", "derivative", "integral", "limit", "primes")


class MathError(ValueError):
    pass


def clean(expr: str) -> str:
    s = str(expr or "").strip()
    if len(s) > 400:
        raise MathError("That problem is too long for me. Try a shorter one.")
    repl = {
        "×": "*", "·": "*", "÷": "/", "−": "-", "–": "-", "²": "**2", "³": "**3",
        "√": "sqrt", "π": "pi", "≤": "<=", "≥": ">=", "^": "**", "∞": "oo",
    }
    for a, b in repl.items():
        s = s.replace(a, b)
    s = re.sub(r"(?<=\d),(?=\d{3}\b)", "", s)            # 1,000 -> 1000
    s = re.sub(r"(\d+(?:\.\d+)?)\s*%\s*of\s*", r"(\1/100)*", s, flags=re.I)  # 15% of 80
    s = re.sub(r"(\d+(?:\.\d+)?)\s*%", r"(\1/100)", s)    # 15% -> (15/100)
    s = re.sub(r"\bx(?=\s*\d)", "*", s) if re.fullmatch(r"[\d\s.x+\-*/()]+", s) else s  # 3 x 4
    s = s.replace("**", "^^").replace("^^", "**")
    if not ALLOWED_CHARS.match(s):
        raise MathError("I can only read numbers, letters and + - * / ^ ( ) = in a maths problem.")
    if "__" in s:
        raise MathError("That doesn't look like maths.")
    for name in IDENT.findall(s):
        if name in FUNCS or name in GREEK:
            continue
        if re.fullmatch(r"[a-zA-Z][0-9]?", name):
            continue
        if re.fullmatch(r"[a-zA-Z]{2,3}", name) and name.islower():
            continue  # implicit products like "xy" or "abc"
        raise MathError(f"I don't know the word '{name}' in maths.")
    return s


def _split_top(s: str, seps=",;") -> list[str]:
    parts, depth, cur = [], 0, ""
    for ch in s:
        if ch in "([":
            depth += 1
        elif ch in ")]":
            depth -= 1
        if ch in seps and depth == 0:
            parts.append(cur)
            cur = ""
        else:
            cur += ch
    parts.append(cur)
    return [p.strip() for p in parts if p.strip()]


# Runs inside the worker process ---------------------------------------
def _work(op: str, expr: str, var: str | None, lower, upper, point) -> dict:
    import sympy as sp
    from sympy.parsing.sympy_parser import (
        convert_xor, factorial_notation, implicit_multiplication_application,
        parse_expr, standard_transformations,
    )

    tx = standard_transformations + (implicit_multiplication_application, convert_xor, factorial_notation)
    local = {"ln": sp.log, "abs": sp.Abs, "mod": sp.Mod, "lam": sp.Symbol("lam"), "e": sp.E,
             "round": lambda x, n=0: sp.Float(round(float(x), int(n))) if n else sp.Integer(round(float(x))),
             "degree": sp.pi / 180, "cbrt": sp.cbrt}

    def P(t: str):
        return parse_expr(t, local_dict=dict(local), transformations=tx, evaluate=True)

    def fmt(v) -> str:
        if isinstance(v, (list, tuple, set)):
            return ", ".join(fmt(x) for x in v) if v else "no solution"
        return str(v).replace("**", "^").replace("sqrt", "√")

    def dec(v):
        try:
            if getattr(v, "is_number", False) and not v.is_Integer:
                f = sp.N(v, 12)
                if f.is_real:
                    return str(sp.Float(f, 10)).rstrip("0").rstrip(".")
        except Exception:
            pass
        return None

    rel = re.compile(r"(<=|>=|<|>|=)")
    pieces = _split_top(expr)
    has_rel = any(rel.search(p) for p in pieces)
    if op == "auto":
        op = "solve" if has_rel else "evaluate"

    def rel_of(p: str):
        m = re.split(r"(<=|>=|==|<|>|=)", p, maxsplit=1)
        if len(m) == 1:
            return sp.Eq(P(p), 0)
        a, o, b = m
        A, B = P(a), P(b)
        return {"=": sp.Eq, "==": sp.Eq, "<": sp.Lt, ">": sp.Gt, "<=": sp.Le, ">=": sp.Ge}[o](A, B)

    if op == "solve":
        rels = [rel_of(p) for p in pieces]
        syms = sorted(set().union(*[r.free_symbols for r in rels]), key=str)
        if var:
            syms = [sp.Symbol(v.strip()) for v in var.split(",")]
        if not syms:
            truth = all(bool(r) for r in rels)
            return {"ok": True, "op": "check", "result": "true" if truth else "false"}
        if any(not isinstance(r, sp.Equality) for r in rels):
            if len(syms) != 1 or len(rels) != 1:
                raise MathError("I can solve one inequality with one letter at a time.")
            s0 = syms[0]
            sol = sp.solve_univariate_inequality(rels[0], s0, relational=False)

            def iv(i) -> str:
                if isinstance(i, sp.Union):
                    return " or ".join(iv(a) for a in i.args)
                if i == sp.S.Reals:
                    return f"any value of {s0}"
                if i == sp.S.EmptySet:
                    return "no solution"
                if isinstance(i, sp.FiniteSet):
                    return " or ".join(f"{s0} = {fmt(a)}" for a in i)
                a, b = i.start, i.end
                lo = f"{fmt(a)} {'<' if i.left_open else '≤'} " if a != -sp.oo else ""
                hi = f" {'<' if i.right_open else '≤'} {fmt(b)}" if b != sp.oo else ""
                if lo and not hi:
                    return f"{s0} {'>' if i.left_open else '≥'} {fmt(a)}"
                return f"{lo}{s0}{hi}"

            return {"ok": True, "op": "solve", "result": iv(sol)}
        sol = sp.solve(rels, syms, dict=True)
        if not sol:
            return {"ok": True, "op": "solve", "result": "no solution"}
        out = []
        for s in sol:
            parts = []
            for k, v in s.items():
                d = dec(v)
                parts.append(f"{k} = {fmt(v)}" + (f" (≈ {d})" if d else ""))
            out.append(", ".join(parts))
        return {"ok": True, "op": "solve", "result": " or ".join(out)}

    e = P(pieces[0])
    syms = sorted(e.free_symbols, key=str)
    x = sp.Symbol(var) if var else (syms[0] if syms else sp.Symbol("x"))
    if op == "evaluate":
        v = sp.nsimplify(e) if e.is_number and e.is_Float else sp.simplify(e)
        return {"ok": True, "op": op, "result": fmt(v), "decimal": dec(v)}
    if op == "simplify":
        return {"ok": True, "op": op, "result": fmt(sp.simplify(e))}
    if op == "factor":
        if e.is_Integer:
            return {"ok": True, "op": op, "result": " × ".join(f"{p}^{k}" if k > 1 else str(p) for p, k in sp.factorint(e).items())}
        return {"ok": True, "op": op, "result": fmt(sp.factor(e))}
    if op == "expand":
        return {"ok": True, "op": op, "result": fmt(sp.expand(e))}
    if op == "derivative":
        return {"ok": True, "op": op, "result": fmt(sp.simplify(sp.diff(e, x)))}
    if op == "integral":
        if lower is not None and upper is not None:
            v = sp.integrate(e, (x, P(str(lower)), P(str(upper))))
            return {"ok": True, "op": op, "result": fmt(v), "decimal": dec(v)}
        return {"ok": True, "op": op, "result": fmt(sp.integrate(e, x)) + " + C"}
    if op == "limit":
        v = sp.limit(e, x, P(str(point if point is not None else 0)))
        return {"ok": True, "op": op, "result": fmt(v), "decimal": dec(v)}
    if op == "primes":
        n = int(e)
        return {"ok": True, "op": op, "result": "prime" if sp.isprime(n) else "not prime, factors: "
                + " × ".join(f"{p}^{k}" if k > 1 else str(p) for p, k in sp.factorint(n).items())}
    raise MathError(f"Unknown operation {op}")


def _safe_work(*a) -> dict:
    try:
        return _work(*a)
    except MathError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:  # SymPy raises many kinds of errors on bad input
        return {"ok": False, "error": f"I couldn't work that out ({type(e).__name__})."}


class MathEngine:
    """Keeps one warm worker process; kills and replaces it on a timeout."""

    def __init__(self, timeout: float = 12.0):
        self.timeout = timeout
        self._lock = threading.Lock()
        self._pool: cf.ProcessPoolExecutor | None = None

    def _get_pool(self) -> cf.ProcessPoolExecutor:
        if self._pool is None:
            # 'spawn' is safe in a multi-threaded server and works the same on Windows.
            self._pool = cf.ProcessPoolExecutor(max_workers=1, mp_context=mp.get_context("spawn"))
        return self._pool

    def _reset(self) -> None:
        pool, self._pool = self._pool, None
        if pool is not None:
            for p in list(getattr(pool, "_processes", {}).values()):
                p.terminate()
            pool.shutdown(wait=False, cancel_futures=True)

    def run(self, expression: str, op: str = "auto", variable: str | None = None,
            lower=None, upper=None, point=None) -> dict:
        op = (op or "auto").lower().strip()
        if op not in OPS:
            op = "auto"
        try:
            expr = clean(expression)
            if variable:
                variable = ",".join(v for v in re.findall(r"[a-zA-Z]", variable))[:20] or None
        except MathError as e:
            return {"ok": False, "error": str(e)}
        with self._lock:
            try:
                fut = self._get_pool().submit(_safe_work, op, expr, variable, lower, upper, point)
                res = fut.result(timeout=self.timeout)
            except cf.TimeoutError:
                self._reset()
                return {"ok": False, "error": "That one is taking too long even for my maths engine."}
            except Exception as e:  # broken pool etc.
                self._reset()
                return {"ok": False, "error": f"Maths engine restarted ({type(e).__name__}). Try again."}
        res["input"] = expression
        return res

    def warm_up(self) -> None:
        """Start the worker and load SymPy before the first question."""
        self.run("1+1")

    def close(self) -> None:
        self._reset()
