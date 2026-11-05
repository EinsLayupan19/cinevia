"""Combines both sources: genre buckets, merging, search, Discover filters, trailers."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date

from . import games, itunes, music, tvmaze
from .http import FetchError, cached
from .models import Title
from .util import unique_by

# Apple and TVmaze name genres differently; these buckets let one filter cover both.
GENRE_BUCKETS: dict[str, tuple[str, ...]] = {
    "Action": ("Action & Adventure", "Action", "War", "Western"),
    "Adventure": ("Action & Adventure", "Adventure"),
    "Animation": ("Anime", "Kids & Family", "Children"),
    "Comedy": ("Comedy",),
    "Crime": ("Crime", "Legal", "Espionage"),
    "Documentary": ("Documentary", "History", "Nature"),
    "Drama": ("Drama", "Medical", "Family"),
    "Fantasy": ("Sci-Fi & Fantasy", "Fantasy", "Supernatural"),
    "Horror": ("Horror",),
    "Romance": ("Romance",),
    "Science Fiction": ("Sci-Fi & Fantasy", "Science-Fiction"),
    "Thriller": ("Thriller", "Mystery"),
}


def buckets_of(t: Title) -> list[str]:
    return [name for name, match in GENRE_BUCKETS.items() if any(g in match for g in t.genres)]


def merge_titles(lists: list[list[Title]]) -> list[Title]:
    """A film that charts in several genre feeds keeps every genre and its best chart position."""
    by_id: dict[str, Title] = {}
    for lst in lists:
        for t in lst:
            prev = by_id.get(t.id)
            if prev is None:
                by_id[t.id] = replace(t, genres=list(t.genres))
                continue
            prev.genres.extend(g for g in t.genres if g not in prev.genres)
            prev.popularity = max(prev.popularity, t.popularity)
    return list(by_id.values())


def _settled(*loaders) -> list[list[Title]]:
    out = []
    for load in loaders:
        try:
            out.append(load())
        except FetchError:
            continue
    return out


def movie_library() -> list[Title]:
    """Every movie across the top chart and the genre charts (about 500 titles)."""

    def load() -> list[Title]:
        lists = _settled(itunes.top_movies, *[(lambda g=g: itunes.top_movies(g)) for g, _ in itunes.MOVIE_GENRES])
        if not lists:
            raise FetchError("Couldn't reach the movie charts. Check your connection.")
        return merge_titles(lists)

    return cached("movie-library", load)


def everything() -> list[Title]:
    lists = _settled(movie_library, tvmaze.trending_shows, tvmaze.airing_today, tvmaze.show_library)
    if not lists:
        raise FetchError("Catalog unavailable. Check your connection.")
    return unique_by([t for lst in lists for t in lst], lambda t: t.id)


def matches_query(t: Title, q: str) -> bool:
    needle = q.strip().lower()
    return bool(needle) and (needle in t.title.lower() or needle in (t.credit or "").lower())


def discover_pool(query: str) -> list[Title]:
    """The browsable catalog, plus TVmaze's full search when a title was typed."""
    q = query.strip()
    if not q:
        return everything()
    local = [t for t in everything() if matches_query(t, q)]
    try:
        shows = tvmaze.search_shows(q)
    except FetchError:
        shows = []
    return unique_by([*local, *shows], lambda t: t.id)


def details(t: Title) -> dict:
    if t.kind == "game":
        return games.game_details(t.source_id)
    if t.kind == "song":
        return {}
    return itunes.movie_details(t.source_id) if t.kind == "movie" else tvmaze.show_details(t.source_id)


def title_by_id(title_id: str) -> Title | None:
    prefix, _, raw = title_id.partition(":")
    if not raw.isdigit():
        return None
    if prefix == "t":
        return tvmaze.show_by_id(int(raw))
    if prefix == "m":
        found = [t for t in movie_library() if t.id == title_id]
        return found[0] if found else None
    return None


def more_like_this(t: Title) -> list[Title]:
    if t.kind == "game":
        return games.more_like(t)
    pool = movie_library() if t.kind == "movie" else tvmaze.show_library()
    mine = set(buckets_of(t))
    scored = [(len(mine & set(buckets_of(o))), o) for o in pool if o.id != t.id]
    scored = [(s, o) for s, o in scored if s > 0]
    scored.sort(key=lambda x: (x[0], x[1].popularity), reverse=True)
    return [o for _, o in scored[:16]]


def resolve_trailer(t: Title) -> str | None:
    """Official trailer for a movie, an Apple TV episode preview for a show,
    or FreeToGame's gameplay clip for a game."""
    if t.kind == "game":
        return games.video_url(t.source_id)
    if t.kind == "song":
        return t.trailer
    if t.kind == "movie":
        return t.trailer or itunes.movie_details(t.source_id).get("trailer")
    return itunes.tv_teaser(t.title, t.itunes_collection_id)


# ---------- Discover filters ----------

TYPE_OPTIONS = ["All Types", "Movies", "TV Shows"]
GENRE_OPTIONS = ["All Genres", *GENRE_BUCKETS]
RATING_OPTIONS = ["Any Rating", "9+", "8+", "7+", "6+"]
SORT_OPTIONS = ["Popularity", "Highest Rated", "Newest First", "Oldest First", "Alphabetical (A-Z)"]
OLDER = "Older Titles"


def year_options(today: date | None = None) -> list[str]:
    y = (today or date.today()).year
    return ["All Years", *[str(y - i) for i in range(5)], OLDER]


@dataclass(frozen=True)
class Filters:
    query: str = ""
    type: str = "All Types"
    genre: str = "All Genres"
    year: str = "All Years"
    rating: str = "Any Rating"
    sort: str = "Popularity"


def popularity_score(t: Title) -> float:
    """Movies carry a chart rank (~950-1000), shows a TVmaze weight (0-100): put both on 0-100."""
    return max(0.0, t.popularity - 900) if t.kind == "movie" else t.popularity


def apply_filters(items: list[Title], f: Filters, today: date | None = None) -> list[Title]:
    q = f.query.strip().lower()
    oldest_listed = (today or date.today()).year - 4
    min_rating = 0 if f.rating == "Any Rating" else float(f.rating.rstrip("+"))

    def keep(t: Title) -> bool:
        if f.type == "Movies" and t.kind != "movie":
            return False
        if f.type == "TV Shows" and t.kind != "tv":
            return False
        if q and q not in t.title.lower() and q not in (t.credit or "").lower() and not t.from_search:
            return False
        if f.genre != "All Genres" and f.genre not in buckets_of(t):
            return False
        if f.year == OLDER and not (t.year and t.year < oldest_listed):
            return False
        if f.year not in ("All Years", OLDER) and t.year != int(f.year):
            return False
        return not (min_rating and (t.rating or 0) < min_rating)

    sorters = {
        "Popularity": lambda t: -popularity_score(t),
        "Highest Rated": lambda t: -(t.rating or 0),
        "Newest First": lambda t: -(t.year or 0),
        "Oldest First": lambda t: t.year or 9999,
        "Alphabetical (A-Z)": lambda t: t.title.lower(),
    }
    return sorted([t for t in items if keep(t)], key=sorters[f.sort])


def warm_up() -> None:
    """Loads the shared catalog in the background (called while the login screen is up)."""
    from concurrent.futures import ThreadPoolExecutor

    jobs = [itunes.top_movies, tvmaze.trending_shows, tvmaze.airing_today, movie_library, tvmaze.show_library,
            music.top_songs, games.all_games]
    with ThreadPoolExecutor(max_workers=len(jobs)) as pool:
        for future in [pool.submit(job) for job in jobs]:
            try:
                future.result()
            except Exception:
                pass  # each screen shows its own error and retry; also covers app shutdown
