import asyncio
import datetime as dt
import json

import httpx
import pytest

from tejas_ai.config import Config
from tejas_ai.library import Library
from tejas_ai.llm import LLM, LLMOffline, ToolsUnsupported
from tejas_ai.mathengine import MathEngine
from tejas_ai.memory import Memory
from tejas_ai.news import parse_feed
from tejas_ai.tools import convert_units, parse_when
from tejas_ai.brain import ThinkFilter, looks_like_math


def run(coro):
    return asyncio.run(coro)


def llm_with(handler, tmp_path, backend="ollama"):
    cfg = Config(tmp_path / "c.json")
    cfg.update({"llm": {"backend": backend, "model": "m"}})
    llm = LLM(cfg)
    llm._client = lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return llm


async def collect(agen):
    return [e async for e in agen]


def test_ollama_stream_with_tool_calls(tmp_path):
    lines = [
        {"message": {"content": "Let me "}}, {"message": {"content": "check."}},
        {"message": {"content": "", "tool_calls": [{"function": {"name": "math", "arguments": {"expression": "2+2"}}}]}},
        {"done": True},
    ]

    def h(req):
        body = json.loads(req.content)
        assert body["tools"] and body["model"] == "m"
        return httpx.Response(200, text="\n".join(json.dumps(l) for l in lines))
    evs = run(collect(llm_with(h, tmp_path).stream([{"role": "user", "content": "hi"}], [{"x": 1}])))
    assert evs[0] == ("text", "Let me ") and evs[-1][0] == "tool_calls"
    assert evs[-1][1][0]["name"] == "math" and evs[-1][1][0]["arguments"] == {"expression": "2+2"}


def test_ollama_tools_unsupported(tmp_path):
    h = lambda req: httpx.Response(400, json={"error": "registry.ollama.ai/library/m does not support tools"})
    with pytest.raises(ToolsUnsupported):
        run(collect(llm_with(h, tmp_path).stream([], [{"x": 1}])))


def test_ollama_offline(tmp_path):
    def h(req):
        raise httpx.ConnectError("refused")
    with pytest.raises(LLMOffline):
        run(collect(llm_with(h, tmp_path).stream([], None)))


def test_openai_stream_assembles_tool_call_pieces(tmp_path):
    chunks = [
        {"choices": [{"delta": {"content": "Hi"}}]},
        {"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "c1", "function": {"name": "add_", "arguments": '{"text": "wa'}}]}}]},
        {"choices": [{"delta": {"tool_calls": [{"index": 0, "function": {"name": "reminder", "arguments": 'ter", "when": "7 pm"}'}}]}}]},
    ]
    text = "".join(f"data: {json.dumps(c)}\n\n" for c in chunks) + "data: [DONE]\n\n"
    evs = run(collect(llm_with(lambda r: httpx.Response(200, text=text), tmp_path, "openai").stream([], [{"x": 1}])))
    assert evs[0] == ("text", "Hi")
    call = evs[-1][1][0]
    assert call["name"] == "add_reminder" and call["arguments"] == {"text": "water", "when": "7 pm"}


def test_think_filter_across_chunks():
    f = ThinkFilter()
    out = "".join(f.feed(c) for c in ["Hel", "lo <thi", "nk>hidden</th", "ink> world"]) + f.flush()
    assert out == "Hello  world"


def test_math_detection():
    assert looks_like_math("what is 245 times 37?") == "245 * 37"
    assert looks_like_math("solve 2x + 3 = 11") == "2x + 3 = 11"
    assert looks_like_math("tell me a story about 3 bears") is None
    assert looks_like_math("hello") is None


def test_math_engine_is_safe_and_right():
    m = MathEngine()
    try:
        assert m.run("x^2-5x+6=0")["result"] == "x = 2 or x = 3"
        assert m.run("1/3+1/6")["result"] == "1/2"
        assert m.run("2x-1>5")["result"] == "x > 3"
        assert not m.run("__import__('os').system('ls')")["ok"]
        assert not m.run("eval(1)")["ok"]
    finally:
        m.close()


def test_time_words():
    now = dt.datetime(2026, 10, 19, 21, 55)
    assert parse_when("in 10 minutes", now) == dt.datetime(2026, 10, 19, 22, 5)
    assert parse_when("tomorrow at 7:30 am", now) == dt.datetime(2026, 10, 20, 7, 30)
    assert parse_when("7 pm", now) == dt.datetime(2026, 10, 20, 19, 0)
    assert parse_when("friday 6pm", now) == dt.datetime(2026, 10, 23, 18, 0)
    assert parse_when("banana", now) is None


def test_units():
    assert convert_units(100, "c", "f")["result"] == "100 c = 212 f"
    assert not convert_units(3, "kg", "m")["ok"]


def test_memory_reminders_repeat(tmp_path):
    m = Memory(tmp_path / "t.db")
    p = m.add_profile(name="Ria", age=7)
    m.add_reminder(p["id"], "Brush teeth", 1000, "daily")
    due = m.pop_due(now=1000 + 5)
    assert due[0]["text"] == "Brush teeth"
    assert m.reminders()[0]["due"] == 1000 + 86400  # moved to tomorrow
    assert m.remember(p["id"], "Loves dinosaurs") and not m.remember(p["id"], "loves dinosaurs")


def test_library_search(tmp_path):
    (tmp_path / "science.md").write_text("Plants make food by photosynthesis using sunlight.\n\nThe heart pumps blood.")
    lib = Library(tmp_path)
    hits = lib.search("how do plants make food")
    assert hits and "photosynthesis" in hits[0]["text"]


def test_news_parse_rss_and_atom():
    rss = b"<rss><channel><item><title>Big &amp; small</title><description>&lt;p&gt;Hello&lt;/p&gt;</description></item></channel></rss>"
    assert parse_feed(rss) == [{"title": "Big & small", "summary": "Hello"}]
    atom = b'<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>A</title><summary>B</summary></entry></feed>'
    assert parse_feed(atom) == [{"title": "A", "summary": "B"}]


def test_online_key_hidden_and_live_reload(tmp_path):
    import json, time
    from tejas_ai.config import Config
    a = Config(tmp_path / "config.json")
    b = Config(tmp_path / "config.json")
    b.update({"llm": {"backend": "openai", "api_key": "gsk_secret"}})
    time.sleep(0.01)
    a._checked = 0.0
    assert a.get("llm.api_key") == "gsk_secret"          # picks up the desktop window's change
    assert a.public()["llm"]["api_key"] == "set"          # never sent to screens
    assert "gsk_secret" not in json.dumps(a.public())


def test_home_only_blocks_other_websites(app_factory):
    from fastapi.testclient import TestClient
    app, _ = app_factory()
    with TestClient(app) as client:
        _check_home_only(client)


def _check_home_only(client):
    # Rebinding: a strange website name pointed at this computer
    assert client.get("/api/status", headers={"host": "evil.example.com"}).status_code == 403
    # LAN IP and localhost are fine
    assert client.get("/api/status", headers={"host": "192.168.1.20:8443"}).status_code == 200
    # CSRF: another website posting into Tejas
    r = client.post("/api/reminders", json={"text": "x", "when": "in 5 minutes"},
                    headers={"origin": "https://evil.example.com"})
    assert r.status_code == 403
    # Tejas's own screen posting is fine
    r = client.post("/api/reminders", json={"text": "x", "when": "in 5 minutes"},
                    headers={"origin": "http://testserver"})
    assert r.status_code == 200
    assert client.get("/api/status").headers["x-frame-options"] == "DENY"
