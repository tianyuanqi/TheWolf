from __future__ import annotations

import os
import sqlite3
from pathlib import Path


DEMO_DOCUMENT_ID = "demo-announcement-0001"


def data_root() -> Path:
    """Return the isolated local data directory used by the development service."""
    configured = os.environ.get("WOLF_DATA_ROOT")
    if configured:
        return Path(configured).expanduser()
    return Path.home() / ".local" / "share" / "thewolf"


def connect() -> sqlite3.Connection:
    root = data_root()
    root.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(root / "metadata.sqlite")
    connection.row_factory = sqlite3.Row
    return connection


def initialize_demo_data() -> None:
    """Create the minimum persistent metadata used to exercise the local stack."""
    with connect() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS instruments (
                instrument_id TEXT PRIMARY KEY,
                display_name TEXT NOT NULL,
                exchange TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS daily_bars (
                instrument_id TEXT NOT NULL,
                trade_date TEXT NOT NULL,
                close_price REAL NOT NULL,
                currency TEXT NOT NULL,
                source_name TEXT NOT NULL,
                PRIMARY KEY (instrument_id, trade_date)
            );
            CREATE TABLE IF NOT EXISTS documents (
                document_id TEXT PRIMARY KEY,
                issuer_name TEXT NOT NULL,
                title TEXT NOT NULL,
                published_at TEXT NOT NULL,
                source_url TEXT NOT NULL,
                evidence_page INTEGER NOT NULL,
                evidence_text TEXT NOT NULL
            );
            """
        )
        connection.execute(
            "INSERT OR IGNORE INTO instruments VALUES (?, ?, ?)",
            ("demo-600519", "样本公司", "SSE"),
        )
        connection.execute(
            "INSERT OR IGNORE INTO daily_bars VALUES (?, ?, ?, ?, ?)",
            ("demo-600519", "2026-09-18", 100.0, "CNY", "development fixture"),
        )
        connection.execute(
            "INSERT OR IGNORE INTO documents VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                DEMO_DOCUMENT_ID,
                "样本公司",
                "样本公告（本地验证用）",
                "2026-09-18T18:00:00+08:00",
                "https://example.invalid/thewolf-demo-announcement",
                1,
                "本文件仅用于验证本地证据定位链路，不构成任何投资结论。",
            ),
        )


def demo_research() -> dict:
    with connect() as connection:
        row = connection.execute(
            """
            SELECT i.instrument_id, i.display_name, i.exchange, b.trade_date,
                   b.close_price, b.currency, b.source_name
            FROM instruments i
            JOIN daily_bars b ON b.instrument_id = i.instrument_id
            WHERE i.instrument_id = ?
            """,
            ("demo-600519",),
        ).fetchone()
    if row is None:
        raise RuntimeError("demo data was not initialized")
    return dict(row) | {"document_id": DEMO_DOCUMENT_ID}


def document_evidence(document_id: str) -> dict | None:
    with connect() as connection:
        row = connection.execute(
            "SELECT * FROM documents WHERE document_id = ?", (document_id,)
        ).fetchone()
    return dict(row) if row else None
