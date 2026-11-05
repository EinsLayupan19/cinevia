"""Free-to-play games from the FreeToGame API: cover art, details, screenshots
and gameplay videos. No key needed. Store links are dropped on purpose,
because Cinevia keeps everything inside its own window."""

from __future__ import annotations

from .http import cached, get_json, url_exists
from .models import Title
from .util import year_of

BASE = "https://www.freetogame.com/api"

# The API spells some genres several ways; each group covers its spellings.
GAME_GROUPS: dict[str, tuple[str, ...]] = {
    "Shooter": ("Shooter",),
    "MMORPG": ("MMORPG", "MMO", "MMOARPG"),
    "Action RPG": ("ARPG", "Action RPG", "Action", "Action Game", "RPG", "Dungeon Crawler", "Fantasy"),
    "Strategy": ("Strategy",),
    "MOBA": ("MOBA",),
    "Battle Royale": ("Battle Royale",),
    "Card Games": ("Card", "Card Game"),
    "Racing & Sports": ("Racing", "Sports"),
    "Fighting": ("Fighting",),
    "Social": ("Social",),
}


def group_of(t: Title) -> str:
    genre = t.genres[0] if t.genres else ""
    return next((name for name, spellings in GAME_GROUPS.items() if genre in spellings), "More Games")


def parse_game(g: dict, rank: int) -> Title:
    genre = (g.get("genre") or "").strip()
    thumb = g.get("thumbnail") or ""
    return Title(
        id=f"g:{g['id']}",
        kind="game",
        source_id=int(g["id"]),
        title=(g.get("title") or "").strip(),
        year=year_of(g.get("release_date")),
        genres=[genre] if genre else [],
        summary=(g.get("short_description") or "").strip(),
        poster=thumb,
        poster_large=thumb,
        credit=(g.get("publisher") or "").strip() or None,
        developer=(g.get("developer") or "").strip() or None,
        platform=(g.get("platform") or "").strip() or None,
        popularity=1000 - rank,
    )


def all_games() -> list[Title]:
    """Every live game, most played first (about 400)."""

    def load() -> list[Title]:
        data = get_json(f"{BASE}/games?sort-by=popularity") or []
        return [parse_game(g, i) for i, g in enumerate(data) if g.get("id") and g.get("title")]

    return cached("games:all", load)


def games_in(group: str) -> list[Title]:
    return [t for t in all_games() if group_of(t) == group]


def game_details(source_id: int) -> dict:
    """Long description and screenshots (the first screenshot becomes the backdrop)."""

    def load() -> dict:
        g = get_json(f"{BASE}/game?id={source_id}") or {}
        shots = [s["image"] for s in g.get("screenshots") or [] if s.get("image")]
        return {
            "summary": (g.get("description") or "").strip(),
            "screenshots": shots,
            "backdrop": shots[0] if shots else None,
        }

    return cached(f"game-details:{source_id}", load)


def video_url(source_id: int) -> str | None:
    """FreeToGame's gameplay clip, if this game has one."""
    url = f"https://www.freetogame.com/g/{source_id}/videoplayback.webm"
    return cached(f"game-video:{source_id}", lambda: url if url_exists(url) else None)


def more_like(t: Title) -> list[Title]:
    group = group_of(t)
    return [o for o in all_games() if o.id != t.id and group_of(o) == group][:16]
