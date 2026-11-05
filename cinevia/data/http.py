"""JSON over HTTPS with in-memory and short-lived disk caches, safe to use from worker threads."""

from __future__ import annotations

import gzip
import hashlib
import json
import ssl
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import TypeVar

T = TypeVar("T")


def _tls_context() -> ssl.SSLContext:
    """Verify certificates the way the operating system does (as browsers do).
    Python's bundled OpenSSL can reject valid sites on Windows by picking an
    expired cross-signed root; truststore uses the native verifier instead."""
    try:
        import truststore

        return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    except ImportError:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())


_TLS = _tls_context()

TTL_SECONDS = 30 * 60
DISK_TTL_SECONDS = 2 * 60 * 60
DISK_DIR = Path(__file__).resolve().parents[2] / "data" / "http-cache"
TIMEOUT = 60
USER_AGENT = "Cinevia/1.0 (student project; desktop app)"

_cache: dict[str, tuple[float, object]] = {}
_locks: dict[str, threading.Lock] = {}
_guard = threading.Lock()


class FetchError(Exception):
    pass


def _disk_path(url: str) -> Path:
    return DISK_DIR / (hashlib.sha256(url.encode()).hexdigest()[:32] + ".json")


def _read_disk(url: str) -> object | None:
    """Responses are kept on disk for two hours so the next launch opens instantly."""
    path = _disk_path(url)
    try:
        if time.time() - path.stat().st_mtime < DISK_TTL_SECONDS:
            return json.loads(path.read_text("utf-8"))
    except (OSError, ValueError):
        pass
    return None


def _write_disk(url: str, data: object) -> None:
    try:
        DISK_DIR.mkdir(parents=True, exist_ok=True)
        _disk_path(url).write_text(json.dumps(data), "utf-8")
    except OSError:
        pass  # caching is an optimization; never fail a request over it


def get_json(url: str) -> object:
    """Fetches JSON (gzip-compressed on the wire), backing off when an API rate-limits us (HTTP 429)."""
    hit = _read_disk(url)
    if hit is not None:
        return hit
    req = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT, "Accept": "application/json", "Accept-Encoding": "gzip"}
    )
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT, context=_TLS) as res:
                body = res.read()
                if res.headers.get("Content-Encoding") == "gzip":
                    body = gzip.decompress(body)
                data = json.loads(body.decode("utf-8"))
                _write_disk(url, data)
                return data
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < 3:
                time.sleep(1.5 * (attempt + 1))
                continue
            if e.code == 404:
                return None
            raise FetchError(f"Request failed ({e.code})") from e
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            raise FetchError("Couldn't reach the server. Check your connection.") from e
    raise FetchError("The server is busy. Try again in a moment.")


def url_exists(url: str) -> bool:
    """True when the server has the file (a HEAD request, so nothing is downloaded)."""
    req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=20, context=_TLS) as res:
            return 200 <= res.status < 300
    except urllib.error.HTTPError:
        return False
    except (urllib.error.URLError, TimeoutError) as e:
        raise FetchError("Couldn't reach the server. Check your connection.") from e


def cached(key: str, load: Callable[[], T]) -> T:
    """Runs ``load`` once per key for half an hour; concurrent callers share one request."""
    with _guard:
        hit = _cache.get(key)
        if hit and time.time() - hit[0] < TTL_SECONDS:
            return hit[1]  # type: ignore[return-value]
        lock = _locks.setdefault(key, threading.Lock())
    with lock:
        with _guard:
            hit = _cache.get(key)
            if hit and time.time() - hit[0] < TTL_SECONDS:
                return hit[1]  # type: ignore[return-value]
        value = load()
        with _guard:
            _cache[key] = (time.time(), value)
        return value


def map_limit(items: list, limit: int, fn: Callable) -> list:
    """``fn`` over ``items`` with at most ``limit`` running at once (TVmaze allows ~20 calls / 10 s)."""
    with ThreadPoolExecutor(max_workers=limit) as pool:
        return list(pool.map(fn, items))
