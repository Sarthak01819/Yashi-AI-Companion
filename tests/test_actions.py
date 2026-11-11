"""PC control: command detection, plan checking, confirmations, safety."""
import asyncio

import pytest

from core.actions import agent as agent_mod
from core.actions import planner
from core.actions.registry import TOOLS, Result, Tool


def run(coro):
    return asyncio.run(coro)


def test_yes_no():
    for text in ("yes", "Yeah send it", "ok", "haan", "do it!", "send it please"):
        assert agent_mod.is_yes(text), text
    for text in ("no", "cancel", "don't", "wait", "never mind"):
        assert agent_mod.is_no(text), text
    assert not agent_mod.is_yes("yes but change it to 9pm")


def test_fast_path():
    assert agent_mod.fast_path("pause")["args"] == {"action": "pause"}
    assert agent_mod.fast_path("Yashi, next song please")["args"] == {"action": "next"}
    assert agent_mod.fast_path("what's playing?")["tool"] == "music_now_playing"
    assert agent_mod.fast_path("pause my life for a second") is None


def test_command_detection_skips_chat():
    assert planner.looks_like_command("open whatsapp")
    assert planner.looks_like_command("play some arijit")
    assert not planner.looks_like_command("i had such a long day honestly")
    assert not planner.looks_like_command("how are you feeling?")


def test_validate_drops_unknown_tools_and_args():
    plan = {"actions": [
        {"tool": "open_app", "args": {"name": "Notepad", "evil": "rm -rf"}},
        {"tool": "format_disk", "args": {}},
        {"tool": "whatsapp_send", "args": {"contact": "Mom"}},           # message missing
        {"tool": "volume", "args": {"action": "set", "level": "40%"}},
    ]}
    assert planner.validate(plan) == [
        {"tool": "open_app", "args": {"name": "Notepad"}},
        {"tool": "volume", "args": {"action": "set", "level": 40}},
    ]
    assert planner.validate(planner._extract_json('sure! {"actions": []} hope that helps')) == []


def test_pick_contact():
    from core.actions.tools_whatsapp import pick_contact
    titles = ["Rahul Sharma", "Rahul Gym", "Mom", "Dev Team"]
    assert pick_contact("mom", titles) == ("Mom", [])
    best, others = pick_contact("rahul", titles)
    assert best == "Rahul Sharma" and others == ["Rahul Gym"]          # ambiguous: Yashi asks which
    assert pick_contact("nobody", titles) == (None, [])


def test_site_urls():
    from core.actions.tools_web import resolve_url, site_key
    assert resolve_url("gmail") == "https://mail.google.com"
    assert resolve_url("github.com/anthropics") == "https://github.com/anthropics"
    assert resolve_url("my cousin's blog") is None
    assert site_key("the Amazon website") == "amazon"


@pytest.fixture
def fake_send(monkeypatch):
    sent = []

    async def prepare(contact, message):
        return f'Send "{message}" to {contact.title()}?', {"contact": contact.title(), "message": message}

    async def send(contact, message):
        sent.append((contact, message))
        return Result(True, f"Sent to {contact}.")

    monkeypatch.setitem(TOOLS, "whatsapp_send",
                        Tool("whatsapp_send", "", {"contact": "", "message": ""}, send, True, prepare))

    async def fake_plan(text, history=None):
        return [{"tool": "whatsapp_send", "args": {"contact": "mom", "message": "on my way"}}]

    monkeypatch.setattr(planner, "plan", fake_plan)
    return sent


def test_messages_wait_for_yes(fake_send):
    a = agent_mod.ActionAgent()
    assert run(a.handle("tell mom on my way")) == 'Send "on my way" to Mom?'
    assert fake_send == []                                            # nothing sent yet
    assert run(a.handle("yes")) == "Sent to Mom."
    assert fake_send == [("Mom", "on my way")]


def test_no_or_new_topic_cancels(fake_send):
    a = agent_mod.ActionAgent()
    run(a.handle("tell mom on my way"))
    assert run(a.handle("no")) == "Okay, I won't."
    run(a.handle("tell mom on my way"))
    run(a.handle("actually how was your day"))                       # a new message drops the question
    assert run(a.handle("yes")) is None
    assert fake_send == []


def test_chat_socket_refuses_other_websites():
    from fastapi.testclient import TestClient
    from starlette.websockets import WebSocketDisconnect
    from app.main import app
    client = TestClient(app)
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws/chat/x", headers={"origin": "https://evil.example"}) as ws:
            ws.receive_text()
