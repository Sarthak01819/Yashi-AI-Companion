"""Websites, web search and YouTube, in the user's default browser."""
import json
import os
import re
import urllib.parse
import webbrowser

import httpx

from core.actions.registry import Result, tool

SITES = {
    "youtube": "https://www.youtube.com", "yt": "https://www.youtube.com",
    "youtube music": "https://music.youtube.com", "google": "https://www.google.com",
    "gmail": "https://mail.google.com", "google drive": "https://drive.google.com",
    "drive": "https://drive.google.com", "google maps": "https://maps.google.com",
    "maps": "https://maps.google.com", "calendar": "https://calendar.google.com",
    "github": "https://github.com", "linkedin": "https://www.linkedin.com",
    "reddit": "https://www.reddit.com", "instagram": "https://www.instagram.com",
    "facebook": "https://www.facebook.com", "x": "https://x.com", "twitter": "https://x.com",
    "chatgpt": "https://chatgpt.com", "claude": "https://claude.ai", "netflix": "https://www.netflix.com",
    "amazon": "https://www.amazon.in", "flipkart": "https://www.flipkart.com",
    "wikipedia": "https://en.wikipedia.org", "stack overflow": "https://stackoverflow.com",
    "whatsapp web": "https://web.whatsapp.com", "hotstar": "https://www.hotstar.com",
    "prime video": "https://www.primevideo.com", "spotify": "https://open.spotify.com",
    "pinterest": "https://www.pinterest.com", "twitch": "https://www.twitch.tv",
    "imdb": "https://www.imdb.com", "myntra": "https://www.myntra.com", "zomato": "https://www.zomato.com",
    "swiggy": "https://www.swiggy.com",
}

# {q} is the URL-encoded query.
SEARCH = {
    "google": "https://www.google.com/search?q={q}",
    "youtube": "https://www.youtube.com/results?search_query={q}",
    "youtube music": "https://music.youtube.com/search?q={q}",
    "amazon": "https://www.amazon.in/s?k={q}", "flipkart": "https://www.flipkart.com/search?q={q}",
    "myntra": "https://www.myntra.com/{q}",
    "github": "https://github.com/search?q={q}", "reddit": "https://www.reddit.com/search/?q={q}",
    "wikipedia": "https://en.wikipedia.org/w/index.php?search={q}",
    "stack overflow": "https://stackoverflow.com/search?q={q}",
    "google maps": "https://www.google.com/maps/search/{q}", "maps": "https://www.google.com/maps/search/{q}",
    "images": "https://www.google.com/search?tbm=isch&q={q}",
    "news": "https://news.google.com/search?q={q}",
    "x": "https://x.com/search?q={q}", "twitter": "https://x.com/search?q={q}",
    "linkedin": "https://www.linkedin.com/search/results/all/?keywords={q}",
    "instagram": "https://www.instagram.com/explore/search/keyword/?q={q}",
    "pinterest": "https://www.pinterest.com/search/pins/?q={q}",
    "imdb": "https://www.imdb.com/find/?q={q}", "netflix": "https://www.netflix.com/search?q={q}",
    "spotify": "https://open.spotify.com/search/{q}", "twitch": "https://www.twitch.tv/search?term={q}",
    "zomato": "https://www.zomato.com/search?q={q}", "duckduckgo": "https://duckduckgo.com/?q={q}",
    "bing": "https://www.bing.com/search?q={q}", "chatgpt": "https://chatgpt.com/?q={q}",
}

_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/131.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9"}


def open_in_browser(url: str) -> bool:
    try:
        if os.name == "nt":
            os.startfile(url)                 # the user's default browser
        else:
            webbrowser.open(url)
        return True
    except Exception:
        return False


def site_key(site: str) -> str:
    key = re.sub(r"^(?:the\s+)?|\s*(?:website|site|app)$|\.com$|\.in$", "", site.strip().lower())
    return {"you tube": "youtube", "stackoverflow": "stack overflow", "yt music": "youtube music",
            "ytmusic": "youtube music", "twitter x": "x"}.get(key, key)


def resolve_url(target: str):
    raw = target.strip().strip(".,!?")
    if re.match(r"^https?://", raw, re.I):
        return raw
    key = site_key(raw)
    if key in SITES:
        return SITES[key]
    domain = raw.lower().replace(" dot ", ".").replace(" ", "")
    if re.fullmatch(r"[a-z0-9-]+(\.[a-z0-9-]+)*\.[a-z]{2,}(/\S*)?", domain):
        return "https://" + domain
    return None


@tool("open_website", "Open a website in the default browser (a known name like 'gmail' or a domain/URL).",
      {"site": "site name, domain or URL"})
async def open_website(site: str) -> Result:
    url = resolve_url(site)
    if not url:
        # Unknown name: let the search engine's top result decide.
        url = "https://duckduckgo.com/?q=!ducky+" + urllib.parse.quote(site)
    ok = open_in_browser(url)
    return Result(ok, f"Opening {site}." if ok else "The browser didn't open.")


@tool("web_search", "Search the web (Google) in the default browser.", {"query": "what to search"})
async def web_search(query: str) -> Result:
    ok = open_in_browser(SEARCH["google"].format(q=urllib.parse.quote_plus(query)))
    return Result(ok, f"Searching for {query}.")


@tool("search_site", "Search inside a specific site, e.g. Amazon, Flipkart, YouTube, GitHub, Reddit, "
      "Wikipedia, Maps, Netflix, Instagram, LinkedIn, X, IMDb, any other site.",
      {"site": "site name", "query": "what to search"})
async def search_site(site: str, query: str) -> Result:
    key = site_key(site)
    q = urllib.parse.quote_plus(query)
    if key in SEARCH:
        url = SEARCH[key].format(q=q)
    else:
        # Any other site: Google, restricted to that domain.
        domain = urllib.parse.urlparse(resolve_url(site) or "").netloc or site
        url = SEARCH["google"].format(q=urllib.parse.quote_plus(f"site:{domain} {query}"))
    ok = open_in_browser(url)
    return Result(ok, f"Searching {site} for {query}.")


async def first_youtube_video(query: str):
    """(video_id, title) of the top YouTube search result, without an API key."""
    url = SEARCH["youtube"].format(q=urllib.parse.quote_plus(query))
    async with httpx.AsyncClient(headers=_HEADERS, timeout=10, follow_redirects=True) as client:
        html = (await client.get(url, cookies={"CONSENT": "YES+1"})).text
    match = re.search(r'"videoRenderer":\{"videoId":"([\w-]{11})".{0,600}?"title":\{"runs":\[\{"text":"(.*?)"\}', html)
    if match:
        try:
            title = json.loads(f'"{match.group(2)}"')         # JSON escapes, incl. non-English titles
        except ValueError:
            title = query
        return match.group(1), title
    match = re.search(r'"videoId":"([\w-]{11})"', html)
    return (match.group(1), query) if match else (None, None)


@tool("youtube_play", "Find a video on YouTube and play it (the top result).", {"query": "what to play"})
async def youtube_play(query: str) -> Result:
    try:
        video, title = await first_youtube_video(query)
    except Exception:
        video, title = None, None
    if not video:
        open_in_browser(SEARCH["youtube"].format(q=urllib.parse.quote_plus(query)))
        return Result(True, f"Couldn't pick one, so here are the results for {query}.")
    ok = open_in_browser(f"https://www.youtube.com/watch?v={video}")
    return Result(ok, f"Playing {title} on YouTube.")
