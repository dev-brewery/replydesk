"""SQLite account store (ARCHITECTURE section 13, T26).

Stdlib only. Passwords are hashed with PBKDF2-HMAC-SHA256 (120k iterations,
16-byte per-user salt); sessions are opaque url-safe tokens that expire 30
days after issue. One short-lived sqlite3 connection per operation so the
store is safe under the threaded API server.

Plaintext passwords are never stored, logged, or returned by any function.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

PBKDF2_ITERATIONS = 120_000
SALT_BYTES = 16
KEY_BYTES = 32
SESSION_TTL = timedelta(days=30)


def now() -> datetime:
    """Injectable clock (tests monkeypatch this)."""
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass(frozen=True)
class User:
    id: int
    email: str
    name: str
    created_on: str  # ISO-8601 UTC
    plan: str  # 'founding_trial'
    plan_status: str  # 'trial_active'


class AccountsError(Exception):
    pass


class DuplicateEmailError(AccountsError):
    pass


_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  email         TEXT NOT NULL UNIQUE COLLATE NOCASE,
  name          TEXT NOT NULL,
  password_hash TEXT NOT NULL,
  salt          TEXT NOT NULL,
  created_on    TEXT NOT NULL,
  plan          TEXT NOT NULL DEFAULT 'founding_trial',
  plan_status   TEXT NOT NULL DEFAULT 'trial_active',
  stripe_customer_id     TEXT NULL,
  stripe_subscription_id TEXT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
  token      TEXT PRIMARY KEY,
  user_id    INTEGER NOT NULL,
  created_on TEXT NOT NULL,
  expires_on TEXT NOT NULL
);
"""


class _ClosingConnection:
    """Context manager: commit on success, always close (Windows file locks)."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def __enter__(self) -> sqlite3.Connection:
        return self._conn

    def __exit__(self, exc_type, exc, tb) -> None:
        if exc_type is None:
            self._conn.commit()
        self._conn.close()


def _hash_password(password: str, salt_hex: str) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex),
        PBKDF2_ITERATIONS, dklen=KEY_BYTES,
    ).hex()


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _row_to_user(row: sqlite3.Row) -> User:
    return User(
        id=row["id"], email=row["email"], name=row["name"],
        created_on=row["created_on"], plan=row["plan"],
        plan_status=row["plan_status"],
    )


class AccountStore:
    def __init__(self, path: str) -> None:
        self._path = path
        parent = os.path.dirname(os.path.abspath(path))
        os.makedirs(parent, exist_ok=True)
        with self._open() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.executescript(_SCHEMA)

    def _open(self) -> sqlite3.Connection:
        """Short-lived connection, committed and closed on exit."""
        conn = sqlite3.connect(self._path, timeout=5)
        conn.row_factory = sqlite3.Row
        return _ClosingConnection(conn)

    def create_user(self, name: str, email: str, password: str) -> User:
        email = _normalize_email(email)
        name = name.strip()
        salt = secrets.token_bytes(SALT_BYTES).hex()
        created = _iso(now())
        pw_hash = _hash_password(password, salt)
        try:
            with self._open() as conn:
                cur = conn.execute(
                    "INSERT INTO users (email, name, password_hash, salt,"
                    " created_on) VALUES (?, ?, ?, ?, ?)",
                    (email, name, pw_hash, salt, created),
                )
                user_id = cur.lastrowid
        except sqlite3.IntegrityError as exc:
            raise DuplicateEmailError(
                "An account with that email already exists."
            ) from exc
        return User(id=user_id, email=email, name=name, created_on=created,
                    plan="founding_trial", plan_status="trial_active")

    def authenticate(self, email: str, password: str) -> User | None:
        with self._open() as conn:
            row = conn.execute(
                "SELECT * FROM users WHERE email = ?",
                (_normalize_email(email),),
            ).fetchone()
        if row is None:
            return None
        candidate = _hash_password(password, row["salt"])
        if not hmac.compare_digest(candidate, row["password_hash"]):
            return None
        return _row_to_user(row)

    def issue_session(self, user_id: int) -> str:
        token = secrets.token_urlsafe(32)
        issued = now()
        with self._open() as conn:
            conn.execute(
                "INSERT INTO sessions (token, user_id, created_on,"
                " expires_on) VALUES (?, ?, ?, ?)",
                (token, user_id, _iso(issued), _iso(issued + SESSION_TTL)),
            )
        return token

    def validate_session(self, token: str) -> User | None:
        with self._open() as conn:
            row = conn.execute(
                "SELECT u.*, s.expires_on FROM sessions s"
                " JOIN users u ON u.id = s.user_id WHERE s.token = ?",
                (token,),
            ).fetchone()
            if row is None:
                return None
            if _iso(now()) >= row["expires_on"]:
                conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
                return None
        return _row_to_user(row)

    def revoke_session(self, token: str) -> None:
        with self._open() as conn:
            conn.execute("DELETE FROM sessions WHERE token = ?", (token,))


def user_json(user: User) -> dict:
    """Serialize for API responses — never hash, salt, or token."""
    return {
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "created_on": user.created_on,
        "plan": user.plan,
        "plan_status": user.plan_status,
    }
