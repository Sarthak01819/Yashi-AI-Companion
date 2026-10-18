"""
App Launcher Plugin — opens apps and controls Spotify including song search.
"""
import re, os, glob, shutil, logging, asyncio, subprocess, urllib.parse, urllib.request, webbrowser, ctypes, json
from typing import Optional, Dict, Any
from plugins.base_plugin import YashiPlugin

logger = logging.getLogger(__name__)

SPOTIFY_PATHS = [
    os.path.expandvars(r"%APPDATA%\Spotify\Spotify.exe"),
    os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WindowsApps\Spotify.exe"),
    r"C:\Program Files\Spotify\Spotify.exe",
    r"C:\Program Files (x86)\Spotify\Spotify.exe",
]

WINDOWS_APPS = {
    "chrome":      [r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
                    os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe")],
    "firefox":     [r"C:\Program Files\Mozilla Firefox\firefox.exe"],
    "edge":        [os.path.expandvars(r"%PROGRAMFILES(X86)%\Microsoft\Edge\Application\msedge.exe")],
    "discord":     [os.path.expandvars(r"%LOCALAPPDATA%\Discord\Update.exe")],
    "steam":       [r"C:\Program Files (x86)\Steam\steam.exe"],
    "vlc":         [r"C:\Program Files\VideoLAN\VLC\vlc.exe"],
    "vscode":      [os.path.expandvars(r"%LOCALAPPDATA%\Programs\Microsoft VS Code\Code.exe")],
    "notepad":     [r"C:\Windows\System32\notepad.exe"],
    "calculator":  [r"C:\Windows\System32\calc.exe"],
    "paint":       [r"C:\Windows\System32\mspaint.exe"],
    "explorer":    [r"C:\Windows\explorer.exe"],
    "cmd":         [r"C:\Windows\System32\cmd.exe"],
    "terminal":    [os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WindowsApps\wt.exe"),
                    r"C:\Windows\System32\cmd.exe"],
}

ALIASES = {
    "browser": "chrome", "google chrome": "chrome", "internet": "chrome",
    "vs code": "vscode", "visual studio code": "vscode",
    "file manager": "explorer", "files": "explorer",
    "music": "spotify", "songs": "spotify",
    "command prompt": "cmd", "task manager": "taskmgr",
}

KNOWN_WEBSITES = {
    "youtube": "https://www.youtube.com",
    "yt": "https://www.youtube.com",
    "google": "https://www.google.com",
    "gmail": "https://mail.google.com",
    "drive": "https://drive.google.com",
    "github": "https://github.com",
    "linkedin": "https://www.linkedin.com",
    "reddit": "https://www.reddit.com",
    "instagram": "https://www.instagram.com",
    "facebook": "https://www.facebook.com",
    "x": "https://x.com",
    "twitter": "https://x.com",
    "chatgpt": "https://chat.openai.com",
    "openai": "https://openai.com",
    "spotify": "https://open.spotify.com",
    "netflix": "https://www.netflix.com",
    "amazon": "https://www.amazon.com",
}

GENERIC_SPOTIFY_TARGETS = {
    "music",
    "any music",
    "some music",
    "random music",
    "songs",
    "song",
    "playlist",
    "playlists",
    "my music",
    "something",
    "anything",
}

SPOTIFY_WEB_TOKEN_URL = "https://open.spotify.com/get_access_token?reason=transport&productType=web_player"
SPOTIFY_WEB_SEARCH_URL = "https://api.spotify.com/v1/search"

_spotify_autoplay_task: Optional[asyncio.Task] = None


def _find_spotify():
    for p in SPOTIFY_PATHS:
        if os.path.isfile(p): return p
    # Glob for versioned paths
    matches = glob.glob(os.path.expandvars(r"%LOCALAPPDATA%\Packages\SpotifyAB*\LocalState\Spotify.exe"))
    return matches[-1] if matches else None


def _focus_window(title_hint: str) -> bool:
    if os.name != "nt":
        return False

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    matches = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    def _enum_proc(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return True
        title = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, title, length + 1)
        if title_hint.lower() in title.value.lower():
            matches.append(hwnd)
        return True

    user32.EnumWindows(_enum_proc, 0)
    if not matches:
        return False

    hwnd = matches[0]
    user32.ShowWindow(hwnd, 9)  # SW_RESTORE
    user32.AllowSetForegroundWindow(kernel32.GetCurrentProcessId())
    return bool(user32.SetForegroundWindow(hwnd))


def _spotify_keyboard_play(song: str, ensure_play: bool = False) -> bool:
    try:
        from pynput.keyboard import Key, Controller
    except ImportError:
        logger.warning("pynput not installed — Spotify autoplay fallback unavailable")
        return False

    import time

    def focus_spotify_window(retries: int = 5, delay: float = 0.22) -> bool:
        for _ in range(retries):
            if _focus_window("Spotify"):
                return True
            time.sleep(delay)
        return False

    if not focus_spotify_window():
        return False

    kb = Controller()

    def tap(key, delay: float = 0.16):
        kb.press(key)
        kb.release(key)
        time.sleep(delay)

    def hotkey(*keys):
        for key in keys:
            kb.press(key)
        time.sleep(0.08)
        for key in reversed(keys):
            kb.release(key)
        time.sleep(0.16)

    def run_pattern_basic() -> None:
        hotkey(Key.ctrl, "l")
        hotkey(Key.ctrl, "a")
        tap(Key.backspace, 0.10)
        kb.type(song)
        tap(Key.enter, 0.62)
        tap(Key.tab, 0.16)
        tap(Key.tab, 0.16)
        tap(Key.enter, 0.24)

    def run_pattern_alt() -> None:
        hotkey(Key.ctrl, "l")
        hotkey(Key.ctrl, "a")
        tap(Key.backspace, 0.10)
        kb.type(song)
        tap(Key.enter, 0.55)
        tap(Key.tab, 0.18)
        tap(Key.enter, 0.22)
        tap(Key.down, 0.16)
        tap(Key.enter, 0.18)

    # Focus search, type the song, and attempt to play top result.
    run_pattern_basic()
    # A second pattern improves compatibility across Spotify UI variants.
    if focus_spotify_window(retries=2, delay=0.12):
        run_pattern_alt()

    # If Spotify was just launched, force playback once after selecting a result.
    if ensure_play:
        tap(Key.media_play_pause, 0.10)
    return True


def _normalise_text_for_match(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9\s]", " ", value.lower())
    return re.sub(r"\s+", " ", cleaned).strip()


def _score_spotify_track_candidate(query: str, item: Dict[str, Any]) -> float:
    query_text = _normalise_text_for_match(query)
    if not query_text:
        return 0.0

    track_name = str(item.get("name") or "")
    artists = " ".join(
        str(a.get("name") or "")
        for a in (item.get("artists") or [])
        if isinstance(a, dict)
    )

    combined = _normalise_text_for_match(f"{track_name} {artists}")
    if not combined:
        return 0.0

    query_tokens = set(query_text.split())
    candidate_tokens = set(combined.split())
    overlap = len(query_tokens & candidate_tokens)

    score = overlap * 2.0
    if query_text in combined:
        score += 4.0
    if _normalise_text_for_match(track_name).startswith(query_text):
        score += 2.0

    popularity = item.get("popularity")
    if isinstance(popularity, int):
        score += popularity / 200.0

    return score


def _fetch_spotify_web_token_sync() -> Optional[str]:
    req = urllib.request.Request(
        SPOTIFY_WEB_TOKEN_URL,
        headers={"User-Agent": "Mozilla/5.0"},
    )

    with urllib.request.urlopen(req, timeout=1.8) as resp:
        payload = json.loads(resp.read().decode("utf-8", errors="ignore"))

    token = payload.get("accessToken")
    return token if isinstance(token, str) and token else None


def _search_spotify_track_uri_sync(query: str) -> Optional[str]:
    token = _fetch_spotify_web_token_sync()
    if not token:
        return None

    qs = urllib.parse.urlencode({
        "q": query,
        "type": "track",
        "limit": 8,
    })
    req = urllib.request.Request(
        f"{SPOTIFY_WEB_SEARCH_URL}?{qs}",
        headers={
            "Authorization": f"Bearer {token}",
            "User-Agent": "Mozilla/5.0",
        },
    )

    with urllib.request.urlopen(req, timeout=1.8) as resp:
        payload = json.loads(resp.read().decode("utf-8", errors="ignore"))

    items = (((payload or {}).get("tracks") or {}).get("items") or [])
    if not items:
        return None

    best_uri: Optional[str] = None
    best_score = float("-inf")

    for item in items:
        if not isinstance(item, dict):
            continue
        uri = item.get("uri")
        if not (isinstance(uri, str) and uri.startswith("spotify:")):
            continue

        score = _score_spotify_track_candidate(query, item)
        if score > best_score:
            best_score = score
            best_uri = uri

    return best_uri


async def _search_spotify_track_uri(query: str) -> Optional[str]:
    try:
        return await asyncio.to_thread(_search_spotify_track_uri_sync, query)
    except Exception as e:
        logger.debug("Spotify web search fallback unavailable: %s", e)
        return None


def _open_spotify_uri(uri: str) -> bool:
    try:
        subprocess.Popen(f'start "" "{uri}"', shell=True)
        return True
    except Exception as e:
        logger.debug("Failed to open Spotify URI '%s': %s", uri, e)
        return False


def _known_app_paths(name: str) -> list:
    """Configured paths for an app name (after alias resolution), fuzzy-matched."""
    paths = WINDOWS_APPS.get(name, [])
    if not paths:
        for key, value in WINDOWS_APPS.items():
            if name in key or key in name:
                return value
    return paths


def _can_launch(name: str) -> bool:
    """
    True only when we can actually open this target. Keeps ordinary sentences
    ("start over", "open up to me") from being swallowed by the launcher.
    """
    name = ALIASES.get(name.lower().strip(), name.lower().strip())
    if not name:
        return False
    if name == "spotify":
        return True
    if name in KNOWN_WEBSITES:
        return True
    if any(os.path.isfile(p) for p in _known_app_paths(name)):
        return True
    if " " not in name and shutil.which(name):
        return True
    return False


def _launch(name: str) -> bool:
    name = ALIASES.get(name.lower(), name.lower())
    if name == "spotify":
        p = _find_spotify()
        if p:
            try:
                subprocess.Popen([p], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return True
            except Exception: pass
        # Windows URI fallback
        try:
            subprocess.Popen("start spotify:", shell=True)
            return True
        except Exception: pass
        return False

    for p in _known_app_paths(name):
        try:
            subprocess.Popen([p], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            logger.info("Launched: %s", p)
            return True
        except (FileNotFoundError, Exception):
            continue

    # A website we know by name.
    if name in KNOWN_WEBSITES:
        webbrowser.open(KNOWN_WEBSITES[name])
        return True

    # Last resort: only for a real executable on PATH — never a blind
    # `start "<anything>"`, which "succeeds" for text that isn't an app at all.
    exe = shutil.which(name) if " " not in name else None
    if exe:
        try:
            subprocess.Popen([exe], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        except Exception:
            return False
    return False


def _resolve_site_url(site: str) -> Optional[str]:
    """Convert user-spoken website target to an absolute URL."""
    raw = site.strip().strip(".,!?;: ")
    raw = re.sub(r"^the\s+", "", raw, flags=re.IGNORECASE)
    if not raw:
        return None

    key = raw.lower()
    if key in KNOWN_WEBSITES:
        return KNOWN_WEBSITES[key]

    if key.startswith(("http://", "https://")):
        return raw

    key = key.replace(" dot ", ".")

    if re.fullmatch(r"[a-z0-9][a-z0-9.-]*\.[a-z]{2,}", key):
        return f"https://{key}"

    if " " not in key and re.fullmatch(r"[a-z0-9-]{2,63}", key):
        return f"https://www.{key}.com"

    return None


def _normalise_phrase(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9\s]", " ", value.lower())
    return re.sub(r"\s+", " ", cleaned).strip()


def _is_generic_spotify_target(target: str) -> bool:
    phrase = _normalise_phrase(target)
    if not phrase:
        return False
    if phrase in GENERIC_SPOTIFY_TARGETS:
        return True

    return bool(
        re.fullmatch(
            r"(?:any|some|random|something|anything|my)?\s*(?:music|song|songs|playlist|playlists|tracks?)",
            phrase,
        )
    )


def _queue_spotify_autoplay(song: str, launched: bool) -> None:
    global _spotify_autoplay_task

    if _spotify_autoplay_task is not None and not _spotify_autoplay_task.done():
        _spotify_autoplay_task.cancel()

    async def _runner():
        try:
            await asyncio.sleep(0.45 if launched else 0.75)

            # First try direct track URI for quick and accurate song targeting.
            track_uri = await _search_spotify_track_uri(song)
            if track_uri and _open_spotify_uri(track_uri):
                return

            # Fallback workflow: search, select, then play inside Spotify desktop UI.
            search_uri = f"spotify:search:{urllib.parse.quote(song)}"
            _open_spotify_uri(search_uri)
            await asyncio.sleep(0.35)
            await asyncio.to_thread(_spotify_keyboard_play, song, launched)
        except asyncio.CancelledError:
            logger.debug("Cancelled previous Spotify autoplay task")
            return
        except Exception as e:
            logger.debug("Spotify autoplay background error: %s", e)

    _spotify_autoplay_task = asyncio.create_task(_runner())


async def _media_key(action: str) -> bool:
    m_vk = {
        "play_pause": 0xB3,
        "next": 0xB0,
        "previous": 0xB1,
    }

    # Fast path via pynput when available.
    try:
        from pynput.keyboard import Key, Controller
        kb = Controller()
        m = {"play_pause": Key.media_play_pause,
             "next": Key.media_next, "previous": Key.media_previous}
        k = m.get(action)
        if k:
            kb.press(k); kb.release(k)
            return True
    except ImportError:
        logger.info("pynput not installed — using Windows media key fallback")
    except Exception as e:
        logger.warning("Media key error: %s", e)

    # Reliable Windows fallback that does not require extra packages.
    if os.name == "nt":
        vk = m_vk.get(action)
        if not vk:
            return False
        try:
            KEYEVENTF_KEYUP = 0x0002
            user32 = ctypes.windll.user32
            user32.keybd_event(vk, 0, 0, 0)
            user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)
            return True
        except Exception as e:
            logger.warning("Windows media key fallback error: %s", e)

    return False


class Plugin(YashiPlugin):
    name = "app_launcher"
    description = "Opens apps and controls Spotify including song search"
    trigger_phrases = ["open", "launch", "start", "play", "pause", "next", "search", "spotify", "youtube", "website", "browser"]

    async def can_handle(self, text: str, intent: Optional[str] = None) -> bool:
        if intent in ("app_control", "open_url", "spotify_search",
                      "youtube_search", "open_website"):
            return True
        if intent == "open_app":
            # Only claim the message if the target is really an app we can open;
            # otherwise it belongs to the conversation, not the launcher.
            from plugins.intent_detector import detect_intent
            data = detect_intent(text) or {}
            return _can_launch(data.get("target", ""))
        return False

    async def execute(self, text: str, context: Dict[str, Any]) -> Dict[str, Any]:
        intent_data = context.get("intent") or {}
        intent = intent_data.get("intent", "")
        target = intent_data.get("target", "").strip()
        tl = text.lower()

        # ── Spotify: search/play specific song ───────────────────────────────
        if intent == "spotify_search" and target:
            song = target
            try:
                launched = _launch("spotify")

                # Fast-path for generic requests like "play any music on spotify".
                if _is_generic_spotify_target(song):
                    if launched:
                        await asyncio.sleep(0.25)
                    played = await _media_key("play_pause")
                    return {
                        "success": True,
                        "message": (
                            "Opening Spotify and playing music."
                            if launched and played
                            else "Playing music on Spotify."
                            if played
                            else "Opened Spotify. If playback is paused, press play once."
                        ),
                        "data": {"launched": launched, "generic": True, "played": played},
                    }

                _queue_spotify_autoplay(song, launched)
                return {"success": True,
                    "message": f"Opening Spotify, finding '{song}', and starting playback.",
                    "data": {"song": song, "launched": launched, "workflow_queued": True}}
            except Exception:
                # Fallback: open in browser
                url = f"https://open.spotify.com/search/{urllib.parse.quote(song)}"
                webbrowser.open(url)
                return {"success": True,
                        "message": f"Opening Spotify search for '{song}' in browser.",
                        "data": {"song": song}}

        # ── YouTube: open + search query in default browser ──────────────────
        if intent == "youtube_search":
            query = target.strip()
            if not query:
                return {
                    "success": False,
                    "message": "Tell me what to search on YouTube.",
                    "data": None,
                }

            url = "https://www.youtube.com/results?search_query=" + urllib.parse.quote_plus(query)
            webbrowser.open(url)
            return {
                "success": True,
                "message": f"Opening YouTube and searching for '{query}'.",
                "data": {"query": query, "url": url},
            }

        # ── Open any requested website in default browser ───────────────────
        if intent == "open_website":
            site = target.strip()
            if not site:
                return {
                    "success": False,
                    "message": "Tell me which website to open.",
                    "data": None,
                }

            url = _resolve_site_url(site)
            if url:
                webbrowser.open(url)
                return {
                    "success": True,
                    "message": f"Opening {site} in your browser.",
                    "data": {"site": site, "url": url},
                }

            # Fallback: search the website name and open likely official site result page.
            query_url = "https://www.google.com/search?q=" + urllib.parse.quote_plus(f"{site} official website")
            webbrowser.open(query_url)
            return {
                "success": True,
                "message": f"Searching for {site} in your browser.",
                "data": {"site": site, "url": query_url},
            }

        # ── Web search ────────────────────────────────────────────────────────
        if intent == "open_url":
            query = target or re.sub(r"(search|google|look up|find)(\s+for)?", "", tl).strip()
            if query:
                url = "https://www.google.com/search?q=" + urllib.parse.quote_plus(query)
                webbrowser.open(url)
                return {"success": True, "message": f"Searching Google for '{query}'.", "data": {}}

        # ── Spotify media controls ────────────────────────────────────────────
        if intent == "app_control" or "spotify" in tl:
            if any(w in tl for w in ["pause", "stop"]):
                ok = await _media_key("play_pause")
                return {
                    "success": True,
                    "message": "Paused the music." if ok else "I couldn't send the pause key right now.",
                    "data": {"ok": ok},
                }
            if any(w in tl for w in ["next", "skip"]):
                ok = await _media_key("next")
                return {
                    "success": True,
                    "message": "Skipped to next track." if ok else "I couldn't send the next-track key right now.",
                    "data": {"ok": ok},
                }
            if any(w in tl for w in ["previous", "back", "last"]):
                ok = await _media_key("previous")
                return {
                    "success": True,
                    "message": "Went back to previous track." if ok else "I couldn't send the previous-track key right now.",
                    "data": {"ok": ok},
                }
            if "resume" in tl or ("play" in tl and "spotify" in tl and not target):
                ok = _launch("spotify")
                if ok:
                    await asyncio.sleep(0.25)
                await _media_key("play_pause")
                msg = "Opening Spotify and resuming playback!" if ok else "Resuming Spotify playback."
                return {"success": True, "message": msg, "data": {}}

        # ── Generic app open ──────────────────────────────────────────────────
        app = target or re.sub(r"(open|launch|start)\s+", "", tl).strip()
        if not app:
            return {"success": False, "message": "Which app should I open?", "data": None}

        ok = _launch(app)
        return ({"success": True, "message": f"Opening {app}!", "data": {"app": app}}
                if ok else
                {"success": False, "message": f"Couldn't find '{app}'. Is it installed?", "data": None})
