"""Accounts: registration and login against SQLite with salted, hashed passwords.

Passwords are never stored. Each user gets a random 16-byte salt, and we keep
only PBKDF2-HMAC-SHA256(password, salt) run for many iterations, so a leaked
database can't be reversed into passwords or checked with precomputed tables.
"""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import sqlite3
import time
from collections.abc import Callable
from dataclasses import dataclass

# OWASP's recommended work factor for PBKDF2-HMAC-SHA256.
ITERATIONS = 600_000
SALT_BYTES = 16
MAX_FAILURES = 5
LOCKOUT_SECONDS = 30
BAD_LOGIN = "Incorrect username or password."

USERNAME_RE = re.compile(r"^[A-Za-z0-9_.]{3,30}$")


class AuthError(Exception):
    """A message that is safe to show on the login screen."""


@dataclass(frozen=True)
class User:
    id: int
    username: str


def hash_password(password: str, salt: bytes | None = None, iterations: int = ITERATIONS) -> tuple[bytes, bytes]:
    """Returns ``(salt, digest)``; a fresh random salt is made when none is given."""
    salt = salt if salt is not None else secrets.token_bytes(SALT_BYTES)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return salt, digest


def verify_password(password: str, salt: bytes, digest: bytes, iterations: int) -> bool:
    _, candidate = hash_password(password, salt, iterations)
    # Constant-time comparison, so response time doesn't leak how many bytes matched.
    return hmac.compare_digest(candidate, digest)


def username_problem(username: str) -> str | None:
    if not USERNAME_RE.fullmatch(username):
        return "Username must be 3-30 characters: letters, numbers, dots or underscores."
    return None


def password_problem(password: str) -> str | None:
    if len(password) < 8:
        return "Password must be at least 8 characters."
    if len(password) > 128:
        return "Password must be at most 128 characters."
    if not (re.search(r"[A-Za-z]", password) and re.search(r"\d", password)):
        return "Password needs at least one letter and one number."
    return None


class Accounts:
    def __init__(
        self,
        conn: sqlite3.Connection,
        iterations: int = ITERATIONS,
        now: Callable[[], float] = time.monotonic,
    ) -> None:
        self.conn = conn
        self.iterations = iterations
        self.now = now
        self._failures: dict[str, list[float]] = {}
        # Hashed for unknown usernames so both failure paths take the same time.
        self._dummy_salt, self._dummy_hash = hash_password(secrets.token_hex(8), iterations=iterations)

    def register(self, username: str, password: str) -> User:
        username = username.strip()
        problem = username_problem(username) or password_problem(password)
        if problem:
            raise AuthError(problem)
        salt, digest = hash_password(password, iterations=self.iterations)
        try:
            with self.conn:
                cur = self.conn.execute(
                    "INSERT INTO users (username, salt, password_hash, iterations, created_at) VALUES (?, ?, ?, ?, ?)",
                    (username, salt, digest, self.iterations, time.time()),
                )
        except sqlite3.IntegrityError:
            raise AuthError("That username is taken. Try another one.") from None
        return User(int(cur.lastrowid), username)

    def login(self, username: str, password: str) -> User:
        key = username.strip().lower()
        self._check_lockout(key)
        row = self.conn.execute(
            "SELECT id, username, salt, password_hash, iterations FROM users WHERE username = ?",
            (username.strip(),),
        ).fetchone()
        if row is None:
            verify_password(password, self._dummy_salt, self._dummy_hash, self.iterations)
            self._record_failure(key)
            raise AuthError(BAD_LOGIN)
        if not verify_password(password, row["salt"], row["password_hash"], row["iterations"]):
            self._record_failure(key)
            raise AuthError(BAD_LOGIN)
        self._failures.pop(key, None)
        return User(row["id"], row["username"])

    def _recent_failures(self, key: str) -> list[float]:
        cutoff = self.now() - LOCKOUT_SECONDS
        recent = [t for t in self._failures.get(key, []) if t > cutoff]
        self._failures[key] = recent
        return recent

    def _check_lockout(self, key: str) -> None:
        recent = self._recent_failures(key)
        if len(recent) >= MAX_FAILURES:
            wait = int(recent[0] + LOCKOUT_SECONDS - self.now()) + 1
            raise AuthError(f"Too many attempts. Try again in {wait} seconds.")

    def _record_failure(self, key: str) -> None:
        self._recent_failures(key).append(self.now())
