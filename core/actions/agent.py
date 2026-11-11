"""
Runs PC commands for one chat connection.

    reply = await agent.handle(text)     # None -> not a command, chat normally

Order: a pending yes/no question first, then instant rules for the common
one-word commands (no LLM call), then the planner. Tools marked confirm=True
are never run straight away: their prepare step finds the details, Yashi asks,
and the tool runs only on a clear yes in the next message.
"""
import logging
import re
import time
from dataclasses import dataclass, field
from typing import List, Optional

from core.actions import planner
from core.actions.registry import TOOLS, Result, load_tools

logger = logging.getLogger(__name__)
load_tools()

CONFIRM_TTL = 120                       # seconds a question stays open

_YES_WORD = (r"(?:yes|yeah|yep|yup|ya|haan|ha|han|sure|ok|okay|send(?: it)?|do it|go(?: ahead)?|"
             r"confirm(?:ed)?|correct|right|please(?: do)?|y)")
# One or more yes-words and nothing else: "yeah send it", "ok do it please".
_YES = re.compile(rf"^\s*{_YES_WORD}(?:[\s,.!]+{_YES_WORD})*[\s,.!]*$", re.I)
_NO = re.compile(r"^\s*(no|nope|nah|nahi|cancel|stop|don'?t|do not|wait|never ?mind|forget it|n)\b", re.I)


def is_yes(text: str) -> bool:
    return bool(_YES.match(text))


def is_no(text: str) -> bool:
    return bool(_NO.match(text))


# Instant commands: (pattern, tool, args). Music controls fall back to the
# system media keys when YouTube Music isn't open in Yashi's browser.
_FAST = [
    (r"(pause|stop)( the)?( music| song| it| this)?", "music_control", {"action": "pause"}),
    (r"(resume|unpause|continue|play)( the)?( music| song| it)?", "music_control", {"action": "resume"}),
    (r"(next|skip)( song| track| this| it| this song)?", "music_control", {"action": "next"}),
    (r"(previous|prev|last|go back)( song| track)?", "music_control", {"action": "previous"}),
    (r"(volume up|louder|turn it up)", "volume", {"action": "up"}),
    (r"(volume down|quieter|softer|turn it down)", "volume", {"action": "down"}),
    (r"(mute|unmute)", "volume", {"action": "mute"}),
    (r"(what'?s|what is) (playing|this song)|what song is this", "music_now_playing", {}),
    (r"what time is it|what'?s the time", "current_time", {}),
]
_MEDIA_FALLBACK = {"pause": "play_pause", "resume": "play_pause", "next": "next", "previous": "previous"}


def fast_path(text: str) -> Optional[dict]:
    cleaned = re.sub(r"^(hey |ok |okay )?(yashi[, ]+)?|[.!?]+$|\s*please$", "", text.strip(), flags=re.I).strip()
    for pattern, name, args in _FAST:
        if re.fullmatch(pattern, cleaned, re.I):
            return {"tool": name, "args": dict(args)}
    return None


@dataclass
class Pending:
    tool: str
    args: dict
    question: str
    rest: List[dict] = field(default_factory=list)      # actions after this one
    expires: float = 0.0


class ActionAgent:
    def __init__(self):
        self.pending: Optional[Pending] = None
        self.history: List[dict] = []                    # recent commands, for "send it to him too"

    async def handle(self, text: str) -> Optional[str]:
        if self.pending and time.time() < self.pending.expires:
            pending, self.pending = self.pending, None
            if is_yes(text):
                return await self._finish(pending)
            if is_no(text):
                return "Okay, I won't."
            # Anything else: drop the question and treat this as a new message.
        self.pending = None

        actions = None
        fast = fast_path(text)
        if fast:
            actions = [fast]
        elif planner.looks_like_command(text):
            actions = await planner.plan(text, self.history)
        if not actions:
            return None                                   # conversation, or the planner failed

        reply = await self._run(actions)
        self._remember(text, reply)
        return reply

    async def _finish(self, pending: Pending) -> str:
        result = await self._call(pending.tool, pending.args)
        reply = result.message
        if result.ok and pending.rest:
            reply = f"{reply} {await self._run(pending.rest)}"
        self._remember("yes", reply)
        return reply

    async def _run(self, actions: List[dict]) -> str:
        said = []
        for index, action in enumerate(actions):
            spec = TOOLS[action["tool"]]
            if spec.confirm:
                prepared = await spec.prepare(**action["args"])
                if isinstance(prepared, Result):          # couldn't get ready: explain and stop
                    said.append(prepared.message)
                    break
                question, args = prepared
                self.pending = Pending(spec.name, args, question, actions[index + 1:],
                                       time.time() + CONFIRM_TTL)
                said.append(question)
                break
            result = await self._call(action["tool"], action["args"])
            said.append(result.message)
            if not result.ok:
                break
        return " ".join(s for s in said if s)

    async def _call(self, name: str, args: dict) -> Result:
        if name == "music_control":
            from core.actions.tools_music import is_playing_here
            if not is_playing_here() and args.get("action") in _MEDIA_FALLBACK:
                name, args = "media", {"action": _MEDIA_FALLBACK[args["action"]]}
        try:
            return await TOOLS[name].run(**args)
        except Exception as error:
            logger.exception("Tool %s failed", name)
            return Result(False, f"That didn't work ({type(error).__name__}).")

    def _remember(self, text: str, reply: str) -> None:
        self.history = (self.history + [{"role": "user", "content": text},
                                        {"role": "assistant", "content": reply}])[-6:]
