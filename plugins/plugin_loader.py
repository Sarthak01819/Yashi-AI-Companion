"""
Dynamic plugin loader — discovers and loads all plugins from the plugins/ directory.
"""

import importlib
import logging
from pathlib import Path
from typing import List

from plugins.base_plugin import YashiPlugin

logger = logging.getLogger(__name__)
_loaded_plugins: List[YashiPlugin] = []


def load_all_plugins() -> List[YashiPlugin]:
    global _loaded_plugins
    _loaded_plugins = []

    plugins_dir = Path(__file__).parent
    for sub in sorted(plugins_dir.iterdir()):
        if sub.is_dir() and (sub / "plugin.py").exists():
            module_path = f"plugins.{sub.name}.plugin"
            try:
                mod = importlib.import_module(module_path)
                plugin_class = getattr(mod, "Plugin", None)
                if plugin_class and issubclass(plugin_class, YashiPlugin):
                    instance = plugin_class()
                    _loaded_plugins.append(instance)
                    logger.info("Loaded plugin: %s", instance.name)
            except Exception as e:
                logger.warning("Failed to load plugin %s: %s", sub.name, e)

    logger.info("Total plugins loaded: %d", len(_loaded_plugins))
    return _loaded_plugins


async def dispatch(text: str, context: dict) -> dict:
    """
    Try all plugins; return first successful result, or None.
    """
    from plugins.intent_detector import detect_intent
    intent_data = detect_intent(text)
    intent = intent_data["intent"] if intent_data else None

    for plugin in _loaded_plugins:
        try:
            if await plugin.can_handle(text, intent):
                result = await plugin.execute(text, {**context, "intent": intent_data})
                if result.get("success"):
                    return result
        except Exception as e:
            logger.warning("Plugin %s error: %s", plugin.name, e)

    return {"success": False, "message": "", "data": None}


def get_plugins() -> List[YashiPlugin]:
    return _loaded_plugins
