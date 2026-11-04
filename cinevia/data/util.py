from __future__ import annotations

import html
import re
import time
from collections.abc import Callable, Iterable
from datetime import datetime
from typing import TypeVar

T = TypeVar("T")


def strip_html(text: str | None) -> str:
    """TVmaze summaries are HTML fragments; we only ever show them as text."""
    if not text:
        return ""
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]*>", " ", text))).strip()


def normalize_name(name: str) -> str:
    """Loose key for matching a show across sources ("FROM" vs "From")."""
    s = name.lower().replace("&", "and")
    s = re.sub(r"^the\s+", "", s)
    return re.sub(r"[^a-z0-9]+", "", s)


def year_of(date: str | None) -> int | None:
    if not date or len(date) < 4 or not date[:4].isdigit():
        return None
    return int(date[:4])


def format_runtime(minutes: int | None) -> str | None:
    if not minutes or minutes <= 0:
        return None
    h, m = divmod(minutes, 60)
    if not h:
        return f"{m}m"
    return f"{h}h {m}m" if m else f"{h}h"


def unique_by(items: Iterable[T], key: Callable[[T], str]) -> list[T]:
    seen: set[str] = set()
    out: list[T] = []
    for item in items:
        k = key(item)
        if k not in seen:
            seen.add(k)
            out.append(item)
    return out


def format_when(ts: float, now: datetime | None = None) -> str:
    """'Today, 10:02 AM', 'Yesterday, 9:41 PM', 'Mar 18, 6:10 PM'."""
    now = now or datetime.now()
    d = datetime.fromtimestamp(ts)
    clock = d.strftime("%I:%M %p").lstrip("0")
    days = (now.date() - d.date()).days
    if days == 0:
        return f"Today, {clock}"
    if days == 1:
        return f"Yesterday, {clock}"
    return f"{d.strftime('%b')} {d.day}, {clock}"


def today_iso(days_from_today: int = 0) -> str:
    return datetime.fromtimestamp(time.time() + days_from_today * 86_400).strftime("%Y-%m-%d")
