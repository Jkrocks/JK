import json

from fastapi.testclient import TestClient


def chat(client, text, pid=None, deep=None):
    r = client.post("/api/chat", json={"text": text, "profile_id": pid, "deep": deep})
    assert r.status_code == 200
    return [json.loads(line) for line in r.text.splitlines() if line.strip()]


def make_kid(client, **kw):
    body = {"name": "Aarav", "age": 9, "grade": "Class 4", "language": "en", "interests": "cricket, space"}
    body.update(kw)
    r = client.post("/api/profiles", json=body)
    assert r.status_code == 200, r.text
    return r.json()["id"]


def test_tool_round_trip_and_memory(app_factory):
    app, llm = app_factory([
        [("math", {"expression": "245*37"}), ("remember", {"fact": "Loves cricket stats"})],
        "245 times 37 is 9065. Great question!",
    ])
    with TestClient(app) as c:
        pid = make_kid(c)
        evs = chat(c, "Can you help me multiply 245 by 37 for my cricket score sheet?", pid)
        tools = [e for e in evs if e["type"] == "tool"]
        assert any(t["name"] == "math" and t["result"] == "9065" for t in tools)
        done = evs[-1]
        assert done["type"] == "done" and "9065" in done["text"]
        assert c.get(f"/api/facts/{pid}").json()[0]["text"] == "Loves cricket stats"
        # Second turn sees the remembered fact and history in the prompt.
        chat(c, "thanks", pid)
        sysmsg = llm.calls[-1]["messages"][0]["content"]
        assert "Loves cricket stats" in sysmsg and "Aarav" in sysmsg and "9 years old" in sysmsg
        hist = c.get(f"/api/history/{pid}").json()
        assert [h["role"] for h in hist] == ["user", "assistant", "user", "assistant"]


def test_math_prerouter_gives_exact_answer_without_tools(app_factory):
    app, llm = app_factory(["The answer is x = 4."], tools_supported=False)
    with TestClient(app) as c:
        evs = chat(c, "solve 2x + 3 = 11")
        assert any(e["type"] == "tool" and e["result"] == "x = 4" for e in evs)
        notes = [m["content"] for m in llm.calls[-1]["messages"] if m["role"] == "system"]
        assert any("MATHS ENGINE" in n and "x = 4" in n for n in notes)
        assert llm.calls[-1]["tools"] is None  # fell back after "does not support tools"


def test_self_harm_never_reaches_model(app_factory):
    app, llm = app_factory(["should not be used"])
    with TestClient(app) as c:
        pid = make_kid(c)
        evs = chat(c, "I want to die", pid)
        assert evs[-1]["flagged"] == "wellbeing"
        assert "14416" in evs[-1]["text"]
        assert llm.calls == []
        hist = c.get(f"/api/history/{pid}").json()
        assert hist[0]["flagged"] == "wellbeing"


def test_reminder_and_timer_actions(app_factory):
    app, llm = app_factory([
        [("add_reminder", {"text": "drink water", "when": "in 20 minutes"}),
         ("set_timer", {"minutes": 2, "label": "Brush teeth"})],
        "Done! I'll remind you to drink water in 20 minutes, and your 2 minute brushing timer has started.",
    ])
    with TestClient(app) as c:
        evs = chat(c, "remind me to drink water in 20 minutes and start a brushing timer")
        acts = [e for e in evs if e["type"] == "action"]
        assert {"action": "timer", "seconds": 120, "label": "Brush teeth", "type": "action"} in acts
        rs = c.get("/api/reminders").json()
        assert rs[0]["text"] == "drink water"


def test_deep_mode_checks_its_work(app_factory):
    app, llm = app_factory(["Draft: maybe 12.", [("math", {"expression": "3*4"})], "It's 12."])
    with TestClient(app) as c:
        evs = chat(c, "A hard puzzle about three boxes of four", deep=True)
        stages = [e["stage"] for e in evs if e["type"] == "stage"]
        assert stages == ["thinking", "checking"]
        assert evs[-1]["text"] == "It's 12."
        assert "check your answer" in llm.calls[1]["messages"][-1]["content"]


def test_think_tags_hidden(app_factory):
    app, llm = app_factory(["<think> secret plan </think> Hello there"])
    with TestClient(app) as c:
        evs = chat(c, "hi")
        spoken = "".join(e["text"] for e in evs if e["type"] == "token")
        assert "secret" not in spoken and "Hello there" in spoken


def test_repeat_tool_call_guard(app_factory):
    same = [("math", {"expression": "1+1"})]
    app, llm = app_factory([same, same, "Two."])
    with TestClient(app) as c:
        evs = chat(c, "what's one and one")
        tools = [e for e in evs if e["type"] == "tool"]
        assert tools[1]["ok"] is False
        assert evs[-1]["text"] == "Two."


def test_parent_pin_protects_history(app_factory):
    app, _ = app_factory()
    with TestClient(app) as c:
        pid = make_kid(c)
        assert c.post("/api/parent/pin", json={"pin": "2468"}).status_code == 200
        assert c.get(f"/api/history/{pid}").status_code == 401
        assert c.get(f"/api/history/{pid}", headers={"X-Parent-Pin": "2468"}).status_code == 200
        assert c.post("/api/profiles", json={"name": "Sneaky"}).status_code == 401
        assert c.post("/api/parent/pin", json={"pin": "1111"}).status_code == 401  # needs old PIN
        for _ in range(5):
            c.post("/api/parent/check", json={"pin": "0000"})
        assert c.post("/api/parent/check", json={"pin": "2468"}).status_code == 429  # locked out
