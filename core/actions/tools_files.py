"""Files and folders in the user's own folders (Desktop, Documents, Downloads...)."""
import asyncio

from core.actions import files
from core.actions.registry import Result, tool


@tool("open_file", "Find a file by name in the user's folders and open it.", {"name": "file name or part of it"})
async def open_file(name: str) -> Result:
    matches = await asyncio.to_thread(files.search_files, name)
    if not matches:
        return Result(False, f"I couldn't find a file called {name}.")
    ok = files.open_path(matches[0])
    return Result(ok, f"Opening {matches[0].name}.")


@tool("find_file", "Find where a file is, without opening it.", {"name": "file name or part of it"})
async def find_file(name: str) -> Result:
    matches = await asyncio.to_thread(files.search_files, name)
    if not matches:
        return Result(False, f"No file called {name} in your usual folders.")
    return Result(True, f"Found {matches[0].name} in {matches[0].parent}"
                        + (f", and {len(matches) - 1} more." if len(matches) > 1 else "."),
                  [str(p) for p in matches])


@tool("open_folder", "Open a folder in File Explorer (e.g. Downloads, Documents, a project folder).",
      {"name": "folder name"})
async def open_folder(name: str) -> Result:
    matches = await asyncio.to_thread(files.search_dirs, name)
    if not matches:
        return Result(False, f"I couldn't find a folder called {name}.")
    ok = files.open_path(matches[0])
    return Result(ok, f"Opening {matches[0].name}.")


@tool("write_file", "Create a text file (in Documents unless a path is given), or add to one.",
      {"name": "file name, e.g. notes.txt", "?content": "text to write", "?append": "true to add to the end"})
async def write_file(name: str, content: str = "", append: bool = False) -> Result:
    target = await asyncio.to_thread(files.target_for, name)
    if target.exists() and not append:
        return Result(False, f"{target.name} already exists. Want me to add to it instead?")   # never overwrite
    try:
        await asyncio.to_thread(files.write_text, target, content, append)
    except OSError as error:
        return Result(False, f"I couldn't write that file: {error.strerror or error}.")
    return Result(True, f"{'Added to' if append else 'Saved'} {target.name} in {target.parent.name}.")
