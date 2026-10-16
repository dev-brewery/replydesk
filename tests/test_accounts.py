"""Tests for replydesk.accounts (T26). Offline, temp-dir DBs only."""

from datetime import datetime, timedelta, timezone
import os
import sqlite3
import tempfile
import unittest
from unittest import mock

from replydesk import accounts
from replydesk.accounts import (
    AccountStore,
    DuplicateEmailError,
    user_json,
)


class AccountsTestBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db_path = os.path.join(self.tmp.name, "accounts.db")
        self.store = AccountStore(self.db_path)

    def set_clock(self, dt):
        patcher = mock.patch.object(accounts, "now", return_value=dt)
        patcher.start()
        self.addCleanup(patcher.stop)
        return dt


class TestSignupLoginRoundTrip(AccountsTestBase):
    def test_create_then_authenticate(self):
        user = self.store.create_user("Ada", "Ada@Example.com ", "s3cretpass")
        self.assertEqual(user.email, "ada@example.com")
        self.assertEqual(user.name, "Ada")
        self.assertEqual(user.plan, "founding_trial")
        self.assertEqual(user.plan_status, "trial_active")
        got = self.store.authenticate("ada@example.com", "s3cretpass")
        self.assertEqual(got.id, user.id)

    def test_wrong_password_returns_none(self):
        self.store.create_user("Ada", "ada@example.com", "s3cretpass")
        self.assertIsNone(self.store.authenticate("ada@example.com", "wrongpass"))

    def test_unknown_email_returns_none(self):
        self.assertIsNone(self.store.authenticate("nobody@example.com", "whatever1"))

    def test_duplicate_email_case_insensitive(self):
        self.store.create_user("Ada", "ada@example.com", "s3cretpass")
        with self.assertRaises(DuplicateEmailError):
            self.store.create_user("Ada2", "ADA@EXAMPLE.COM", "otherpass1")


class TestSessions(AccountsTestBase):
    def test_issue_validate_revoke(self):
        user = self.store.create_user("Ada", "ada@example.com", "s3cretpass")
        token = self.store.issue_session(user.id)
        self.assertTrue(token)
        self.assertEqual(self.store.validate_session(token).id, user.id)
        self.store.revoke_session(token)
        self.assertIsNone(self.store.validate_session(token))

    def test_expired_session_invalid_and_deleted(self):
        issued_at = self.set_clock(datetime(2026, 10, 17, tzinfo=timezone.utc))
        user = self.store.create_user("Ada", "ada@example.com", "s3cretpass")
        token = self.store.issue_session(user.id)
        # Still valid just before 30 days.
        self.set_clock(issued_at + timedelta(days=29, hours=23))
        self.assertIsNotNone(self.store.validate_session(token))
        # Invalid after expiry; row is lazily deleted.
        self.set_clock(issued_at + timedelta(days=30, seconds=1))
        self.assertIsNone(self.store.validate_session(token))
        conn = sqlite3.connect(self.db_path)
        try:
            count = conn.execute(
                "SELECT COUNT(*) FROM sessions WHERE token = ?", (token,)
            ).fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(count, 0)

    def test_token_is_32_byte_urlsafe(self):
        user = self.store.create_user("Ada", "ada@example.com", "s3cretpass")
        token = self.store.issue_session(user.id)
        self.assertGreaterEqual(len(token), 40)  # token_urlsafe(32) ~ 43 chars
        self.assertTrue(all(c.isalnum() or c in "-_" for c in token))


class TestStoreProperties(AccountsTestBase):
    def test_wal_mode_on(self):
        conn = sqlite3.connect(self.db_path)
        try:
            mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(mode.lower(), "wal")

    def test_wal_artifacts_confined_to_temp_dir(self):
        self.store.create_user("Ada", "ada@example.com", "s3cretpass")
        self.store.issue_session(1)
        names = set(os.listdir(self.tmp.name))
        self.assertTrue(names)
        for name in names:
            self.assertTrue(
                name.startswith("accounts.db"),
                f"unexpected artifact outside temp dir: {name}",
            )

    def test_schema_has_inert_stripe_columns(self):
        conn = sqlite3.connect(self.db_path)
        try:
            cols = {
                row[1]: row
                for row in conn.execute("PRAGMA table_info(users)").fetchall()
            }
            self.assertIn("stripe_customer_id", cols)
            self.assertIn("stripe_subscription_id", cols)
            self.assertEqual(cols["stripe_customer_id"][3], 0)  # nullable
            self.assertEqual(cols["stripe_subscription_id"][3], 0)
            # no code path populates them
            for row in conn.execute(
                "SELECT stripe_customer_id, stripe_subscription_id FROM users"
            ):
                self.assertIsNone(row[0])
                self.assertIsNone(row[1])
        finally:
            conn.close()

    def test_no_plaintext_password_stored(self):
        self.store.create_user("Ada", "ada@example.com", "s3cretpass")
        with open(self.db_path, "rb") as fh:
            blob = fh.read()
        self.assertNotIn(b"s3cretpass", blob)

    def test_user_json_never_contains_hash_salt_or_token(self):
        user = self.store.create_user("Ada", "ada@example.com", "s3cretpass")
        token = self.store.issue_session(user.id)
        data = user_json(user)
        self.assertEqual(
            set(data),
            {"id", "email", "name", "created_on", "plan", "plan_status"},
        )
        self.assertNotIn(token, str(data))


if __name__ == "__main__":
    unittest.main()
