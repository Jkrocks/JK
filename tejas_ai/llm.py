"""Talks to the local language model. Nothing here ever leaves the house:
the model runs on this computer through Ollama (default) or any
OpenAI-compatible local server (llama.cpp's llama-server, LM Studio, vLLM).
"""
from __future__ import annotations

import json
import uuid
from typing import AsyncIterator

import httpx


class LLMOffline(RuntimeError):
    """The model server isn't running or can't be reached."""


class ToolsUnsupported(RuntimeError):
    """The chosen model can't call tools; we retry without them."""


class LLM:
    def __init__(self, cfg):
        self.cfg = cfg

    @property
    def backend(self) -> str:
        return self.cfg.get("llm.backend", "ollama")

    @property
    def url(self) -> str:
        return self.cfg.get("llm.url", "http://127.0.0.1:11434").rstrip("/")

    @property
    def model(self) -> str:
        return self.cfg.get("llm.model")

    def _client(self) -> httpx.AsyncClient:
        t = float(self.cfg.get("llm.timeout_s", 300))
        return httpx.AsyncClient(timeout=httpx.Timeout(t, connect=5.0))

    async def status(self) -> dict:
        try:
            async with httpx.AsyncClient(timeout=3.0) as c:
                if self.backend == "ollama":
                    r = await c.get(f"{self.url}/api/tags")
                    r.raise_for_status()
                    names = [m["name"] for m in r.json().get("models", [])]
                else:
                    r = await c.get(f"{self.url}/v1/models")
                    r.raise_for_status()
                    names = [m["id"] for m in r.json().get("data", [])]
        except Exception as e:
            return {"ok": False, "backend": self.backend, "error": f"model server not reachable ({type(e).__name__})"}
        have = self.model in names or f"{self.model}:latest" in names or self.backend != "ollama"
        return {"ok": have, "backend": self.backend, "model": self.model, "models": names,
                **({} if have else {"error": f"model '{self.model}' is not downloaded yet"})}

    # Message helpers (each backend wants tool turns shaped differently) --
    def assistant_msg(self, content: str, calls: list[dict]) -> dict:
        if self.backend == "ollama":
            return {"role": "assistant", "content": content,
                    "tool_calls": [{"function": {"name": c["name"], "arguments": c["arguments"]}} for c in calls]}
        return {"role": "assistant", "content": content or None,
                "tool_calls": [{"id": c["id"], "type": "function",
                                "function": {"name": c["name"], "arguments": json.dumps(c["arguments"])}} for c in calls]}

    def tool_msg(self, call: dict, result) -> dict:
        content = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False)
        if self.backend == "ollama":
            return {"role": "tool", "content": content, "tool_name": call["name"]}
        return {"role": "tool", "tool_call_id": call["id"], "content": content}

    # Streaming -----------------------------------------------------------
    async def stream(self, messages: list[dict], tools: list[dict] | None = None,
                     temperature: float | None = None) -> AsyncIterator[tuple[str, object]]:
        """Yields ("text", chunk) as words arrive, then ("tool_calls", [...])
        once at the end if the model wants to use tools."""
        temp = self.cfg.get("llm.temperature", 0.6) if temperature is None else temperature
        try:
            if self.backend == "ollama":
                async for ev in self._ollama(messages, tools, temp):
                    yield ev
            else:
                async for ev in self._openai(messages, tools, temp):
                    yield ev
        except (httpx.ConnectError, httpx.ConnectTimeout) as e:
            raise LLMOffline("The thinking engine isn't running on this computer. Start Ollama and try again.") from e

    async def _ollama(self, messages, tools, temp):
        body = {"model": self.model, "messages": messages, "stream": True,
                "options": {"temperature": temp, "num_ctx": int(self.cfg.get("llm.num_ctx", 8192))},
                "keep_alive": "30m"}
        if tools:
            body["tools"] = tools
        calls: list[dict] = []
        async with self._client() as c:
            async with c.stream("POST", f"{self.url}/api/chat", json=body) as r:
                if r.status_code >= 400:
                    err = (await r.aread()).decode("utf-8", "ignore")
                    if tools and "tool" in err.lower():
                        raise ToolsUnsupported(err)
                    if r.status_code == 404:
                        raise LLMOffline(f"The model '{self.model}' isn't downloaded. Run: ollama pull {self.model}")
                    raise RuntimeError(f"model error {r.status_code}: {err[:200]}")
                async for line in r.aiter_lines():
                    if not line.strip():
                        continue
                    try:
                        d = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if d.get("error"):
                        raise RuntimeError(d["error"])
                    msg = d.get("message") or {}
                    if msg.get("content"):
                        yield "text", msg["content"]
                    for tc in msg.get("tool_calls") or []:
                        f = tc.get("function", {})
                        args = f.get("arguments") or {}
                        if isinstance(args, str):
                            try:
                                args = json.loads(args)
                            except json.JSONDecodeError:
                                args = {}
                        calls.append({"id": uuid.uuid4().hex[:12], "name": f.get("name", ""), "arguments": args})
        if calls:
            yield "tool_calls", calls

    async def _openai(self, messages, tools, temp):
        body = {"model": self.model, "messages": messages, "stream": True, "temperature": temp}
        if tools:
            body["tools"] = tools
        parts: dict[int, dict] = {}
        async with self._client() as c:
            async with c.stream("POST", f"{self.url}/v1/chat/completions", json=body) as r:
                if r.status_code >= 400:
                    err = (await r.aread()).decode("utf-8", "ignore")
                    if tools and "tool" in err.lower():
                        raise ToolsUnsupported(err)
                    raise RuntimeError(f"model error {r.status_code}: {err[:200]}")
                async for line in r.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        d = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    for ch in d.get("choices", []):
                        delta = ch.get("delta") or {}
                        if delta.get("content"):
                            yield "text", delta["content"]
                        for tc in delta.get("tool_calls") or []:
                            p = parts.setdefault(tc.get("index", 0), {"id": "", "name": "", "args": ""})
                            p["id"] = tc.get("id") or p["id"]
                            f = tc.get("function") or {}
                            p["name"] += f.get("name") or ""
                            p["args"] += f.get("arguments") or ""
        if parts:
            calls = []
            for i in sorted(parts):
                p = parts[i]
                try:
                    args = json.loads(p["args"] or "{}")
                except json.JSONDecodeError:
                    args = {}
                calls.append({"id": p["id"] or uuid.uuid4().hex[:12], "name": p["name"], "arguments": args})
            yield "tool_calls", calls
