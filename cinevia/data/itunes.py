"""Apple's public iTunes Store feeds: current movie charts with official trailers,
and TV seasons whose episodes carry short preview clips. No key needed."""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import quote

from .http import cached, get_json
from .models import Title
from .util import normalize_name, year_of

BASE = "https://itunes.apple.com"

MOVIE_GENRES = [
    (4401, "Action & Adventure"),
    (4413, "Sci-Fi & Fantasy"),
    (4404, "Comedy"),
    (4406, "Drama"),
    (4416, "Thriller"),
    (4408, "Horror"),
    (4412, "Romance"),
    (4410, "Kids & Family"),
    (4402, "Anime"),
    (4405, "Documentary"),
]


def artwork(url: str, w: int, h: int, mode: str = "bb") -> str:
    """Rewrites an mzstatic artwork URL to a size (``bb`` fit, ``cc`` center crop)."""
    return re.sub(r"/\d+x\d+[a-z]*\.(?:jpg|png|webp)$", f"/{w}x{h}{mode}.jpg", url, flags=re.I)


def _as_list(v) -> list:
    if v is None:
        return []
    return v if isinstance(v, list) else [v]


def _label(entry: dict, key: str) -> str | None:
    v = entry.get(key)
    return v.get("label") if isinstance(v, dict) else None


def parse_movie_entry(entry: dict, rank: int) -> Title:
    source_id = int(entry["id"]["attributes"]["im:id"])
    art = (entry.get("im:image") or [{}])[-1].get("label", "")
    links = _as_list(entry.get("link"))
    trailer = next(
        (
            l["attributes"]["href"]
            for l in links
            if l["attributes"].get("rel") == "enclosure" and l["attributes"].get("im:assetType") == "preview"
        ),
        None,
    )
    page = next((l["attributes"]["href"] for l in links if l["attributes"].get("rel") == "alternate"), None)
    genre = entry.get("category", {}).get("attributes", {}).get("label")
    return Title(
        id=f"m:{source_id}",
        kind="movie",
        source_id=source_id,
        title=_label(entry, "im:name") or "",
        year=year_of(_label(entry, "im:releaseDate")),
        genres=[genre] if genre else [],
        summary=_label(entry, "summary") or "",
        poster=artwork(art, 400, 600),
        poster_large=artwork(art, 1000, 1500),
        trailer=trailer,
        credit=_label(entry, "im:artist"),
        popularity=1000 - rank,
        link=page,
    )


def top_movies(genre_id: int | None = None, limit: int = 50) -> list[Title]:
    genre = f"genre={genre_id}/" if genre_id else ""

    def load() -> list[Title]:
        data = get_json(f"{BASE}/us/rss/topmovies/limit={limit}/{genre}json") or {}
        return [parse_movie_entry(e, i) for i, e in enumerate(_as_list(data.get("feed", {}).get("entry")))]

    return cached(f"movies:{genre_id or 'all'}:{limit}", load)


def parse_lookup_movie(m: dict) -> Title | None:
    if m.get("kind") != "feature-movie" or not m.get("trackId") or not m.get("trackName"):
        return None
    art = m.get("artworkUrl100", "")
    return Title(
        id=f"m:{m['trackId']}",
        kind="movie",
        source_id=int(m["trackId"]),
        title=m["trackName"],
        year=year_of(m.get("releaseDate")),
        genres=[m["primaryGenreName"]] if m.get("primaryGenreName") else [],
        summary=m.get("shortDescription") or m.get("longDescription") or "",
        poster=artwork(art, 400, 600) if art else "",
        poster_large=artwork(art, 1000, 1500) if art else "",
        trailer=m.get("previewUrl"),
        credit=m.get("artistName"),
        certification=m.get("contentAdvisoryRating"),
        runtime_min=round(m["trackTimeMillis"] / 60000) if m.get("trackTimeMillis") else None,
        link=m.get("trackViewUrl"),
    )


def movie_details(source_id: int) -> dict:
    """Runtime, rating and the long synopsis the chart feed leaves out."""

    def load() -> dict:
        data = get_json(f"{BASE}/lookup?id={source_id}&country=us") or {}
        results = data.get("results") or []
        if not results:
            return {}
        m = results[0]
        return {
            "runtime_min": round(m["trackTimeMillis"] / 60000) if m.get("trackTimeMillis") else None,
            "certification": m.get("contentAdvisoryRating"),
            "summary": m.get("longDescription"),
            "trailer": m.get("previewUrl"),
        }

    return cached(f"movie-details:{source_id}", load)


@dataclass(frozen=True)
class TvChartEntry:
    rank: int
    show_name: str
    collection_id: int


def top_tv_seasons(limit: int = 40) -> list[TvChartEntry]:
    """Apple TV's best-selling TV seasons right now: our "trending" signal for TV."""

    def load() -> list[TvChartEntry]:
        data = get_json(f"{BASE}/us/rss/toptvseasons/limit={limit}/json") or {}
        out = []
        for i, e in enumerate(_as_list(data.get("feed", {}).get("entry"))):
            out.append(
                TvChartEntry(i, _label(e, "im:artist") or _label(e, "im:name") or "", int(e["id"]["attributes"]["im:id"]))
            )
        return out

    return cached(f"tv-chart:{limit}", load)


def _season_preview(collection_id: int) -> str | None:
    data = get_json(f"{BASE}/lookup?id={collection_id}&entity=tvEpisode&country=us&limit=50") or {}
    episodes = [r for r in data.get("results", []) if r.get("kind") == "tv-episode" and r.get("previewUrl")]
    episodes.sort(key=lambda r: r.get("trackNumber") or 0)
    return episodes[0]["previewUrl"] if episodes else None


def tv_teaser(show_name: str, collection_id: int | None = None) -> str | None:
    """Preview of the first episode of the show's latest Apple TV season.
    Matches by exact (normalized) name so we never play another series' clip."""

    def load() -> str | None:
        if collection_id:
            url = _season_preview(collection_id)
            if url:
                return url
        data = get_json(
            f"{BASE}/search?term={quote(show_name)}&media=tvShow&entity=tvSeason&attribute=showTerm&country=us&limit=25"
        ) or {}
        key = normalize_name(show_name)
        seasons = [
            r
            for r in data.get("results", [])
            if r.get("collectionId") and r.get("artistName") and normalize_name(r["artistName"]) == key
        ]
        seasons.sort(key=lambda r: r.get("releaseDate") or "", reverse=True)
        for s in seasons[:3]:
            url = _season_preview(s["collectionId"])
            if url:
                return url
        return None

    return cached(f"tv-teaser:{collection_id or normalize_name(show_name)}", load)
