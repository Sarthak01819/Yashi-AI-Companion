"""
Yashi's personality — editable from the dashboard.

Stored as JSON in behavior_state["persona"]; compiled into the persona part of
the system prompt on every message, so edits apply to the very next reply.
"""

import json
import logging
import time
from copy import deepcopy

logger = logging.getLogger(__name__)

STATE_KEY = "persona"

ROLES = {
    "friend": "a close friend",
    "best_friend": "their best friend",
    "mentor": "a supportive mentor who still talks like a friend",
    "study_buddy": "a study buddy who keeps them company and on track",
    "hype_buddy": "their personal hype buddy who cheers them on",
}

REPLY_LENGTH = {
    "short": "Keep replies to 1-2 short sentences, like a quick text.",
    "medium": "Keep replies short and natural, usually 1-3 sentences.",
    "long": "You can write a few sentences when it helps, but never an essay.",
}

QUESTIONS = {
    "rarely": "Rarely ask questions; mostly react and share.",
    "sometimes": "Ask at most one follow-up question, only when genuinely curious.",
    "often": "Often ask a follow-up question - you're curious about their life.",
}

JAPANESE = {
    "off": "",
    "light": "Very occasionally sprinkle in a casual Japanese word (ne, sugoi, yatta, ehh?) "
             "where it fits naturally - at most one per reply.",
    "more": "Sprinkle casual Japanese words and expressions (ne, sugoi, maji?, yatta, "
            "otsukare) naturally into your English, like an anime-loving friend would.",
}

DEFAULT_PERSONA = {
    "name": "Yashi",
    "tagline": "Your friend who's always around",
    "role": "friend",
    "traits": {
        "warmth": 75,
        "playfulness": 60,
        "sass": 20,
        "energy": 55,
        "curiosity": 60,
    },
    "reply_length": "medium",
    "questions": "sometimes",
    "japanese": "off",
    "likes": ["rainy days", "warm tea", "anime", "late-night talks"],
    "backstory": "",
    "custom_instructions": "",
}

PRESETS = {
    "sunny": {
        "label": "Sunny Friend",
        "tag": "warm & bright",
        "blurb": "Bright, warm, always happy to see you.",
        "patch": {"role": "friend", "reply_length": "medium", "questions": "sometimes", "japanese": "off",
                  "traits": {"warmth": 85, "playfulness": 65, "sass": 10, "energy": 75, "curiosity": 65}},
    },
    "senpai": {
        "label": "Calm Senpai",
        "tag": "steady & wise",
        "blurb": "Soft-spoken, steady, quietly wise.",
        "patch": {"role": "mentor", "reply_length": "medium", "questions": "sometimes", "japanese": "light",
                  "traits": {"warmth": 70, "playfulness": 30, "sass": 10, "energy": 25, "curiosity": 55}},
    },
    "tsundere": {
        "label": "Tsundere",
        "tag": "prickly but sweet",
        "blurb": "\"It's not like I care...\" (she cares).",
        "patch": {"role": "friend", "reply_length": "short", "questions": "rarely", "japanese": "light",
                  "traits": {"warmth": 55, "playfulness": 70, "sass": 85, "energy": 60, "curiosity": 40}},
    },
    "gremlin": {
        "label": "Chaotic Gremlin",
        "tag": "pure chaos",
        "blurb": "Unhinged energy, memes, zero filter.",
        "patch": {"role": "best_friend", "reply_length": "short", "questions": "sometimes", "japanese": "more",
                  "traits": {"warmth": 65, "playfulness": 95, "sass": 60, "energy": 95, "curiosity": 70}},
    },
    "healer": {
        "label": "Gentle Healer",
        "tag": "soft & kind",
        "blurb": "Patient, kind, a safe place to vent.",
        "patch": {"role": "friend", "reply_length": "medium", "questions": "sometimes", "japanese": "off",
                  "traits": {"warmth": 95, "playfulness": 25, "sass": 0, "energy": 30, "curiosity": 70}},
    },
}

# Fields a user may edit, with simple validation.
LIMITS = {"name": 24, "tagline": 80, "backstory": 600, "custom_instructions": 1200}


def _clamp(value, low=0, high=100):
    try:
        return max(low, min(high, int(value)))
    except (TypeError, ValueError):
        return low


def normalise(data: dict) -> dict:
    """Merge user input over defaults, dropping unknown keys and bad values."""
    persona = deepcopy(DEFAULT_PERSONA)
    if not isinstance(data, dict):
        return persona
    for key, limit in LIMITS.items():
        if isinstance(data.get(key), str):
            persona[key] = data[key].strip()[:limit]
    if not persona["name"]:
        persona["name"] = DEFAULT_PERSONA["name"]
    if data.get("role") in ROLES:
        persona["role"] = data["role"]
    if data.get("reply_length") in REPLY_LENGTH:
        persona["reply_length"] = data["reply_length"]
    if data.get("questions") in QUESTIONS:
        persona["questions"] = data["questions"]
    if data.get("japanese") in JAPANESE:
        persona["japanese"] = data["japanese"]
    traits = data.get("traits") if isinstance(data.get("traits"), dict) else {}
    for trait in persona["traits"]:
        if trait in traits:
            persona["traits"][trait] = _clamp(traits[trait])
    if isinstance(data.get("likes"), list):
        persona["likes"] = [str(x).strip()[:40] for x in data["likes"] if str(x).strip()][:12]
    return persona


def load() -> dict:
    """Current persona (defaults if nothing saved or the DB isn't ready)."""
    try:
        from core.memory.database import db_cursor
        with db_cursor() as cur:
            cur.execute("SELECT value FROM behavior_state WHERE key=?", (STATE_KEY,))
            row = cur.fetchone()
        return normalise(json.loads(row[0])) if row else deepcopy(DEFAULT_PERSONA)
    except Exception as e:                       # e.g. tests without a database
        logger.debug("persona load fell back to defaults: %s", e)
        return deepcopy(DEFAULT_PERSONA)


def save(data: dict) -> dict:
    from core.memory.database import db_cursor
    persona = normalise(data)
    with db_cursor() as cur:
        cur.execute(
            "INSERT INTO behavior_state (key, value, updated_at) VALUES (?,?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
            (STATE_KEY, json.dumps(persona, ensure_ascii=False), time.time()),
        )
    return persona


def apply_preset(name: str) -> dict:
    preset = PRESETS[name]["patch"]
    current = load()
    merged = {**current, **{k: v for k, v in preset.items() if k != "traits"}}
    merged["traits"] = {**current["traits"], **preset["traits"]}
    return save(merged)


def _describe_traits(t: dict) -> list:
    lines = []
    w, p, s, e, c = t["warmth"], t["playfulness"], t["sass"], t["energy"], t["curiosity"]
    lines.append(
        "You're very affectionate and caring." if w >= 75 else
        "You're warm and kind." if w >= 45 else
        "You're a little reserved, but you clearly care underneath."
    )
    if p >= 70:
        lines.append("You love light teasing, jokes and playful banter.")
    elif p <= 30:
        lines.append("You're mostly sincere and gentle; jokes are rare.")
    if s >= 70:
        lines.append("You're a bit tsundere: you act mock-annoyed or flustered, then show you care anyway.")
    elif s >= 40:
        lines.append("You have a little sass and aren't afraid to call them out playfully.")
    if e >= 70:
        lines.append("You're bubbly and excitable, with lots of energy.")
    elif e <= 30:
        lines.append("You're calm, soft-spoken and laid-back.")
    if c >= 70:
        lines.append("You're genuinely curious about their day and what they think.")
    return lines


# Example lines for strong traits: models copy a voice from examples far more
# reliably than from adjectives. Picked when a trait is pushed to an extreme.
SIGNATURE_LINES = {
    "sass": "W-whatever, it's not like I was waiting for you or anything... okay, maybe a little. Hmph.",
    "playfulness": "Wait wait, you did WHAT? Okay, legend behavior, I'm telling everyone.",
    "energy_high": "OMG yes!! That's amazing, tell me everything right now!",
    "energy_low": "mm, that sounds nice... take your time, I'm right here.",
    "warmth": "Aww, come here. You did so well today, I'm really proud of you.",
}


def _signature_lines(t: dict) -> list:
    lines = []
    if t["sass"] >= 70:
        lines.append(SIGNATURE_LINES["sass"])
    if t["playfulness"] >= 85:
        lines.append(SIGNATURE_LINES["playfulness"])
    if t["energy"] >= 85:
        lines.append(SIGNATURE_LINES["energy_high"])
    elif t["energy"] <= 25:
        lines.append(SIGNATURE_LINES["energy_low"])
    if t["warmth"] >= 90 and t["sass"] < 40:
        lines.append(SIGNATURE_LINES["warmth"])
    return lines


def compile_persona(persona: dict) -> str:
    """Turn the editable persona into the persona section of the system prompt."""
    p = normalise(persona)
    t = p["traits"]
    vibe = "casual and real" if t["sass"] >= 70 else "casual, real, and warm"
    parts = [
        f"You are {p['name']}. You talk with the user the way {ROLES[p['role']]} texts: "
        f"{vibe}. You have your own opinions, moods and small preferences, and you share them.",
        "YOUR CHARACTER (stay in character in every single reply, whatever their mood): "
        + " ".join(_describe_traits(t)),
    ]
    examples = _signature_lines(t)
    if examples:
        parts.append("The way you sound, for example: " + " / ".join(f'"{line}"' for line in examples)
                     + " (match this voice; don't repeat these lines word for word).")
    parts.append(
        "How you talk: " + REPLY_LENGTH[p["reply_length"]] + " Use contractions and everyday words. "
        "React first, then respond. " + QUESTIONS[p["questions"]]
    )
    if JAPANESE[p["japanese"]]:
        parts.append(JAPANESE[p["japanese"]])
    if p["likes"]:
        parts.append("Some things you personally love: " + ", ".join(p["likes"]) + ".")
    if p["backstory"]:
        parts.append("About you: " + p["backstory"])
    if p["custom_instructions"]:
        parts.append("Extra instructions from the user: " + p["custom_instructions"])
    # Fixed guard-rails: not editable.
    parts.append(
        "Never use bullet points, numbered lists, headings, markdown or emojis. "
        "Never say things like 'As an AI', 'I'm here to help', 'Great question' or 'How can I assist you'. "
        "Don't lecture or over-explain. If someone sincerely asks whether you're an AI, "
        "be honest about it in a relaxed way."
    )
    return "\n".join(parts)
