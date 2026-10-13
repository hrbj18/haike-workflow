"""SQLite serializes local sandbox writes. Production needs PostgreSQL migrations/locks."""

import hashlib
import json
import os
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path


def now():
    return datetime.now(UTC).isoformat(timespec="microseconds")


def later(seconds):
    return (datetime.now(UTC) + timedelta(seconds=seconds)).isoformat(
        timespec="microseconds"
    )


def uid(prefix):
    return prefix + "_" + secrets.token_hex(12)


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


class Problem(Exception):
    def __init__(self, status, code, message):
        self.status, self.code, self.message = status, code, message
        super().__init__(message)


class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def connect(self):
        db = sqlite3.connect(self.path, timeout=20, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA busy_timeout=20000")
        return db

    def initialize(self):
        with self.read() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript(Path(__file__).with_name("schema.sql").read_text())
        if os.name != "nt":
            os.chmod(self.path, 0o600)

    @contextmanager
    def read(self):
        db = self.connect()
        try:
            yield db
        finally:
            db.close()

    @contextmanager
    def write(self):
        with self.read() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                yield db
                db.commit()
            except BaseException:
                db.rollback()
                raise


def owned(db, table, resource_id, user_id):
    # Table names are internal constants, never user input.
    row = db.execute(
        f"SELECT * FROM {table} WHERE id=? AND user_id=?", (resource_id, user_id)
    ).fetchone()
    if row is None:
        raise Problem(404, "not_found", "记录不存在")
    return row


def post(db, user_id, event_key, kind, reference, entries):
    """The only write path for money. Entries use signed liability balances in micros."""
    existing = db.execute(
        "SELECT id FROM vouchers WHERE event_key=?", (event_key,)
    ).fetchone()
    if existing:
        return existing["id"]
    if sum(entries.values()) != 0 or any(type(v) is not int for v in entries.values()):
        raise ValueError("unbalanced voucher")
    wallet = db.execute("SELECT * FROM wallets WHERE user_id=?", (user_id,)).fetchone()
    available = wallet["available"] + entries.get("available", 0)
    reserved = wallet["reserved"] + entries.get("reserved", 0)
    if available < 0 or reserved < 0 or available + reserved > 10**12:
        raise Problem(409, "wallet_limit", "余额不足或超过本地演示限额")
    voucher_id = uid("vch")
    db.execute(
        "INSERT INTO vouchers VALUES(?,?,?,?,?,?,?,?)",
        (
            voucher_id,
            event_key,
            user_id,
            kind,
            reference,
            now(),
            available,
            reserved,
        ),
    )
    db.executemany(
        "INSERT INTO postings(voucher_id,account,amount) VALUES(?,?,?)",
        ((voucher_id, account, amount) for account, amount in entries.items()),
    )
    db.execute(
        "UPDATE wallets SET available=?,reserved=? WHERE user_id=?",
        (available, reserved, user_id),
    )
    return voucher_id


def audit(db, actor, action, resource):
    db.execute(
        "INSERT INTO audit VALUES(?,?,?,?,?)",
        (uid("aud"), actor, action, resource, now()),
    )
