"""
Tool registry. A tool is an async function plus a short description and its
arguments, rendered into the planner prompt.

A tool returns a Result. Risky tools (sending a message, shutting down) are
registered with confirm=True: the agent first calls their `prepare` step,
reads the outcome back to the user, and only runs the tool after a "yes".
"""
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, Optional


@dataclass
class Result:
    ok: bool
    message: str = ""                 # what Yashi says about it
    data: Any = None


@dataclass
class Tool:
    name: str
    description: str
    args: Dict[str, str]              # arg name -> short description ("?" prefix = optional)
    run: Callable[..., Awaitable[Result]]
    confirm: bool = False
    # For confirm tools: resolve details first (e.g. find the exact contact) and
    # return the question to ask, or a failed Result. Returns (question, args).
    prepare: Optional[Callable[..., Awaitable[Any]]] = None
    examples: list = field(default_factory=list)


TOOLS: Dict[str, Tool] = {}


def tool(name: str, description: str, args: Optional[Dict[str, str]] = None, *,
         confirm: bool = False, prepare=None, examples=None):
    def register(func):
        TOOLS[name] = Tool(name, description, args or {}, func, confirm, prepare, examples or [])
        return func
    return register


def describe_tools() -> str:
    """Compact tool list for the planner prompt."""
    lines = []
    for t in TOOLS.values():
        params = ", ".join(f"{k}: {v}" for k, v in t.args.items())
        flag = " [asks the user first]" if t.confirm else ""
        lines.append(f"- {t.name}({params}): {t.description}{flag}")
    return "\n".join(lines)


def load_tools() -> Dict[str, Tool]:
    # Importing the modules registers their tools.
    import importlib
    for module in ("tools_system", "tools_web", "tools_music", "tools_whatsapp", "tools_files"):
        importlib.import_module(f"core.actions.{module}")
    return TOOLS
