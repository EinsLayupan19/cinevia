import unittest
from datetime import date, datetime

from cinevia.data import catalog
from cinevia.data.catalog import OLDER, Filters, apply_filters, buckets_of, matches_query, merge_titles, year_options
from cinevia.data.itunes import artwork, parse_lookup_movie, parse_movie_entry
from cinevia.data.models import Title
from cinevia.data.tvmaze import parse_show
from cinevia.data.util import format_runtime, format_when, normalize_name, strip_html, youtube_search_url

ART = "https://is1-ssl.mzstatic.com/image/thumb/Video211/v4/f3/a5/2000x3000_Verity.jpg/115x170bb.png"

RSS_ENTRY = {
    "im:name": {"label": "Verity"},
    "im:image": [{"label": ART.replace("115x170", "40x60")}, {"label": ART}],
    "summary": {"label": "A ghostwriter finds a chilling manuscript."},
    "link": [
        {"attributes": {"rel": "alternate", "type": "text/html", "href": "https://itunes.apple.com/us/movie/verity/id1"}},
        {
            "attributes": {
                "rel": "enclosure",
                "type": "video/x-m4v",
                "href": "https://video-ssl.itunes.apple.com/trailer.m4v",
                "im:assetType": "preview",
            }
        },
    ],
    "id": {"label": "https://itunes.apple.com/us/movie/verity/id6808034868", "attributes": {"im:id": "6808034868"}},
    "im:artist": {"label": "Michael Showalter"},
    "category": {"attributes": {"term": "Thriller", "label": "Thriller"}},
    "im:releaseDate": {"label": "2026-10-02T00:00:00-07:00"},
}

MAZE_SHOW = {
    "id": 54723,
    "url": "https://www.tvmaze.com/shows/54723/from",
    "name": "FROM",
    "genres": ["Drama", "Horror", "Science-Fiction"],
    "premiered": "2022-02-20",
    "averageRuntime": 51,
    "rating": {"average": 7.8},
    "weight": 100,
    "network": None,
    "webChannel": {"name": "MGM+"},
    "image": {"medium": "https://static.tvmaze.com/m.jpg", "original": "https://static.tvmaze.com/o.jpg"},
    "summary": "<p>Unravel the mystery of a <b>nightmarish</b> town &amp; its rules.</p>",
}


class UtilTests(unittest.TestCase):
    def test_strip_html(self):
        self.assertEqual(strip_html("<p>Tom &amp; Jerry&#39;s <i>chase</i></p>"), "Tom & Jerry's chase")
        self.assertEqual(strip_html(None), "")

    def test_normalize_name(self):
        self.assertEqual(normalize_name("FROM"), normalize_name("From"))
        self.assertEqual(normalize_name("The Bear"), "bear")
        self.assertEqual(normalize_name("Law & Order"), normalize_name("Law and Order"))

    def test_format_runtime(self):
        self.assertEqual(format_runtime(138), "2h 18m")
        self.assertEqual(format_runtime(45), "45m")
        self.assertEqual(format_runtime(120), "2h")
        self.assertIsNone(format_runtime(None))

    def test_format_when(self):
        now = datetime(2026, 11, 2, 20, 0)
        self.assertEqual(format_when(datetime(2026, 11, 2, 10, 2).timestamp(), now), "Today, 10:02 AM")
        self.assertEqual(format_when(datetime(2026, 11, 1, 21, 41).timestamp(), now), "Yesterday, 9:41 PM")
        self.assertEqual(format_when(datetime(2026, 3, 18, 18, 10).timestamp(), now), "Mar 18, 6:10 PM")

    def test_youtube_link(self):
        self.assertEqual(
            youtube_search_url("The Bear", "tv"),
            "https://www.youtube.com/results?search_query=The%20Bear%20official%20series%20trailer",
        )


class ParserTests(unittest.TestCase):
    def test_artwork_resize(self):
        self.assertTrue(artwork(ART, 400, 600).endswith("2000x3000_Verity.jpg/400x600bb.jpg"))
        self.assertTrue(artwork(ART, 1600, 900, "cc").endswith("/1600x900cc.jpg"))

    def test_chart_entry_with_trailer(self):
        t = parse_movie_entry(RSS_ENTRY, 0)
        self.assertEqual(t.id, "m:6808034868")
        self.assertEqual((t.title, t.year, t.genres), ("Verity", 2026, ["Thriller"]))
        self.assertEqual(t.trailer, "https://video-ssl.itunes.apple.com/trailer.m4v")
        self.assertEqual(t.credit, "Michael Showalter")
        self.assertTrue(t.poster.endswith("400x600bb.jpg"))

    def test_chart_entry_with_single_link(self):
        entry = dict(RSS_ENTRY, link={"attributes": {"rel": "alternate", "href": "https://x"}})
        self.assertIsNone(parse_movie_entry(entry, 3).trailer)

    def test_lookup_movie(self):
        t = parse_lookup_movie(
            {
                "kind": "feature-movie",
                "trackId": 6808034868,
                "trackName": "Verity",
                "artworkUrl100": ART.replace("115x170bb.png", "100x100bb.jpg"),
                "releaseDate": "2026-10-02T07:00:00Z",
                "trackTimeMillis": 7030834,
                "contentAdvisoryRating": "R",
                "primaryGenreName": "Thriller",
                "shortDescription": "Short.",
            }
        )
        self.assertEqual((t.id, t.year, t.runtime_min, t.certification, t.summary), ("m:6808034868", 2026, 117, "R", "Short."))
        self.assertIsNone(parse_lookup_movie({"kind": "tv-episode", "trackId": 1, "trackName": "x"}))

    def test_show(self):
        t = parse_show(MAZE_SHOW, 42)
        self.assertEqual((t.id, t.kind, t.year, t.rating, t.runtime_min), ("t:54723", "tv", 2022, 7.8, 51))
        self.assertEqual(t.credit, "MGM+")
        self.assertEqual(t.itunes_collection_id, 42)
        self.assertEqual(t.summary, "Unravel the mystery of a nightmarish town & its rules.")

    def test_round_trip_through_dict(self):
        t = parse_show(MAZE_SHOW)
        self.assertEqual(Title.from_dict(t.to_dict()), t)
        self.assertEqual(t.with_details({"backdrop": "b.jpg", "cast": []}).backdrop, "b.jpg")


def movie(id_: str, genres: list[str], popularity: float) -> Title:
    return Title(id=id_, kind="movie", source_id=1, title=f"Movie {id_}", genres=genres, popularity=popularity)


class CatalogTests(unittest.TestCase):
    def test_merge_keeps_genres_and_best_rank(self):
        merged = merge_titles([[movie("m:1", ["Drama"], 990)], [movie("m:1", ["Thriller"], 999), movie("m:2", [], 1)]])
        self.assertEqual(len(merged), 2)
        self.assertEqual((merged[0].genres, merged[0].popularity), (["Drama", "Thriller"], 999))

    def test_buckets(self):
        self.assertEqual(buckets_of(parse_show(MAZE_SHOW)), ["Drama", "Horror", "Science Fiction"])
        self.assertEqual(buckets_of(movie("m:3", ["Sci-Fi & Fantasy"], 0)), ["Fantasy", "Science Fiction"])

    def test_query_match(self):
        t = parse_movie_entry(RSS_ENTRY, 0)
        self.assertTrue(matches_query(t, "veri"))
        self.assertTrue(matches_query(t, "showalter"))
        self.assertFalse(matches_query(t, "dune"))
        self.assertFalse(matches_query(t, "  "))


class FilterTests(unittest.TestCase):
    today = date(2026, 11, 2)

    def setUp(self):
        self.film = parse_movie_entry(RSS_ENTRY, 0)
        self.show = parse_show(MAZE_SHOW)
        self.old = parse_show(dict(MAZE_SHOW, id=9, name="Twin Peaks", premiered="1990-04-08", rating={"average": 8.6}, weight=99))
        self.all = [self.film, self.show, self.old]

    def names(self, f: Filters) -> list[str]:
        return [t.title for t in apply_filters(self.all, f, self.today)]

    def test_default_is_popularity(self):
        self.assertEqual(self.names(Filters()), ["Verity", "FROM", "Twin Peaks"])

    def test_filters(self):
        self.assertEqual(len(self.names(Filters(type="TV Shows"))), 2)
        self.assertEqual(self.names(Filters(genre="Thriller")), ["Verity"])
        self.assertEqual(self.names(Filters(year="2022")), ["FROM"])
        self.assertEqual(self.names(Filters(year=OLDER)), ["Twin Peaks"])
        self.assertEqual(self.names(Filters(rating="8+")), ["Twin Peaks"])

    def test_query_and_sort(self):
        self.assertEqual(self.names(Filters(query="peaks")), ["Twin Peaks"])
        self.assertEqual(self.names(Filters(sort="Oldest First"))[0], "Twin Peaks")
        self.assertEqual(self.names(Filters(sort="Alphabetical (A-Z)"))[0], "FROM")

    def test_year_options(self):
        self.assertEqual(year_options(self.today), ["All Years", "2026", "2025", "2024", "2023", "2022", OLDER])

    def test_genre_options_match_buckets(self):
        self.assertEqual(catalog.GENRE_OPTIONS[1:], list(catalog.GENRE_BUCKETS))


if __name__ == "__main__":
    unittest.main()
