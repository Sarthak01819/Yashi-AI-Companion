"""
Web Launcher Plugin — opens URLs or performs web searches.
"""

import re
import webbrowser
import urllib.parse
import logging
from typing import Optional, Dict, Any

from plugins.base_plugin import YashiPlugin

logger = logging.getLogger(__name__)


class Plugin(YashiPlugin):
    name = "web_launcher"
    description = "Opens websites or performs web searches"
    trigger_phrases = ["search", "google", "look up", "open website", "go to", "browse"]

    async def can_handle(self, text: str, intent: Optional[str] = None) -> bool:
        return intent == "open_url"

    async def execute(self, text: str, context: Dict[str, Any]) -> Dict[str, Any]:
        intent_data = context.get("intent") or {}
        target = intent_data.get("target", "").strip()

        if not target:
            return {"success": False, "message": "What would you like me to search for?", "data": None}

        # Determine if it's a direct URL or a search query
        if re.match(r'^https?://', target) or re.match(r'^[\w\-]+\.\w{2,}', target):
            url = target if target.startswith("http") else f"https://{target}"
            label = f"opening {url}"
        else:
            # Treat as search
            url = "https://www.google.com/search?q=" + urllib.parse.quote_plus(target)
            label = f"searching for '{target}'"

        try:
            webbrowser.open(url)
            logger.info("Opened URL: %s", url)
            return {
                "success": True,
                "message": f"Sure! I'm {label} in your browser.",
                "data": {"url": url},
            }
        except Exception as e:
            logger.error("Web launch failed: %s", e)
            return {
                "success": False,
                "message": "I couldn't open the browser. Is one installed?",
                "data": None,
            }
