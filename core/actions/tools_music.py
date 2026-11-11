"""
YouTube Music in Yashi's browser.

Finding what to play uses YouTube Music's own search endpoint (no key, no
login). Playback is a navigation to a watch URL with a queue (a song plus its
radio, or the playlist/album/artist mix), so music keeps going afterwards.
Controls go through the page's player object, which is the same API the
on-page buttons use.
"""
import json
import re

import httpx

from core.actions import browser
from core.actions.registry import Result, tool

HOST = "music.youtube.com"
HOME = "https://music.youtube.com/"
SEARCH_URL = "https://music.youtube.com/youtubei/v1/search?prettyPrint=false"
CLIENT = {"client": {"clientName": "WEB_REMIX", "clientVersion": "1.20241023.01.00", "hl": "en", "gl": "IN"}}
# Search filters, as the YouTube Music web app sends them.
FILTERS = {
    "song": "EgWKAQIIAWoMEA4QChADEAQQCRAF",
    "album": "EgWKAQIYAWoMEA4QChADEAQQCRAF",
    "artist": "EgWKAQIgAWoMEA4QChADEAQQCRAF",
    "playlist": "EgeKAQQoAEABagwQDhAKEAMQBBAJEAU=",
}


def _unescape(text: str) -> str:
    try:
        return json.loads(f'"{text}"')
    except ValueError:
        return text


async def find_music(query: str, kind: str = "song"):
    """(watch_url, title) for the best match, or (None, None)."""
    kind = kind if kind in FILTERS else "song"
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.post(SEARCH_URL, json={"context": CLIENT, "query": query, "params": FILTERS[kind]},
                                     headers={"Origin": "https://music.youtube.com", "User-Agent": "Mozilla/5.0"})
    text = response.text
    title = re.search(r'"musicResponsiveListItemFlexColumnRenderer":\{"text":\{"runs":\[\{"text":"(.*?)"', text)
    title = _unescape(title.group(1)) if title else query
    if kind == "song":
        video = re.search(r'"videoId":"([\w-]{11})"', text)
        if not video:
            return None, None
        # The song, then its radio, so the music doesn't stop after one track.
        return f"{HOME}watch?v={video.group(1)}&list=RDAMVM{video.group(1)}", title
    wanted = {"playlist": r"(?:PL|VL|RD|OL)[\w-]+", "album": r"OLAK5uy_[\w-]+", "artist": r"RDEM[\w-]+"}[kind]
    playlist = re.search(r'"playlistId":"(' + wanted + ')"', text)
    if not playlist:
        return None, None
    return f"{HOME}watch?list={playlist.group(1)}", title


# Runs in the page. `movie_player` is YouTube's player element; the buttons
# are YouTube Music's player bar.
PLAYER_JS = """([action, arg]) => {
  const p = document.getElementById('movie_player');
  const click = (sel) => { const el = document.querySelector(sel); if (el) { el.click(); return true; } return false; };
  const video = document.querySelector('video');
  const slider = document.querySelector('ytmusic-player-bar #volume-slider');
  const info = () => {
    const d = p && p.getVideoData ? p.getVideoData() : {};
    return {title: d.title || '', artist: d.author || '', playing: !!video && !video.paused,
            volume: slider ? Number(slider.value) : (p && p.getVolume ? p.getVolume() : null)};
  };
  const setVolume = (level) => {
    level = Math.max(0, Math.min(100, Math.round(level)));
    if (slider) {                       // YouTube Music's own slider keeps its state in sync
      slider.value = level;
      slider.dispatchEvent(new Event('change', {bubbles: true}));
      slider.dispatchEvent(new Event('immediate-value-change', {bubbles: true}));
    }
    if (p.setVolume) p.setVolume(level);
    if (p.isMuted && p.isMuted()) p.unMute();
  };
  if (!p) return {error: 'no player'};
  switch (action) {
    case 'pause': p.pauseVideo(); break;
    case 'resume': p.playVideo(); break;
    case 'toggle': video && video.paused ? p.playVideo() : p.pauseVideo(); break;
    case 'next': if (!click('ytmusic-player-bar .next-button')) p.nextVideo(); break;
    case 'previous': if (!click('ytmusic-player-bar .previous-button')) p.previousVideo(); break;
    case 'shuffle': click('ytmusic-player-bar .shuffle'); break;
    case 'repeat': click('ytmusic-player-bar .repeat'); break;
    case 'like': click('ytmusic-player-bar #like-button-renderer #button-shape-like button')
                 || click('ytmusic-player-bar ytmusic-like-button-renderer .like'); break;
    case 'dislike': click('ytmusic-player-bar #like-button-renderer #button-shape-dislike button')
                    || click('ytmusic-player-bar ytmusic-like-button-renderer .dislike'); break;
    case 'volume': setVolume(arg); break;
    case 'info': break;
    default: return {error: 'unknown action'};
  }
  return info();
}"""


def is_playing_here() -> bool:
    """YouTube Music is open in Yashi's browser (checked without starting it)."""
    return browser.is_open(HOST)


async def _player(action: str, arg=None):
    if not is_playing_here():
        return {"error": "not open"}

    def work(pages):
        page = pages.find(HOST)
        if page is None:
            return {"error": "not open"}
        return page.evaluate(PLAYER_JS, [action, arg])
    try:
        return await browser.run(lambda pages: work(pages))
    except browser.BrowserUnavailable as error:
        return {"error": str(error)}


def _now(info: dict) -> str:
    if not info.get("title"):
        return "nothing yet"
    return f"{info['title']} by {info['artist']}" if info.get("artist") else info["title"]


@tool("music_play", "Play music on YouTube Music: a song, playlist, album or an artist's mix.",
      {"query": "song / playlist / album / artist name", "?kind": "song | playlist | album | artist (default song)"})
async def music_play(query: str, kind: str = "song") -> Result:
    try:
        url, title = await find_music(query, kind)
    except Exception:
        url, title = None, None
    if not url:
        return Result(False, f"I couldn't find {query} on YouTube Music.")

    def work(pages):
        # A playing tab asks "Leave site?" when navigated away from, so start
        # the new queue in a fresh tab and close the old one without asking.
        old = pages.find(HOST)
        page = pages.context.new_page()
        page.goto(url, wait_until="domcontentloaded")
        page.bring_to_front()
        if old is not None:
            old.close(run_before_unload=False)
        page.wait_for_selector("#movie_player", timeout=15000)
        # Some sessions open paused; nudge it.
        page.wait_for_timeout(1500)
        page.evaluate("() => { const v = document.querySelector('video'); const p = document.getElementById('movie_player');"
                      " if (p && (!v || v.paused)) p.playVideo(); }")
        return True

    try:
        await browser.run(work)
    except browser.BrowserUnavailable as error:
        return Result(False, f"I can't open my browser: {error}.")
    except Exception:
        return Result(False, "YouTube Music didn't load properly. Try again in a sec?")
    label = {"song": "", "playlist": " playlist", "album": " album", "artist": " mix"}.get(kind, "")
    return Result(True, f"Playing {title}{label}.")


@tool("music_control", "Control YouTube Music that is already playing.",
      {"action": "pause | resume | next | previous | shuffle | repeat | like | dislike"})
async def music_control(action: str) -> Result:
    info = await _player(action)
    if "error" in info:
        return Result(False, "YouTube Music isn't open. Ask me to play something first.")
    replies = {"pause": "Paused.", "resume": "Back on.", "next": "Skipping.", "previous": "Going back.",
               "shuffle": "Toggled shuffle.", "repeat": "Changed repeat.", "like": "Liked it.",
               "dislike": "Okay, disliked it."}
    return Result(True, replies.get(action, "Done."))


@tool("music_volume", "YouTube Music volume (not the system volume).",
      {"?level": "0-100", "?change": "up | down"})
async def music_volume(level: int = None, change: str = None) -> Result:
    info = await _player("info")
    if "error" in info:
        return Result(False, "YouTube Music isn't open.")
    current = info.get("volume") or 50
    target = int(level) if level is not None else current + (15 if change == "up" else -15)
    info = await _player("volume", max(0, min(100, target)))
    return Result(True, f"Music volume at {info.get('volume', target)}.")


@tool("music_now_playing", "Say what's playing on YouTube Music.")
async def music_now_playing() -> Result:
    info = await _player("info")
    if "error" in info:
        return Result(False, "Nothing's playing on YouTube Music right now.")
    return Result(True, f"It's {_now(info)}.")
