"""Apple Music's public charts and search: songs with 30-second previews. No key needed."""

from __future__ import annotations

from urllib.parse import quote

from .http import cached, get_json
from .itunes import BASE, _as_list, _label, artwork
from .models import Title
from .util import year_of

# Apple's genre ids for its song charts.
MUSIC_GENRES = [
    (14, "Pop"),
    (18, "Hip-Hop/Rap"),
    (15, "R&B/Soul"),
    (20, "Alternative"),
    (21, "Rock"),
    (6, "Country"),
    (7, "Electronic"),
    (12, "Latin"),
    (51, "K-Pop"),
]


def parse_song_entry(entry: dict, rank: int) -> Title | None:
    links = _as_list(entry.get("link"))
    preview = next(
        (
            l["attributes"]["href"]
            for l in links
            if l["attributes"].get("rel") == "enclosure" and l["attributes"].get("im:assetType") == "preview"
        ),
        None,
    )
    if not preview:
        return None  # nothing to play
    source_id = int(entry["id"]["attributes"]["im:id"])
    art = (entry.get("im:image") or [{}])[-1].get("label", "")
    genre = entry.get("category", {}).get("attributes", {}).get("label")
    album = (entry.get("im:collection") or {}).get("im:name", {}).get("label")
    return Title(
        id=f"s:{source_id}",
        kind="song",
        source_id=source_id,
        title=_label(entry, "im:name") or "",
        year=year_of(_label(entry, "im:releaseDate")),
        genres=[genre] if genre else [],
        poster=artwork(art, 400, 400),
        poster_large=artwork(art, 1000, 1000),
        trailer=preview,
        credit=_label(entry, "im:artist"),
        album=album,
        popularity=1000 - rank,
    )


def top_songs(genre_id: int | None = None, limit: int = 50) -> list[Title]:
    genre = f"genre={genre_id}/" if genre_id else ""

    def load() -> list[Title]:
        data = get_json(f"{BASE}/us/rss/topsongs/limit={limit}/{genre}json") or {}
        songs = (parse_song_entry(e, i) for i, e in enumerate(_as_list(data.get("feed", {}).get("entry"))))
        return [s for s in songs if s]

    return cached(f"songs:{genre_id or 'all'}:{limit}", load)


def parse_search_song(r: dict) -> Title | None:
    if r.get("kind") != "song" or not r.get("trackId") or not r.get("previewUrl"):
        return None
    art = r.get("artworkUrl100", "")
    return Title(
        id=f"s:{r['trackId']}",
        kind="song",
        source_id=int(r["trackId"]),
        title=r.get("trackName") or "",
        year=year_of(r.get("releaseDate")),
        genres=[r["primaryGenreName"]] if r.get("primaryGenreName") else [],
        poster=artwork(art, 400, 400) if art else "",
        poster_large=artwork(art, 1000, 1000) if art else "",
        trailer=r["previewUrl"],
        credit=r.get("artistName"),
        album=r.get("collectionName"),
        from_search=True,
    )


def search_songs(query: str, limit: int = 40) -> list[Title]:
    q = query.strip()
    if len(q) < 2:
        return []

    def load() -> list[Title]:
        data = get_json(f"{BASE}/search?term={quote(q)}&media=music&entity=song&limit={limit}&country=us") or {}
        songs = (parse_search_song(r) for r in data.get("results", []))
        return [s for s in songs if s]

    return cached(f"song-search:{q.lower()}", load)
