import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class FakeLLM:
    """Scripted stand-in for the local model. Each script entry is either a
    string (the model replies with text) or a list of tool calls."""

    backend = "ollama"
    model = "fake"

    def __init__(self, script=None, tools_supported=True):
        self.script = list(script or [])
        self.calls = []
        self.tools_supported = tools_supported

    async def status(self):
        return {"ok": True, "backend": "fake", "model": "fake", "models": ["fake"]}

    def assistant_msg(self, content, calls):
        return {"role": "assistant", "content": content,
                "tool_calls": [{"function": {"name": c["name"], "arguments": c["arguments"]}} for c in calls]}

    def tool_msg(self, call, result):
        import json
        return {"role": "tool", "content": json.dumps(result), "tool_name": call["name"]}

    async def stream(self, messages, tools=None, temperature=None):
        from tejas_ai.llm import ToolsUnsupported
        self.calls.append({"messages": [dict(m) for m in messages], "tools": tools})
        if tools and not self.tools_supported:
            raise ToolsUnsupported("does not support tools")
        step = self.script.pop(0) if self.script else "Okay!"
        if isinstance(step, list):
            yield "tool_calls", [{"id": f"c{i}", "name": n, "arguments": a} for i, (n, a) in enumerate(step)]
        else:
            for w in step.split(" "):
                yield "text", w + " "


@pytest.fixture
def fake_llm():
    return FakeLLM


@pytest.fixture
def app_factory(tmp_path, monkeypatch):
    monkeypatch.setenv("TEJAS_OFFLINE", "1")
    from tejas_ai.server import create_app

    def make(script=None, **kw):
        llm = FakeLLM(script, **kw)
        return create_app(tmp_path, llm=llm), llm
    return make
