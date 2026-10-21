"""
Personal fact extractor — heuristically pulls user facts from conversation.
Light-weight regex + keyword approach to avoid loading an extra NLP model.
"""

import re
import logging
from typing import List, Tuple

logger = logging.getLogger(__name__)

# (category, pattern_list)
FACT_PATTERNS: List[Tuple[str, List[str]]] = [
    ("name",     [r"my name is (\w+)", r"call me (\w+)"]),
    ("age",      [r"i(?:'m| am) (\d{1,3})(?: years? old)?", r"my age is (\d{1,3})"]),
    ("job",      [r"i(?:'m| am) a(?:n)? ([\w\s]+(?:developer|engineer|designer|teacher|student|doctor|nurse|manager|artist|writer|lawyer|chef|driver))", r"i work as (?:a(?:n)? )?([\w\s]+)"]),
    ("location", [r"i(?:'m| am) from ([\w\s,]+)", r"i live in ([\w\s,]+)", r"i(?:'m| am) based in ([\w\s,]+)"]),
    ("hobby",    [r"i (?:love|enjoy|like) ([\w\s]+ing)", r"my hobbies? (?:is|are|include) ([\w\s,]+)"]),
    ("pet",      [r"i have a(?:n)? (cat|dog|bird|hamster|rabbit|fish|turtle)", r"my (cat|dog|bird|hamster|rabbit|fish|turtle)(?:'s name is (\w+))?"]),
    ("goal",     [r"i want to ([\w\s]+)", r"my goal is to ([\w\s]+)", r"i(?:'m| am) trying to ([\w\s]+)"]),
]


# Words that follow "I'm" / "call me" / "I want to" but are never facts.
_NOT_A_NAME = {
    "going", "gonna", "just", "so", "not", "really", "very", "here", "back", "fine", "good", "ok",
    "okay", "tired", "sorry", "sure", "done", "home", "busy", "bored", "sad", "happy", "glad",
    "excited", "trying", "thinking", "feeling", "working", "doing", "making", "having", "getting",
    "later", "anytime", "maybe", "now", "sometimes", "whenever", "if", "when",
}
_BAD_ENDINGS = {"a", "an", "the", "to", "and", "or", "some", "my", "your", "for", "of", "with", "in", "on"}


def _valid(category: str, value: str, original: str) -> bool:
    words = value.split()
    if not words:
        return False
    if category == "name":
        if value in _NOT_A_NAME or len(value) < 2:
            return False
        # Names are written with a capital letter; "call me later" is not a name.
        return bool(re.search(rf"\b{re.escape(value)}\b", original, re.IGNORECASE)) and any(
            m.group(0)[0].isupper() for m in re.finditer(rf"\b{re.escape(value)}\b", original, re.IGNORECASE))
    if category in ("goal", "hobby", "job", "location"):
        return len(words) >= 2 and words[-1] not in _BAD_ENDINGS
    return True


def extract_facts(text: str) -> List[Tuple[str, str]]:
    """Return list of (category, fact_string) extracted from user text."""
    text_lower = text.lower().strip()
    found: List[Tuple[str, str]] = []

    for category, patterns in FACT_PATTERNS:
        for pattern in patterns:
            match = re.search(pattern, text_lower)
            if match:
                groups = [g for g in match.groups() if g]
                fact_value = " ".join(groups).strip()
                if fact_value and len(fact_value) < 120 and _valid(category, fact_value, text):
                    found.append((category, fact_value))
                break  # one match per category

    return found
