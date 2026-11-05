import random
import unittest

from cinevia import db
from cinevia.arcade.memory import MemoryGame
from cinevia.arcade.snake import SnakeGame
from cinevia.arcade.tictactoe import TicTacToe, winner
from cinevia.auth import Accounts
from cinevia.data import catalog
from cinevia.data.games import group_of, parse_game
from cinevia.data.music import parse_search_song, parse_song_entry

ART = "https://is1-ssl.mzstatic.com/image/thumb/Music221/v4/a0/26UM1IM21436.rgb.jpg/170x170bb.png"
PREVIEW = "https://audio-ssl.itunes.apple.com/itunes-assets/AudioPreview221/x.plus.aac.p.m4a"

SONG_ENTRY = {
    "im:name": {"label": "Patient Zero"},
    "im:image": [{"label": ART.replace("170x170", "55x55")}, {"label": ART}],
    "im:collection": {"im:name": {"label": "The Life of a Showgirl: The Encore"}},
    "link": [
        {"attributes": {"rel": "alternate", "type": "text/html", "href": "https://music.apple.com/us/album/x"}},
        {"attributes": {"rel": "enclosure", "type": "audio/x-m4a", "href": PREVIEW, "im:assetType": "preview"}},
    ],
    "id": {"label": "https://music.apple.com/us/album/x", "attributes": {"im:id": "6814997425"}},
    "im:artist": {"label": "Taylor Swift"},
    "category": {"attributes": {"im:id": "14", "term": "Pop", "label": "Pop"}},
    "im:releaseDate": {"label": "2026-09-24T00:00:00-07:00"},
}

SEARCH_SONG = {
    "wrapperType": "track",
    "kind": "song",
    "trackId": 6814997425,
    "trackName": "Patient Zero",
    "artistName": "Taylor Swift",
    "collectionName": "The Life of a Showgirl: The Encore",
    "previewUrl": PREVIEW,
    "artworkUrl100": ART.replace("170x170bb.png", "100x100bb.jpg"),
    "releaseDate": "2026-09-24T07:00:00Z",
    "primaryGenreName": "Pop",
}

GAME = {
    "id": 452,
    "title": "Call Of Duty: Warzone",
    "thumbnail": "https://www.freetogame.com/g/452/thumbnail.jpg",
    "short_description": "A standalone free-to-play battle royale.",
    "game_url": "https://www.freetogame.com/open/call-of-duty-warzone",
    "genre": " Shooter",
    "platform": "PC (Windows)",
    "publisher": "Activision",
    "developer": "Infinity Ward",
    "release_date": "2020-03-10",
}


class MusicParsingTests(unittest.TestCase):
    def test_chart_entry_becomes_a_song_with_its_preview(self):
        s = parse_song_entry(SONG_ENTRY, 0)
        self.assertEqual((s.id, s.kind, s.title, s.credit), ("s:6814997425", "song", "Patient Zero", "Taylor Swift"))
        self.assertEqual(s.album, "The Life of a Showgirl: The Encore")
        self.assertEqual(s.trailer, PREVIEW)
        self.assertEqual(s.genres, ["Pop"])
        self.assertEqual(s.year, 2026)
        self.assertTrue(s.poster.endswith("/400x400bb.jpg"))  # square art, sized up from the feed's 170px

    def test_chart_entry_without_preview_is_skipped(self):
        entry = dict(SONG_ENTRY, link=[SONG_ENTRY["link"][0]])
        self.assertIsNone(parse_song_entry(entry, 0))

    def test_search_result_matches_chart_entry(self):
        s = parse_search_song(SEARCH_SONG)
        self.assertEqual((s.id, s.title, s.credit, s.trailer), ("s:6814997425", "Patient Zero", "Taylor Swift", PREVIEW))
        self.assertTrue(s.from_search)
        self.assertIsNone(parse_search_song(dict(SEARCH_SONG, previewUrl=None)))
        self.assertIsNone(parse_search_song(dict(SEARCH_SONG, kind="music-video")))


class GameParsingTests(unittest.TestCase):
    def test_game_fields(self):
        g = parse_game(GAME, 3)
        self.assertEqual((g.id, g.kind, g.title, g.year), ("g:452", "game", "Call Of Duty: Warzone", 2020))
        self.assertEqual(g.genres, ["Shooter"])  # stray spaces in the API's genre are trimmed
        self.assertEqual((g.credit, g.developer, g.platform), ("Activision", "Infinity Ward", "PC (Windows)"))
        self.assertGreater(parse_game(GAME, 0).popularity, g.popularity)  # earlier in the list = more popular
        self.assertIsNone(g.link)  # the store link is never kept: the app does not send players out

    def test_genre_groups_merge_the_apis_spellings(self):
        self.assertEqual(group_of(parse_game(dict(GAME, genre="Card Game"), 0)), "Card Games")
        self.assertEqual(group_of(parse_game(dict(GAME, genre="Card"), 0)), "Card Games")
        self.assertEqual(group_of(parse_game(dict(GAME, genre=" MMORPG"), 0)), "MMORPG")
        self.assertEqual(group_of(parse_game(dict(GAME, genre="ARPG"), 0)), "Action RPG")

    def test_songs_and_games_have_no_film_genre_bucket(self):
        self.assertEqual(catalog.buckets_of(parse_game(GAME, 0)), [])


class ScoreTests(unittest.TestCase):
    def setUp(self):
        self.conn = db.connect(":memory:")
        db.migrate(self.conn)
        accounts = Accounts(self.conn)
        self.a = accounts.register("zirk", "movienight42").id
        self.b = accounts.register("nathan", "movienight42").id

    def test_highest_score_is_kept(self):
        self.assertEqual(db.record_score(self.conn, self.a, "snake", 12), (12, True))
        self.assertEqual(db.record_score(self.conn, self.a, "snake", 7), (12, False))
        self.assertEqual(db.record_score(self.conn, self.a, "snake", 20), (20, True))
        self.assertEqual(db.best_scores(self.conn, self.a)["snake"], (20, 3))

    def test_fewest_moves_is_kept_for_memory(self):
        db.record_score(self.conn, self.a, "memory", 18, mode="min")
        self.assertEqual(db.record_score(self.conn, self.a, "memory", 25, mode="min"), (18, False))
        self.assertEqual(db.record_score(self.conn, self.a, "memory", 14, mode="min"), (14, True))

    def test_wins_add_up(self):
        db.record_score(self.conn, self.a, "tictactoe", 1, mode="sum")
        db.record_score(self.conn, self.a, "tictactoe", 0, mode="sum")
        self.assertEqual(db.record_score(self.conn, self.a, "tictactoe", 1, mode="sum"), (2, True))

    def test_scores_are_per_user(self):
        db.record_score(self.conn, self.a, "snake", 30)
        self.assertEqual(db.best_scores(self.conn, self.b), {})


class SnakeTests(unittest.TestCase):
    def test_moves_and_grows_when_eating(self):
        g = SnakeGame(10, 8, rng=random.Random(1))
        head = g.body[0]
        g.food = (head[0] + 1, head[1])
        g.step()
        self.assertEqual(g.body[0], (head[0] + 1, head[1]))
        self.assertEqual((g.score, len(g.body)), (1, 4))
        self.assertNotIn(g.food, g.body)

    def test_cannot_reverse_into_itself(self):
        g = SnakeGame(10, 8)
        g.turn((-1, 0))  # heading right; a U-turn is ignored
        g.step()
        self.assertTrue(g.alive)

    def test_hitting_a_wall_ends_the_game(self):
        g = SnakeGame(6, 6)
        for _ in range(6):
            g.step()
        self.assertFalse(g.alive)


class MemoryTests(unittest.TestCase):
    def test_pairs_match_and_count_moves(self):
        g = MemoryGame(["a", "b"], rng=random.Random(0))
        a1, a2 = [i for i, f in enumerate(g.faces) if f == "a"]
        b1, b2 = [i for i, f in enumerate(g.faces) if f == "b"]
        self.assertEqual(g.flip(a1), "first")
        self.assertEqual(g.flip(b1), "miss")
        g.hide_misses()
        self.assertEqual(g.flip(a1), "first")
        self.assertEqual(g.flip(a2), "match")
        g.flip(b1)
        self.assertEqual(g.flip(b2), "match")
        self.assertTrue(g.done)
        self.assertEqual(g.moves, 3)

    def test_matched_or_open_cards_ignore_clicks(self):
        g = MemoryGame(["a", "b"], rng=random.Random(0))
        g.flip(0)
        self.assertIsNone(g.flip(0))


class TicTacToeTests(unittest.TestCase):
    def test_winner(self):
        self.assertEqual(winner(list("XXXOO    ")), "X")
        self.assertEqual(winner(list("XOXXOOOXX")), "draw")
        self.assertIsNone(winner(list("XO       ")))

    def test_hard_cpu_takes_the_win_and_blocks(self):
        g = TicTacToe(hard=True)
        g.board = list("OO XX    ")
        self.assertEqual(g.cpu_move(), 2)  # win beats blocking
        g.board = list("XX O     ")
        self.assertEqual(g.cpu_move(), 2)

    def test_hard_cpu_never_loses(self):
        def play(g):
            while not g.result:
                if g.turn == "X":
                    for i in range(9):
                        if g.board[i] == " ":
                            g.play(i)
                            break
                else:
                    g.play(g.cpu_move())
            return g.result

        for first in range(9):
            g = TicTacToe(hard=True)
            g.play(first)
            self.assertNotEqual(play(g), "X")


if __name__ == "__main__":
    unittest.main()
