"""Finding, opening and writing files in the user's own folders."""
import fnmatch
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import List

HOME = Path.home()
SEARCH_ROOTS = [HOME / "Desktop", HOME / "Documents", HOME / "Downloads", HOME / "Pictures",
                HOME / "Music", HOME / "Videos", HOME]
NEW_FILES_DIR = HOME / "Documents"
_SKIP = {"AppData", "node_modules", ".git", "site-packages", "__pycache__", ".venv", "venv"}
LIMIT = 5


def _walk(predicate) -> List[Path]:
    found: List[Path] = []
    seen = set()
    for root in SEARCH_ROOTS:
        if not root.exists():
            continue
        for folder, dirs, files in os.walk(root):
            dirs[:] = [d for d in dirs if d not in _SKIP and not d.startswith(".")]
            if root == HOME and Path(folder) == HOME:
                # The other roots are searched on their own.
                dirs[:] = [d for d in dirs if HOME / d not in SEARCH_ROOTS]
            for name in dirs + files:
                path = Path(folder) / name
                if path not in seen and predicate(path):
                    seen.add(path)
                    found.append(path)
                    if len(found) >= LIMIT:
                        return found
    return found


def search_files(name: str) -> List[Path]:
    pattern = f"*{name.lower().strip()}*"
    return _walk(lambda p: p.is_file() and fnmatch.fnmatch(p.name.lower(), pattern))


def search_dirs(name: str) -> List[Path]:
    wanted = name.lower().strip()
    exact = HOME / name.strip().title()
    if exact.is_dir():                                    # "downloads", "documents"...
        return [exact]
    return _walk(lambda p: p.is_dir() and wanted in p.name.lower())


def open_path(path: Path) -> bool:
    try:
        if sys.platform == "win32":
            os.startfile(str(path))
        else:
            subprocess.Popen(["xdg-open", str(path)])
        return True
    except OSError:
        return False


def target_for(name: str) -> Path:
    """Where a named file lives (or would be created): explicit path, an existing
    file with that exact name, else Documents. No extension means .txt."""
    cleaned = name.strip().strip("\"'")
    path = Path(os.path.expandvars(cleaned)).expanduser()
    if not path.suffix:
        path = path.with_suffix(".txt")
    if path.is_absolute() or re.match(r"^[A-Za-z]:[\\/]", cleaned):
        return path
    if "/" in cleaned or "\\" in cleaned:
        return HOME / path
    existing = [p for p in search_files(path.name) if p.name.lower() == path.name.lower()]
    return existing[0] if existing else NEW_FILES_DIR / path.name


def write_text(path: Path, content: str, append: bool = False) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a" if append else "w", encoding="utf-8") as handle:
        if append and path.exists() and path.stat().st_size and not content.startswith("\n"):
            handle.write("\n")
        handle.write(content)
    return path
