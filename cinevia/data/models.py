from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from typing import Literal

Kind = Literal["movie", "tv"]


@dataclass
class Title:
    """One movie or TV show, normalized from whichever source it came from."""

    id: str  # "m:<itunes id>" or "t:<tvmaze id>"
    kind: Kind
    source_id: int
    title: str
    genres: list[str] = field(default_factory=list)
    summary: str = ""
    poster: str = ""
    poster_large: str = ""
    year: int | None = None
    backdrop: str | None = None
    rating: float | None = None  # 0-10, TVmaze only; Apple's charts carry no score
    certification: str | None = None
    runtime_min: int | None = None
    trailer: str | None = None  # direct video URL when already known
    credit: str | None = None  # director for films, network for TV
    cast: list[str] = field(default_factory=list)
    itunes_collection_id: int | None = None  # Apple TV season, for TV teasers
    popularity: float = 0
    link: str | None = None
    from_search: bool = False

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> Title:
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in known})

    def with_details(self, extra: dict) -> Title:
        """A copy with the non-empty values of ``extra`` filled in."""
        merged = self.to_dict()
        merged.update({k: v for k, v in extra.items() if v not in (None, "", [])})
        return Title.from_dict(merged)
