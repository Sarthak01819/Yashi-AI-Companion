"""
File Operations Plugin — create files, search directories, open folders.
"""
import os, re, sys, fnmatch, logging, subprocess
from pathlib import Path
from typing import Optional, Dict, Any, List
from plugins.base_plugin import YashiPlugin

logger = logging.getLogger(__name__)

SEARCH_ROOTS = [
    Path.home() / "Documents",
    Path.home() / "Downloads",
    Path.home() / "Desktop",
    Path.home() / "Pictures",
    Path.home() / "Music",
    Path.home() / "Videos",
    Path.home(),
]

DEFAULT_CREATE_DIR = Path.home() / "Documents"
DEFAULT_CREATE_FALLBACK = Path.home() / "Desktop"


def _open_path(path: Path) -> bool:
    try:
        if sys.platform == "win32":
            os.startfile(str(path))
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])
        return True
    except Exception as e:
        logger.warning("Cannot open %s: %s", path, e)
        return False


def _search_dirs(name: str) -> List[Path]:
    name_lower = name.lower().strip()
    results = []
    for root in SEARCH_ROOTS:
        if not root.exists(): continue
        try:
            for entry in root.rglob("*"):
                if entry.is_dir() and name_lower in entry.name.lower():
                    results.append(entry)
                    if len(results) >= 5: return results
        except (PermissionError, OSError):
            continue
    return results


def _search_files(pattern: str) -> List[Path]:
    pat = f"*{pattern.lower()}*"
    results = []
    for root in SEARCH_ROOTS:
        if not root.exists(): continue
        try:
            for entry in root.rglob("*"):
                if entry.is_file() and fnmatch.fnmatch(entry.name.lower(), pat):
                    results.append(entry)
                    if len(results) >= 5: return results
        except (PermissionError, OSError):
            continue
    return results


def _default_boilerplate(target: Path) -> str:
    ext = target.suffix.lower()
    if ext == ".py":
        return "# Python script\n\ndef main():\n    print('Hello!')\n\nif __name__ == '__main__':\n    main()\n"
    if ext == ".html":
        return "<!DOCTYPE html>\n<html>\n<head><title>My Page</title></head>\n<body>\n<h1>Hello!</h1>\n</body>\n</html>\n"
    if ext == ".md":
        return f"# {target.stem}\n\nCreated by Yashi.\n"
    return ""


def _clean_target(target: str) -> str:
    return target.strip().strip('"').strip("'")


def _resolve_target_path(target: str, create_if_missing: bool = True) -> Path:
    cleaned = _clean_target(target)
    explicit = Path(os.path.expandvars(cleaned)).expanduser()
    if explicit.is_absolute() or re.match(r"^[A-Za-z]:[\\/]", cleaned):
        if create_if_missing and not explicit.suffix:
            explicit = explicit.with_suffix(".txt")
        return explicit

    candidates = []
    if "\\" in cleaned or "/" in cleaned:
        explicit_rel = (Path.home() / explicit).resolve()
        if create_if_missing and not explicit_rel.suffix:
            explicit_rel = explicit_rel.with_suffix(".txt")
        candidates.append(explicit_rel)
    else:
        file_name = cleaned if "." in cleaned else f"{cleaned}.txt"
        exact_matches = [
            match for match in _search_files(cleaned)
            if match.name.lower() in {cleaned.lower(), file_name.lower()}
        ]
        if exact_matches:
            return exact_matches[0]
        candidates.extend([
            DEFAULT_CREATE_FALLBACK / file_name,
            DEFAULT_CREATE_DIR / file_name,
        ])

    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0] if candidates else DEFAULT_CREATE_DIR / cleaned


def _create_file(filename: str, content: str = "") -> Path:
    """Create a file on Desktop by default."""
    target = _resolve_target_path(filename, create_if_missing=True)
    target.parent.mkdir(parents=True, exist_ok=True)

    if not content:
        content = _default_boilerplate(target)

    target.write_text(content, encoding="utf-8")
    return target


def _write_file(filename: str, content: str, append: bool = False) -> Path:
    target = _resolve_target_path(filename, create_if_missing=True)
    target.parent.mkdir(parents=True, exist_ok=True)

    if not target.exists() and not append and not content:
        content = _default_boilerplate(target)

    mode = "a" if append else "w"
    with target.open(mode, encoding="utf-8") as handle:
        if append and target.exists() and target.stat().st_size > 0 and content and not content.startswith("\n"):
            handle.write("\n")
        handle.write(content)
    return target


def _extract_write_request(text: str, intent: str, target: str, extra: str) -> tuple[str, str]:
    text_lower = text.lower().strip()
    if intent == "file_append":
        return (extra or target), target
    if text_lower.startswith(("overwrite ", "update ")):
        return target, extra
    return (extra or target), target


class Plugin(YashiPlugin):
    name = "file_ops"
    description = "Create files, write to files, search directories, open folders"
    trigger_phrases = ["create", "make", "write", "append", "find", "search", "open folder", "where is"]

    async def can_handle(self, text: str, intent: Optional[str] = None) -> bool:
        return intent in ("file_create", "file_write", "file_append", "find_file", "open_folder", "search_dir")

    async def execute(self, text: str, context: Dict[str, Any]) -> Dict[str, Any]:
        intent_data = context.get("intent") or {}
        intent = intent_data.get("intent", "")
        target = intent_data.get("target", "").strip()
        extra  = intent_data.get("extra", "").strip()
        tl = text.lower()

        # ── Create file ───────────────────────────────────────────────────────
        if intent == "file_create":
            if not target:
                return {"success": False, "message": "What should I name the file?", "data": None}

            # Make sure it has an extension
            if "." not in target:
                target += ".txt"

            # Extra is content if specified
            content = extra if extra else ""
            # Also check for "with content X" pattern
            m = re.search(r"(?:with|containing|that says|saying)\s+(.+)", text, re.I)
            if m:
                content = m.group(1).strip()

            path = _create_file(target, content)
            _open_path(path)  # Open in default app
            return {
                "success": True,
                "message": f"Created '{path.name}' and opened it.",
                "data": {"path": str(path)}
            }

        if intent in ("file_write", "file_append"):
            file_target, content = _extract_write_request(text, intent, target, extra)
            file_target = _clean_target(file_target)
            content = content.strip().strip('"').strip("'")

            if not file_target:
                return {"success": False, "message": "Which file should I update?", "data": None}
            if not content:
                return {"success": False, "message": "What should I write in the file?", "data": None}

            path = _write_file(file_target, content, append=intent == "file_append")
            _open_path(path)
            action = "Appended to" if intent == "file_append" else "Updated"
            return {
                "success": True,
                "message": f"{action} '{path.name}' and opened it.",
                "data": {"path": str(path), "content": content}
            }

        # ── Find file ─────────────────────────────────────────────────────────
        if intent == "find_file":
            files = _search_files(target)
            if files:
                lines = "\n".join(f"  • {p}" for p in files[:5])
                return {"success": True,
                        "message": f"Found {len(files)} file(s) matching '{target}':\n{lines}",
                        "data": {"files": [str(f) for f in files]}}
            return {"success": True,
                    "message": f"No files found matching '{target}'.",
                    "data": {"files": []}}

        # ── Open folder ───────────────────────────────────────────────────────
        if intent in ("open_folder", "search_dir"):
            dirs = _search_dirs(target)
            if dirs:
                _open_path(dirs[0])
                lines = "\n".join(f"  • {p}" for p in dirs[:4])
                return {"success": True,
                        "message": f"Found {len(dirs)} folder(s) matching '{target}'.\nOpened: {dirs[0].name}\n{lines}",
                        "data": {"folders": [str(d) for d in dirs]}}
            return {"success": True,
                    "message": f"No folders found matching '{target}'.",
                    "data": {"folders": []}}

        return {"success": False, "message": "I couldn't understand that file operation.", "data": None}
