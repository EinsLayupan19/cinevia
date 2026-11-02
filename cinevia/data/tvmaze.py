"""TVmaze: open TV metadata (CC BY-SA), no key. https://www.tvmaze.com/api"""

from __future__ import annotations

from urllib.parse import quote

from .http import FetchError, cached, get_json, map_limit
from .itunes import top_tv_seasons
from .models import Title
from .util import normalize_name, strip_html, today_iso, unique_by, year_of

BASE = "https://api.tvmaze.com"


def parse_show(show: dict, itunes_collection_id: int | None = None) -> Title:
    image = show.get("image") or {}
    network = show.get("network") or show.get("webChannel") or {}
    return Title(
        id=f"t:{show['id']}",
        kind="tv",
        source_id=int(show["id"]),
        title=show.get("name") or "",
        year=year_of(show.get("premiered")),
        genres=list(show.get("genres") or []),
        summary=strip_html(show.get("summary")),
        poster=image.get("medium") or "",
        poster_large=image.get("original") or image.get("medium") or "",
        rating=(show.get("rating") or {}).get("average"),
        runtime_min=show.get("averageRuntime") or show.get("runtime"),
        credit=network.get("name"),
        popularity=show.get("weight") or 0,
        itunes_collection_id=itunes_collection_id,
        link=show.get("url"),
    )


def _has_poster(show: dict | None) -> bool:
    return bool(show and show.get("image"))


def trending_shows(limit: int = 16) -> list[Title]:
    """What sells on Apple TV right now, matched to TVmaze for posters and ratings."""

    def load() -> list[Title]:
        chart = unique_by(top_tv_seasons(40), lambda e: normalize_name(e.show_name))[:limit]

        def match(entry):
            try:
                show = get_json(f"{BASE}/singlesearch/shows?q={quote(entry.show_name)}")
            except FetchError:
                return None  # unmatched chart entries are simply skipped
            if not _has_poster(show) or normalize_name(show["name"]) != normalize_name(entry.show_name):
                return None
            return parse_show(show, entry.collection_id)

        return [t for t in map_limit(chart, 6, match) if t]

    return cached(f"tv-trending:{limit}", load)


def scheduled_shows(date: str) -> list[Title]:
    """Shows with an episode out on ``date`` (US networks plus worldwide streaming), most-followed first."""

    def load() -> list[Title]:
        network, web = (
            r or [] for r in map_limit([f"{BASE}/schedule?country=US&date={date}", f"{BASE}/schedule/web?date={date}"], 2, get_json)
        )
        shows = [i.get("show") or (i.get("_embedded") or {}).get("show") for i in [*network, *web]]
        shows = unique_by([s for s in shows if _has_poster(s)], lambda s: str(s["id"]))
        shows.sort(key=lambda s: s.get("weight") or 0, reverse=True)
        return [parse_show(s) for s in shows]

    return cached(f"tv-schedule:{date}", load)


def airing_today(limit: int = 30) -> list[Title]:
    return scheduled_shows(today_iso())[:limit]


def show_library() -> list[Title]:
    """Trending shows plus everything that aired yesterday or today, minus obscure entries."""

    def load() -> list[Title]:
        lists = []
        for fn in (trending_shows, lambda: scheduled_shows(today_iso()), lambda: scheduled_shows(today_iso(-1))):
            try:
                lists.append(fn())
            except FetchError:
                continue
        if not lists:
            raise FetchError("Couldn't reach TVmaze. Check your connection.")
        pool = unique_by([t for lst in lists for t in lst], lambda t: t.id)
        return sorted([t for t in pool if t.popularity >= 60], key=lambda t: t.popularity, reverse=True)

    return cached(f"tv-library:{today_iso()}", load)


def search_shows(query: str) -> list[Title]:
    q = query.strip().lower()

    def load() -> list[Title]:
        data = get_json(f"{BASE}/search/shows?q={quote(q)}") or []
        out = []
        for r in data:
            if _has_poster(r.get("show")):
                t = parse_show(r["show"])
                t.from_search = True
                out.append(t)
        return out

    return cached(f"tv-search:{q}", load)


def show_by_id(show_id: int) -> Title | None:
    def load() -> Title | None:
        show = get_json(f"{BASE}/shows/{show_id}")
        return parse_show(show) if show else None

    return cached(f"tv-by-id:{show_id}", load)


def show_details(show_id: int) -> dict:
    """Wide background art plus the top-billed cast."""

    def load() -> dict:
        show = get_json(f"{BASE}/shows/{show_id}?embed[]=images&embed[]=cast") or {}
        embedded = show.get("_embedded") or {}
        bg = next((i for i in embedded.get("images", []) if i.get("type") == "background"), None)
        return {
            "backdrop": bg["resolutions"]["original"]["url"] if bg else None,
            "cast": [c["person"]["name"] for c in embedded.get("cast", [])[:6]],
        }

    return cached(f"tv-details:{show_id}", load)
