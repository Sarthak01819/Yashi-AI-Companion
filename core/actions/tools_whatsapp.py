"""
WhatsApp Web in Yashi's browser. First use: scan the QR code shown there
(WhatsApp > Linked devices); the profile stays logged in afterwards.

Sending is two-step. `prepare` searches for the contact and reads back the
exact chat name it found; the agent asks "Send ... to <name>?" and only
then `whatsapp_send` opens that chat, checks the header says that name, and
sends.
"""
import difflib
import re

from core.actions import browser
from core.actions.registry import Result, tool

HOST = "web.whatsapp.com"
URL = "https://web.whatsapp.com/"

SEARCH_BOX = "#side div[contenteditable='true']"
CHAT_TITLES = "#pane-side span[title]"
MESSAGE_BOX = "#main footer div[contenteditable='true']"
HEADER_TITLE = "#main header span[dir='auto']"

NOT_LOGGED_IN = ("WhatsApp isn't linked in my browser yet. I've opened it: scan the QR code with your "
                 "phone (WhatsApp, Settings, Linked devices), then ask me again.")


def _ready(page, timeout=25000) -> bool:
    """True once the chat list shows; False if WhatsApp wants a QR scan."""
    page.wait_for_selector("#pane-side, canvas, [data-ref]", timeout=timeout)
    if page.query_selector("#pane-side"):
        return True
    try:
        page.wait_for_selector("#pane-side", timeout=4000)       # still syncing
        return True
    except Exception:
        return False


def _search(page, name: str) -> list:
    box = page.wait_for_selector(SEARCH_BOX, timeout=10000)
    box.click()
    page.keyboard.press("Control+A")
    page.keyboard.press("Backspace")
    page.keyboard.type(name, delay=25)
    page.wait_for_timeout(1500)
    titles = []
    for el in page.query_selector_all(CHAT_TITLES):
        title = (el.get_attribute("title") or "").strip()
        if title and title not in titles and el.is_visible():
            titles.append(title)
    return titles


def _norm(text: str) -> str:
    return re.sub(r"[^\w ]", "", text.lower()).strip()


def pick_contact(wanted: str, titles: list):
    """(best title, other close titles). Exact beats prefix beats contains beats fuzzy."""
    w = _norm(wanted)
    by_norm = {_norm(t): t for t in titles}
    if w in by_norm:
        return by_norm[w], []
    starts = [t for n, t in by_norm.items() if n.startswith(w) or n.split(" ")[0] == w]
    if starts:
        return starts[0], starts[1:3]
    contains = [t for n, t in by_norm.items() if w in n]
    if contains:
        return contains[0], contains[1:3]
    close = difflib.get_close_matches(w, list(by_norm), n=3, cutoff=0.6)
    if close:
        return by_norm[close[0]], [by_norm[c] for c in close[1:]]
    return None, []


def _find_chat(pages, contact: str, open_it: bool = False) -> dict:
    """Runs on the browser thread. {"status": "login"} or {"status": "ok", "best", "others"}."""
    page = pages.tab(HOST, URL)
    if not _ready(page):
        page.bring_to_front()
        return {"status": "login"}
    best, others = pick_contact(contact, _search(page, contact))
    if best and open_it:
        page.click(f"{CHAT_TITLES}[title={_css_string(best)}]")
    return {"status": "ok", "best": best, "others": others}


async def _lookup(contact: str, open_it: bool = False):
    """(found dict, None) or (None, failed Result)."""
    try:
        found = await browser.run(lambda pages: _find_chat(pages, contact, open_it))
    except browser.BrowserUnavailable as error:
        return None, Result(False, f"I can't open my browser: {error}.")
    except Exception:
        return None, Result(False, "WhatsApp Web didn't load. Is the internet okay?")
    if found["status"] == "login":
        return None, Result(False, NOT_LOGGED_IN)
    if not found["best"]:
        return None, Result(False, f"I couldn't find anyone called {contact} on WhatsApp.")
    return found, None


async def _prepare_send(contact: str, message: str):
    if not message.strip():
        return Result(False, "What should the message say?")
    found, failed = await _lookup(contact)
    if failed:
        return failed
    if found["others"]:
        options = ", ".join([found["best"]] + found["others"])
        return Result(False, f"I found a few: {options}. Which one did you mean?")
    best = found["best"]
    return f'Send "{message}" to {best} on WhatsApp?', {"contact": best, "message": message}


@tool("whatsapp_send", "Send a WhatsApp message to a contact or group.",
      {"contact": "name as saved in WhatsApp", "message": "the message text"},
      confirm=True, prepare=_prepare_send)
async def whatsapp_send(contact: str, message: str) -> Result:
    def work(pages):
        page = pages.tab(HOST, URL)
        if not _ready(page):
            return "login"
        titles = _search(page, contact)
        if contact not in titles:
            return "missing"
        page.click(f"{CHAT_TITLES}[title={_css_string(contact)}]")
        page.wait_for_selector(MESSAGE_BOX, timeout=10000)
        header = (page.inner_text(HEADER_TITLE) or "").strip()
        if _norm(header) != _norm(contact):
            return f"header:{header}"                     # wrong chat opened: never send
        page.click(MESSAGE_BOX)
        lines = message.split("\n")
        for i, line in enumerate(lines):
            page.keyboard.type(line, delay=10)
            if i < len(lines) - 1:
                page.keyboard.press("Shift+Enter")
        page.keyboard.press("Enter")
        page.wait_for_timeout(1200)
        return "sent"

    try:
        outcome = await browser.run(work)
    except browser.BrowserUnavailable as error:
        return Result(False, f"I can't open my browser: {error}.")
    except Exception:
        return Result(False, "WhatsApp got stuck, so I didn't send anything. Want me to try again?")
    if outcome == "sent":
        return Result(True, f"Sent to {contact}.")
    if outcome == "login":
        return Result(False, NOT_LOGGED_IN)
    if outcome == "missing":
        return Result(False, f"I couldn't find {contact} anymore, so I didn't send it.")
    return Result(False, f"A different chat opened ({outcome[7:]}), so I didn't send it.")


@tool("whatsapp_open_chat", "Open someone's WhatsApp chat without sending anything.",
      {"contact": "name as saved in WhatsApp"})
async def whatsapp_open_chat(contact: str) -> Result:
    found, failed = await _lookup(contact, open_it=True)
    return failed or Result(True, f"Opened your chat with {found['best']}.")


def _css_string(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'
