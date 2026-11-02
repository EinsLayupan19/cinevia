"""Creates a demo account for presentations, with a few favorites and searches saved.

    py create_demo_account.py

The account goes through the same sign-up as everyone else, so its password is
stored only as a salted PBKDF2 hash. Safe to run again: an existing demo account
is left as it is and only missing favorites are added.
"""

from __future__ import annotations

import sys

from cinevia import auth, db
from cinevia.data import itunes, tvmaze
from cinevia.data.http import FetchError

DEMO_USERNAME = "demo"
DEMO_PASSWORD = "CineviaDemo2026"  # demo only; never reuse a real password here

DEMO_SEARCHES = ["the bear", "spider", "dune", "science fiction"]


def main() -> int:
    conn = db.connect()
    db.migrate(conn)
    accounts = auth.Accounts(conn)
    try:
        user = accounts.register(DEMO_USERNAME, DEMO_PASSWORD)
        print(f"Created account '{DEMO_USERNAME}'.")
    except auth.AuthError:
        user = accounts.login(DEMO_USERNAME, DEMO_PASSWORD)
        print(f"Account '{DEMO_USERNAME}' already exists; topping up its library.")

    picks = []
    try:
        picks += itunes.top_movies()[:3]
    except FetchError as e:
        print(f"Skipped movie favorites: {e}")
    try:
        picks += tvmaze.trending_shows()[:2]
    except FetchError as e:
        print(f"Skipped TV favorites: {e}")
    for title in picks:
        if not db.is_favorite(conn, user.id, title.id):
            db.add_favorite(conn, user.id, title.to_dict())
    for query in reversed(DEMO_SEARCHES):
        if query not in {h.query for h in db.history(conn, user.id)}:
            db.add_search(conn, user.id, query)

    print(f"Favorites: {len(db.favorites(conn, user.id))}, searches: {len(db.history(conn, user.id))}.")
    print("Sign in with the demo username and password listed in README.md.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
