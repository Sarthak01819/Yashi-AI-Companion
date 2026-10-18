"""
File Search Plugin — searches for files on the local filesystem.
"""

import fnmatch
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List

from plugins.base_plugin import YashiPlugin

logger = logging.getLogger(__name__)

SEARCH_ROOTS = [
    Path.home() / "Documents",
    Path.home() / "Downloads",
    Path.home() / "Desktop",
    Path.home(),
]


class Plugin(YashiPlugin):
    name = "file_search"
    description = "Searches for files on the local system"
    trigger_phrases = ["find file", "search file", "locate", "where is"]

    async def can_handle(self, text: str, intent: Optional[str] = None) -> bool:
        return intent == "find_file"

    async def execute(self, text: str, context: Dict[str, Any]) -> Dict[str, Any]:
        intent_data = context.get("intent") or {}
        target = intent_data.get("target", "").strip()

        if not target:
            return {"success": False, "message": "What file should I look for?", "data": None}

        results: List[str] = []
        pattern = f"*{target}*" if "*" not in target else target

        for root in SEARCH_ROOTS:
            if not root.exists():
                continue
            try:
                for entry in root.rglob("*"):
                    if fnmatch.fnmatch(entry.name.lower(), pattern.lower()):
                        results.append(str(entry))
                        if len(results) >= 5:
                            break
            except PermissionError:
                continue
            if len(results) >= 5:
                break

        if results:
            found_str = "\n".join(f"  • {p}" for p in results)
            return {
                "success": True,
                "message": f"I found {len(results)} file(s) matching '{target}':\n{found_str}",
                "data": {"files": results},
            }
        else:
            return {
                "success": True,
                "message": f"I searched your common folders but couldn't find any file matching '{target}'.",
                "data": {"files": []},
            }
