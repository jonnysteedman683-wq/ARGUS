"""Database connection + schema bootstrap.

v1 ships a SQLite backend (zero-setup, testable anywhere). The connection is
opened from a ``DATABASE_URL`` of the form ``sqlite:///path/to.db`` or
``sqlite:///:memory:``. A TimescaleDB backend slots in behind the same
Repository API later (see schema_timescale.sql).
"""

from __future__ import annotations

import sqlite3
from importlib import resources
from pathlib import Path


def _sqlite_path(database_url: str) -> str:
    # sqlite:///argus.db  ->  argus.db ;  sqlite:///:memory:  ->  :memory:
    tail = database_url.split("sqlite:///", 1)[1]
    return tail or ":memory:"


def connect(database_url: str) -> sqlite3.Connection:
    if not database_url.startswith("sqlite"):
        raise NotImplementedError(
            "v1 ships the SQLite backend only; a TimescaleDB backend is planned. "
            f"Got DATABASE_URL={database_url!r}"
        )
    path = _sqlite_path(database_url)
    if path not in (":memory:",):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    sql = resources.files("argus.store").joinpath("schema_sqlite.sql").read_text()
    conn.executescript(sql)
    conn.commit()
