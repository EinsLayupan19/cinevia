import sqlite3
import unittest

from cinevia import auth, db


def memory_db() -> sqlite3.Connection:
    conn = db.connect(":memory:")
    db.migrate(conn)
    return conn


class HashingTests(unittest.TestCase):
    def test_same_password_gets_different_salts_and_hashes(self):
        salt_a, hash_a = auth.hash_password("correct horse", iterations=1_000)
        salt_b, hash_b = auth.hash_password("correct horse", iterations=1_000)
        self.assertNotEqual(salt_a, salt_b)
        self.assertNotEqual(hash_a, hash_b)
        self.assertEqual(len(salt_a), auth.SALT_BYTES)

    def test_verify_accepts_right_password_only(self):
        salt, digest = auth.hash_password("correct horse", iterations=1_000)
        self.assertTrue(auth.verify_password("correct horse", salt, digest, 1_000))
        self.assertFalse(auth.verify_password("Correct horse", salt, digest, 1_000))
        self.assertFalse(auth.verify_password("", salt, digest, 1_000))


class ValidationTests(unittest.TestCase):
    def test_username_rules(self):
        self.assertIsNone(auth.username_problem("nathan_c"))
        self.assertIsNotNone(auth.username_problem("ab"))
        self.assertIsNotNone(auth.username_problem("has space"))
        self.assertIsNotNone(auth.username_problem("x" * 31))

    def test_password_rules(self):
        self.assertIsNone(auth.password_problem("longenough1"))
        self.assertIsNotNone(auth.password_problem("short1"))
        self.assertIsNotNone(auth.password_problem("onlyletters"))
        self.assertIsNotNone(auth.password_problem("x" * 129))


class AccountTests(unittest.TestCase):
    def setUp(self):
        self.conn = memory_db()
        self.accounts = auth.Accounts(self.conn, iterations=1_000)

    def test_register_stores_hash_not_password(self):
        user = self.accounts.register("Nathan", "movienight42")
        self.assertEqual(user.username, "Nathan")
        row = self.conn.execute("SELECT * FROM users WHERE id = ?", (user.id,)).fetchone()
        stored = b"".join(v if isinstance(v, bytes) else str(v).encode() for v in tuple(row))
        self.assertNotIn(b"movienight42", stored)
        self.assertEqual(len(row["password_hash"]), 32)

    def test_usernames_are_unique_ignoring_case(self):
        self.accounts.register("Nathan", "movienight42")
        with self.assertRaises(auth.AuthError) as ctx:
            self.accounts.register("nathan", "anotherpass9")
        self.assertIn("taken", str(ctx.exception))

    def test_register_rejects_weak_input(self):
        with self.assertRaises(auth.AuthError):
            self.accounts.register("ok_name", "short")
        with self.assertRaises(auth.AuthError):
            self.accounts.register("no", "movienight42")

    def test_login_with_right_and_wrong_password(self):
        self.accounts.register("Nathan", "movienight42")
        self.assertEqual(self.accounts.login("nathan", "movienight42").username, "Nathan")
        with self.assertRaises(auth.AuthError) as ctx:
            self.accounts.login("Nathan", "wrongpass99")
        self.assertEqual(str(ctx.exception), auth.BAD_LOGIN)

    def test_unknown_user_gets_same_message(self):
        with self.assertRaises(auth.AuthError) as ctx:
            self.accounts.login("ghost", "whatever123")
        self.assertEqual(str(ctx.exception), auth.BAD_LOGIN)

    def test_lockout_after_repeated_failures(self):
        clock = [1000.0]
        accounts = auth.Accounts(self.conn, iterations=1_000, now=lambda: clock[0])
        accounts.register("Nathan", "movienight42")
        for _ in range(auth.MAX_FAILURES):
            with self.assertRaises(auth.AuthError):
                accounts.login("Nathan", "wrongpass99")
        with self.assertRaises(auth.AuthError) as ctx:
            accounts.login("Nathan", "movienight42")  # right password, still locked
        self.assertIn("Too many attempts", str(ctx.exception))
        clock[0] += auth.LOCKOUT_SECONDS + 1
        self.assertEqual(accounts.login("Nathan", "movienight42").username, "Nathan")


class LibraryTests(unittest.TestCase):
    def setUp(self):
        self.conn = memory_db()
        accounts = auth.Accounts(self.conn, iterations=1_000)
        self.alice = accounts.register("alice", "movienight42")
        self.bob = accounts.register("bob", "movienight42")

    def test_favorites_are_per_user(self):
        title = {"id": "m:1", "title": "Verity"}
        db.add_favorite(self.conn, self.alice.id, title)
        self.assertEqual([t["id"] for t in db.favorites(self.conn, self.alice.id)], ["m:1"])
        self.assertEqual(db.favorites(self.conn, self.bob.id), [])
        db.remove_favorite(self.conn, self.alice.id, "m:1")
        self.assertEqual(db.favorites(self.conn, self.alice.id), [])

    def test_history_dedupes_and_orders_newest_first(self):
        db.add_search(self.conn, self.alice.id, "dune", at=1)
        db.add_search(self.conn, self.alice.id, "from", at=2)
        db.add_search(self.conn, self.alice.id, "Dune", at=3)
        self.assertEqual([h.query for h in db.history(self.conn, self.alice.id)], ["Dune", "from"])
        db.clear_history(self.conn, self.alice.id)
        self.assertEqual(db.history(self.conn, self.alice.id), [])

    def test_theme_preference(self):
        self.assertEqual(db.theme(self.conn, self.alice.id), "dark")
        db.set_theme(self.conn, self.alice.id, "light")
        self.assertEqual(db.theme(self.conn, self.alice.id), "light")


if __name__ == "__main__":
    unittest.main()
