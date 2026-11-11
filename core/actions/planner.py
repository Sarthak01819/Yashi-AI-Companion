"""
Planner: is this message a PC command, and if so which tools, with which
arguments?

A cheap keyword check runs first so ordinary chat never pays for an extra
LLM call. Only messages that look like commands are sent to the brain, which
answers with JSON: {"actions": [{"tool": ..., "args": {...}}]}. An empty
action list means "that was conversation after all".
"""
import json
import logging
import re
from typing import List, Optional

import httpx

import config.settings as S
from core.actions.registry import TOOLS, describe_tools

logger = logging.getLogger(__name__)

# Words that suggest the user wants something done on the PC.
_COMMAND = re.compile(
    r"\b(open|launch|start|close|quit|exit|kill|play|pause|resume|unpause|skip|next|previous|prev|"
    r"shuffle|repeat|replay|like (?:this|the) song|dislike|volume|mute|unmute|louder|quieter|softer|"
    r"search|google|look up|lookup|find|locate|go to|navigate|visit|youtube|yt music|whatsapp|"
    r"message|text|send|dm|reply to|tell (?!me\b)\w+|type|write|press|hit enter|screenshot|screen shot|lock|"
    r"shut ?down|restart|reboot|sleep mode|minimi[sz]e|maximi[sz]e|switch to|bring up|show me|"
    r"what(?:'s| is) playing|what song|which song|what time|create (?:a )?file|save (?:a )?file|"
    r"put on|turn (?:up|down|on|off)|folder|file|website|site|browser|tab)\b",
    re.I,
)


def looks_like_command(text: str) -> bool:
    return bool(_COMMAND.search(text))


SYSTEM = """You control the user's Windows PC. Turn their message into tool calls.

TOOLS
{tools}

Reply with ONLY one JSON object, no other text:
{{"actions": [{{"tool": "<name>", "args": {{...}}}}]}}

RULES
- If the message is conversation, a question about you, or a feeling (not a request to do
  something on the PC), reply {{"actions": []}}.
- Use the fewest actions, in order. Use only the tool and argument names listed.
- "play <music>" with no place given means music_play. "on YouTube" or a video means youtube_play.
- Music controls (pause, skip, like, shuffle) go to music_control. "volume" alone is system volume;
  "music volume" is music_volume.
- "search X on <site>" is search_site; "search X" / "google X" is web_search.
- WhatsApp: put the contact name and the message exactly as the user wants it sent. Turn
  "tell Rahul I'm late" into message "I'm late" (first person, as the user writes). Do not add
  greetings, emojis or anything the user didn't ask for.
- Never invent contacts, files or URLs the user didn't mention.

EXAMPLES
"open whatsapp" -> {{"actions": [{{"tool": "open_app", "args": {{"name": "WhatsApp"}}}}]}}
"play tum hi ho" -> {{"actions": [{{"tool": "music_play", "args": {{"query": "tum hi ho"}}}}]}}
"put on some lofi playlist" -> {{"actions": [{{"tool": "music_play", "args": {{"query": "lofi", "kind": "playlist"}}}}]}}
"play mrbeast's latest video on youtube" -> {{"actions": [{{"tool": "youtube_play", "args": {{"query": "mrbeast latest video"}}}}]}}
"search running shoes on amazon" -> {{"actions": [{{"tool": "search_site", "args": {{"site": "amazon", "query": "running shoes"}}}}]}}
"tell mom I'll be home by 8" -> {{"actions": [{{"tool": "whatsapp_send", "args": {{"contact": "mom", "message": "I'll be home by 8"}}}}]}}
"open notepad and type hello world" -> {{"actions": [{{"tool": "open_app", "args": {{"name": "Notepad"}}}}, {{"tool": "type_text", "args": {{"text": "hello world"}}}}]}}
"i'm so tired of everything today" -> {{"actions": []}}"""


def _extract_json(text: str) -> Optional[dict]:
    text = text.strip()
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        return json.loads(text[start:end + 1])
    except ValueError:
        return None


def _coerce(value, hint: str):
    if isinstance(value, str) and ("0-100" in hint):
        digits = re.search(r"\d+", value)
        return int(digits.group()) if digits else None
    if isinstance(value, str) and "true" in hint and value.lower() in ("true", "false"):
        return value.lower() == "true"
    return value


def validate(plan: Optional[dict]) -> List[dict]:
    """Keep only known tools with known arguments; required args must be present."""
    actions = []
    for item in (plan or {}).get("actions") or []:
        if not isinstance(item, dict) or item.get("tool") not in TOOLS:
            continue
        spec = TOOLS[item["tool"]].args
        names = {k.lstrip("?"): k for k in spec}
        args = {}
        for key, value in (item.get("args") or {}).items():
            if key in names and value not in (None, ""):
                args[key] = _coerce(value, spec[names[key]])
        if all(k.lstrip("?") in args for k in spec if not k.startswith("?")):
            actions.append({"tool": item["tool"], "args": args})
    return actions


async def _ollama(system: str, messages: list) -> str:
    model = S.ACTION_MODEL or S.OLLAMA_CLOUD_MODEL
    body = {
        "model": model, "stream": False, "format": "json",
        "think": "low" if model.startswith("gpt-oss") else False,
        "messages": [{"role": "system", "content": system}] + messages,
        "options": {"temperature": 0.1, "num_predict": 400},
    }
    async with httpx.AsyncClient(base_url=S.OLLAMA_CLOUD_URL, timeout=30,
                                 headers={"Authorization": f"Bearer {S.OLLAMA_API_KEY}"}) as client:
        response = await client.post("/api/chat", json=body)
        response.raise_for_status()
        return response.json().get("message", {}).get("content", "")


async def _complete(system: str, messages: list) -> str:
    backend = getattr(S, "LLM_BACKEND", "ollama_cloud")
    if backend == "ollama_cloud" and S.OLLAMA_API_KEY:
        return await _ollama(system, messages)
    from core.conversation.engine import _get_llm
    return await _get_llm(backend).generate(prompt=messages[-1]["content"], system=system, messages=messages)


async def plan(text: str, history: Optional[list] = None) -> Optional[List[dict]]:
    """List of {"tool", "args"} (possibly empty), or None if the brain failed."""
    messages = list(history or [])[-4:] + [{"role": "user", "content": text}]
    try:
        raw = await _complete(SYSTEM.format(tools=describe_tools()), messages)
    except Exception as error:
        logger.warning("Action planner failed: %s", error)
        return None
    actions = validate(_extract_json(raw))
    # Tool names only at INFO: arguments can be private (message text, typed text).
    logger.info("Planned actions: %s", [action["tool"] for action in actions] or "none")
    logger.debug("Planned %r -> %s", text, actions)
    return actions
