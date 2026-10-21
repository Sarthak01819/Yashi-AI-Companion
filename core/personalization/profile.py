"""
The user's profile, daily check-ins, and gamified stats.

Everything shown on the profile dashboard is derived from real data:
messages you've sent, days you've talked, check-ins you've logged and the
facts Yashi has learned about you.
"""

import datetime as dt
import json
import time
from copy import deepcopy

from core.memory.database import db_cursor

STATE_KEY = "user_profile"
AVATAR_MAX_CHARS = 700_000          # ~512px JPEG as a data URL

DEFAULT_PROFILE = {
    "display_name": "",
    "pronouns": "",
    "birthday": "",                 # "MM-DD"
    "title": "",
    "about": "",
    "motto": "",
    "interests": [],
    "goals": [],
    "avatar": "",                   # data:image/... URL (resized in the browser)
}

LIMITS = {"display_name": 32, "pronouns": 20, "birthday": 5, "title": 40, "about": 400, "motto": 160}

# Friendship titles by level.
BOND_TITLES = [
    (1, "New Face"), (2, "Acquaintance"), (4, "Friend"),
    (6, "Close Friend"), (9, "Best Friend"), (13, "Kindred Spirit"),
]

EMOTION_VALENCE = {
    "joyful": 1.0, "happy": 0.7, "content": 0.4, "excited": 0.6, "neutral": 0.0,
    "concerned": -0.3, "sad": -0.6, "distressed": -0.9,
}


# ── Profile ──────────────────────────────────────────────────────────────────
def _normalise(data: dict) -> dict:
    profile = deepcopy(DEFAULT_PROFILE)
    if not isinstance(data, dict):
        return profile
    for key, limit in LIMITS.items():
        if isinstance(data.get(key), str):
            profile[key] = data[key].strip()[:limit]
    for key in ("interests", "goals"):
        if isinstance(data.get(key), list):
            profile[key] = [str(x).strip()[:40] for x in data[key] if str(x).strip()][:12]
    avatar = data.get("avatar")
    if isinstance(avatar, str) and (avatar == "" or (
            avatar.startswith("data:image/") and len(avatar) <= AVATAR_MAX_CHARS)):
        profile["avatar"] = avatar
    return profile


def load_profile() -> dict:
    try:
        with db_cursor() as cur:
            cur.execute("SELECT value FROM behavior_state WHERE key=?", (STATE_KEY,))
            row = cur.fetchone()
        return _normalise(json.loads(row[0])) if row else deepcopy(DEFAULT_PROFILE)
    except Exception:
        return deepcopy(DEFAULT_PROFILE)


def save_profile(data: dict) -> dict:
    profile = _normalise(data)
    with db_cursor() as cur:
        cur.execute(
            "INSERT INTO behavior_state (key, value, updated_at) VALUES (?,?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
            (STATE_KEY, json.dumps(profile, ensure_ascii=False), time.time()),
        )
    return profile


def describe_user(profile: dict) -> str:
    """Short text about the user for Yashi's system prompt ('' if nothing set)."""
    bits = []
    if profile.get("display_name"):
        name = profile["display_name"]
        if profile.get("pronouns"):
            name += f" ({profile['pronouns']})"
        bits.append(f"Their name is {name}.")
    if profile.get("about"):
        bits.append(f"In their own words: {profile['about']}")
    if profile.get("interests"):
        bits.append("They're into " + ", ".join(profile["interests"]) + ".")
    if profile.get("goals"):
        bits.append("Things they're working towards: " + "; ".join(profile["goals"]) + ".")
    if profile.get("birthday") and dt.date.today().strftime("%m-%d") == profile["birthday"]:
        bits.append("Today is their birthday!")
    return " ".join(bits)


# ── Daily check-in ───────────────────────────────────────────────────────────
def _score(value) -> int:
    try:
        return max(1, min(10, int(value)))
    except (TypeError, ValueError):
        return 5


def save_checkin(willpower, health, mood, note: str = "") -> dict:
    today = dt.date.today().isoformat()
    row = {"date": today, "willpower": _score(willpower), "health": _score(health),
           "mood": _score(mood), "note": (note or "").strip()[:200]}
    with db_cursor() as cur:
        cur.execute(
            "INSERT INTO daily_checkins (date, willpower, health, mood, note, updated_at) "
            "VALUES (:date, :willpower, :health, :mood, :note, :ts) "
            "ON CONFLICT(date) DO UPDATE SET willpower=excluded.willpower, health=excluded.health, "
            "mood=excluded.mood, note=excluded.note, updated_at=excluded.updated_at",
            {**row, "ts": time.time()},
        )
    return row


# ── Stats ────────────────────────────────────────────────────────────────────
def level_for(xp: int) -> tuple:
    """Level L needs 50*L*(L-1) XP: L2=100, L3=300, L4=600, L5=1000 ..."""
    level = 1
    while 50 * (level + 1) * level <= xp:
        level += 1
    return level, 50 * level * (level - 1), 50 * (level + 1) * level


def bond_title(level: int) -> str:
    title = BOND_TITLES[0][1]
    for threshold, name in BOND_TITLES:
        if level >= threshold:
            title = name
    return title


def _streak(days: set, today: dt.date) -> int:
    start = today if today in days else today - dt.timedelta(days=1)
    streak = 0
    while start - dt.timedelta(days=streak) in days:
        streak += 1
    return streak


def compute_stats() -> dict:
    today = dt.date.today()
    with db_cursor() as cur:
        cur.execute("SELECT content, emotion, timestamp FROM conversations WHERE role='user'")
        messages = cur.fetchall()
        cur.execute("SELECT COUNT(*) FROM personal_facts")
        facts = cur.fetchone()[0]
        cur.execute("SELECT date, willpower, health, mood FROM daily_checkins ORDER BY date DESC LIMIT 14")
        checkins = [dict(r) for r in cur.fetchall()]
        cur.execute("SELECT COUNT(*) FROM daily_checkins")
        checkin_total = cur.fetchone()[0]

    days = {dt.date.fromtimestamp(m["timestamp"]) for m in messages}
    streak = _streak(days, today)
    recent_days = sum(1 for d in days if (today - d).days < 14)
    recent = sorted(messages, key=lambda m: m["timestamp"])[-30:]
    valence = (sum(EMOTION_VALENCE.get(m["emotion"], 0.0) for m in recent) / len(recent)) if recent else 0.0
    avg_words = (sum(len((m["content"] or "").split()) for m in messages) / len(messages)) if messages else 0

    xp = len(messages) * 10 + len(days) * 25 + checkin_total * 20 + facts * 15
    level, level_floor, next_level = level_for(xp)

    radar = {
        "Bond": min(100, round(len(messages) / 3)),
        "Mood": round((valence + 1) * 50),
        "Consistency": round(recent_days / 14 * 100),
        "Openness": min(100, facts * 10),
        "Depth": min(100, round(avg_words * 6)),
    }

    today_checkin = next((c for c in checkins if c["date"] == today.isoformat()), None)
    month_days = sorted(d.isoformat() for d in days if d.year == today.year and d.month == today.month)

    return {
        "xp": xp,
        "level": level,
        "level_floor": level_floor,
        "next_level_xp": next_level,
        "title": bond_title(level),
        "streak": streak,
        "days_together": len(days),
        "messages": len(messages),
        "facts": facts,
        "checkins": checkin_total,
        "radar": radar,
        "today": today_checkin,
        "checkin_history": list(reversed(checkins)),
        "active_days_this_month": month_days,
    }
