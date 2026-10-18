"""
Intent detector — maps user text to plugin intents.
Trailing punctuation is stripped from targets so "Open Spotify." works correctly.
"""
import re
from typing import Optional

# Something that actually looks like a file: name.ext, optionally with a path.
_FILENAME = r"[\w .\-/\\:]{1,60}\.\w{1,6}"

INTENT_PATTERNS = {
    "app_control": [
        r"(?:play\s+)?(?:the\s+)?(next|previous|last)\s+(?:song|track)",
        r"(?:go to\s+)?(?:the\s+)?(next|previous|last)\s+(?:song|track)",
        r"(pause|resume|next|previous|skip|stop|mute) (?:on |in )?spotify",
        r"spotify (pause|resume|next|previous|skip|stop|play)",
        r"(pause|next|previous|stop) (?:the )?music",
        r"volume (up|down|louder|quieter)",
    ],
    "spotify_search": [
        r"play (.+?) (?:on|in) spotify",
        r"play (.+?) by (.+)",
        r"search (?:for )?(?:song|music|track) (.+?) (?:on|in) spotify",
        r"play (.+?) song",
        r"^put on (?:some )?(.+)$",
        # Anchored: the whole message must be "play <something>", so
        # "can you play devil's advocate for a second" is left to the LLM.
        r"^play (.+)$",
    ],
    "youtube_search": [
        r"open (?:youtube|you tube) (?:and )?search (?:for )?(.+)",
        r"search (?:youtube|you tube) (?:for )?(.+)",
        r"(?:search|find) (.+?) on (?:youtube|you tube)",
    ],
    "open_website": [
        r"open (.+?) (?:on|in) (?:the )?(?:browser|web|internet)$",
        r"open (?:website|site) (.+)$",
    ],
    # Anchored + short targets only. "start learning python" or "open up about
    # how you feel" must reach the LLM, not the app launcher. The launcher also
    # verifies the target resolves to a real app before claiming the message.
    "open_app": [
        r"^open (?:the )?([\w.+\- ]{2,28}?)(?: app)?$",
        r"^launch (?:the )?([\w.+\- ]{2,28}?)(?: app)?$",
        r"^start (?:the )?([\w.+\- ]{2,28}?)(?: app)?$",
    ],
    "open_url": [
        r"search (?:the web|google|online|for|about) (?:for |about )?(.*)",
        r"google (.+)",
        r"look up (.+)",
        r"open (?:the )?(?:website|site|url|browser) (.+)?",
        r"go to (.+\.(?:com|org|net|io|dev|ai|co).*)",
    ],
    "file_create": [
        r"create (?:a )?(?:new )?file (?:called |named )?(.+)",
        r"make (?:a )?(?:new )?file (?:called |named )?(.+)",
        r"write (?:a )?(?:new )?file (.+)",
        r"save (?:a )?(?:new )?file (?:called |named )?(.+)",
    ],
    # The second capture group must look like a real filename, otherwise
    # everyday phrases ("save money to buy a car", "add some spice to my life")
    # would be treated as file commands.
    "file_write": [
        r"write (.+?) to (?:the )?file (.+)",
        r"^write (.+?) (?:in|into) (" + _FILENAME + r")$",
        r"^save (.+?) to (?:the )?file (.+)$",
        r"^save (.+?) to (" + _FILENAME + r")$",
        r"^put (.+?) (?:in|into) (" + _FILENAME + r")$",
        r"^overwrite (" + _FILENAME + r") with (.+)$",
        r"^update (" + _FILENAME + r") with (.+)$",
    ],
    "file_append": [
        r"append (.+?) to (?:the )?file (.+)",
        r"^append (.+?) to (" + _FILENAME + r")$",
        r"^add (.+?) to (?:the )?file (.+)$",
        r"^add (.+?) to (" + _FILENAME + r")$",
    ],
    "find_file": [
        r"find (?:the )?file (.+)",
        r"where is (?:my )?(.+\.(?:pdf|docx|txt|py|js|mp3|mp4|png|jpg|zip))",
        r"^locate ([\w.\-*& ]{2,40})$",
    ],
    "open_folder": [
        r"open (?:the )?(?:folder|directory|dir)\s+(.+)",
        r"navigate to (?:the )?(?:folder|directory)\s+(.+)",
        r"go to (?:the )?(?:folder|directory)\s+(.+)",
        r"find (?:the )?(?:folder|directory)\s+(.+)",
        r"where is (?:my )?(.+) folder",
    ],
}

# Characters to strip from the END of captured targets
# Handles: "Open Spotify." "Play music!" "Search google?"
_STRIP = ".,!?;: "


def _clean(s: str) -> str:
    """Strip trailing punctuation and whitespace from a captured group."""
    return s.strip(_STRIP)


def detect_intent(text: str) -> Optional[dict]:
    raw_text = text.strip()

    for intent, patterns in INTENT_PATTERNS.items():
        for pattern in patterns:
            m = re.search(pattern, raw_text, re.IGNORECASE)
            if m:
                groups = [g for g in m.groups() if g]
                target = _clean(groups[0]) if groups else ""
                extra  = _clean(groups[1]) if len(groups) > 1 else ""
                return {"intent": intent, "target": target, "extra": extra}

    return None
