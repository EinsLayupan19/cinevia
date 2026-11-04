# Cinevia (desktop)

A Python desktop app for browsing trending **movies and TV shows** and watching their **trailers and teasers**, with user accounts. Built for ITL313-18 (SIA 2 Lab) Final Term Mini Project, **Media and Entertainment: Movies and TV Shows**.

## Group members

| Name | Section |
|---|---|
| Zirk Eins B. Layupan | 1BSIT-3 |
| Nathaniel Coronado | 1BSIT-3 |

## How it meets the project requirements

| Requirement | Where |
|---|---|
| 1. GUI with PyQt/PySide | PySide6 (Qt 6). Screens are in `cinevia/ui/`. |
| 2a. SQLite for user data | `cinevia/db.py`: `users` table, plus each user's `favorites` and `history`. The file is `data/cinevia.db`. |
| 2b. Password hashing with `hashlib` | `cinevia/auth.py`: `hashlib.pbkdf2_hmac("sha256", ...)` with a random 16-byte salt per user and 600,000 iterations. Plain-text passwords are never stored. |
| 2c. Login logic | `Accounts.login()`: looks up the username, re-hashes the typed password with the stored salt, and compares with `hmac.compare_digest`. |
| 3A.1 Movies and TV Shows (plays on the UI, no redirect) | Home, Movies, TV Shows, Details, Discover (search and filters), Favorites, Search History, and an in-app trailer player (`cinevia/ui/player.py`, Qt Multimedia). |

Extra security details:
- The login error never says whether the username exists ("Incorrect username or password."). An unknown username still costs one hash, so response times match.
- After 5 wrong passwords, that username is locked for 30 seconds.
- Sign-up rules: usernames are 3-30 letters, numbers, dots or underscores, unique ignoring case. Passwords are 8-128 characters with at least one letter and one number.
- Hashing runs on a background thread, so the window stays responsive.

## Run it

Requires Python 3.10 or newer (tested with 3.14) on Windows, macOS or Linux, plus an internet connection.

```bash
py -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
py main.py
```

On macOS or Linux, use `python3` instead of `py` and `source .venv/bin/activate` to activate.

Create an account on the first screen, then sign in.

### Demo account

For presentations, create a ready-made account with a few favorites and searches already saved:

```bash
py create_demo_account.py
```

| Username | Password |
|---|---|
| `demo` | `CineviaDemo2026` |

It is a normal account: the password is stored only as a salted PBKDF2 hash, and the script is safe to run again. Use it for demos only, never with a real password.

## Features

- **Sign in / Create account** screen with live poster art.
- **Home**: a featured hero (01 / 05) with "Watch trailer" and "View details", plus rows for Top 10 movies, trending TV, today's new episodes and genres. Drag rows with the mouse, or use the edge arrows.
- **Movies** and **TV Shows** pages with genre rows.
- **Details**: blurred backdrop, poster, rating, runtime, genres, synopsis, director or network, cast, "More Like This", and add to favorites.
- **Trailers**: official movie trailers and TV episode teasers play inside the app's own player and never redirect to a browser. When Apple has no teaser for a show, its Watch button says so instead of opening another site.
- **Discover**: search by title, then filter by type, genre, release year and rating, and sort.
- **Favorites** (grouped by genre) and **Search History** are saved per user in SQLite.
- **Dark and light mode**, remembered per user.
- Keyboard: `Ctrl+K` focuses search, `Alt+Left` goes back. On a focused poster, `Enter` opens it and `F` toggles favorite. `Space` plays or pauses in the player.

## Data sources (no API keys)

- Movies and trailers: Apple's iTunes Store charts (top movies overall and by genre).
- TV shows: [TVmaze](https://www.tvmaze.com/api) (CC BY-SA), for posters, ratings, cast and backgrounds. "Trending" comes from Apple TV's top TV seasons chart.
- TV teasers: the Apple TV preview of a show's latest season.

API responses are cached in `data/http-cache/` for 2 hours and images in `data/image-cache/`, so the second launch is much faster. TVmaze can take a few seconds per request, so the first launch fills in over about half a minute.

## Tests

```bash
py -m unittest discover -s tests
```

31 tests cover password hashing and verification, sign-up rules, unique usernames, login failures and lockout, per-user favorites, history and theme, the API parsers, and the Discover filters.

## Inspect the database

Open `data/cinevia.db` with [DB Browser for SQLite](https://sqlitebrowser.org/). The `users` table shows the `salt`, `password_hash` and `iterations` columns, and no password.

## Project layout

```
main.py                 entry point
cinevia/
  auth.py               hashing, sign-up and login, lockout
  db.py                 SQLite schema and queries
  app.py                starts the app: login, then the main window
  data/                 iTunes and TVmaze clients, caching, Discover filters
  ui/                   theme, login, main window, pages, hero, player, cards
assets/                 logo and the Geist font (SIL Open Font License)
tests/                  unit tests
```
