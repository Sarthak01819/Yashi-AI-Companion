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
    ("name",     [r"my name is (\w+)", r"i'm (\w+)", r"call me (\w+)"]),
    ("age",      [r"i(?:'m| am) (\d{1,3})(?: years? old)?", r"my age is (\d{1,3})"]),
    ("job",      [r"i(?:'m| am) a(?:n)? ([\w\s]+(?:developer|engineer|designer|teacher|student|doctor|nurse|manager|artist|writer|lawyer|chef|driver))", r"i work as (?:a(?:n)? )?([\w\s]+)"]),
    ("location", [r"i(?:'m| am) from ([\w\s,]+)", r"i live in ([\w\s,]+)", r"i(?:'m| am) based in ([\w\s,]+)"]),
    ("hobby",    [r"i (?:love|enjoy|like) ([\w\s]+ing)", r"my hobbies? (?:is|are|include) ([\w\s,]+)"]),
    ("pet",      [r"i have a(?:n)? (cat|dog|bird|hamster|rabbit|fish|turtle)", r"my (cat|dog|bird|hamster|rabbit|fish|turtle)(?:'s name is (\w+))?"]),
    ("goal",     [r"i want to ([\w\s]+)", r"my goal is to ([\w\s]+)", r"i(?:'m| am) trying to ([\w\s]+)"]),
]


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
                if fact_value and len(fact_value) < 120:
                    found.append((category, fact_value))
                break  # one match per category

    return found
