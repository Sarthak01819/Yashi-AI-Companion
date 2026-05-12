"""
Base plugin interface. All Yashi plugins must inherit from YashiPlugin.
"""

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any


class YashiPlugin(ABC):
    name: str = "base"
    description: str = "Base plugin"
    trigger_phrases: list = []   # keywords/phrases that activate this plugin

    @abstractmethod
    async def can_handle(self, text: str, intent: Optional[str] = None) -> bool:
        """Return True if this plugin should handle the given text."""
        ...

    @abstractmethod
    async def execute(self, text: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute the plugin action.
        Returns dict with:
            success: bool
            message: str    (displayed to user)
            data:    any    (optional structured result)
        """
        ...

    def __repr__(self):
        return f"<Plugin:{self.name}>"
