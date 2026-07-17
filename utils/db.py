"""Lightweight SQLite store — request logs and call transcripts."""
import json
import sqlite3
from datetime import datetime
from pathlib import Path

DB_PATH = Path("logs/ronny.db")


def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS request_logs (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                ts          TEXT    NOT NULL,
                input_type  TEXT,
                transcript  TEXT,
                reply       TEXT,
                status      TEXT    NOT NULL,
                error       TEXT,
                stt_ms      INTEGER DEFAULT 0,
                llm_ms      INTEGER DEFAULT 0,
                tts_ms      INTEGER DEFAULT 0,
                total_ms    INTEGER DEFAULT 0
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS call_logs (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                call_id      TEXT    UNIQUE NOT NULL,
                ts           TEXT    NOT NULL,
                contact      TEXT,
                phone        TEXT,
                mission      TEXT,
                status       TEXT    NOT NULL,
                response     TEXT,
                summary      TEXT,
                transcript   TEXT,
                completed_at TEXT
            )
        """)
        conn.commit()


def log_call(
    *,
    call_id: str,
    contact: str | None,
    phone: str | None,
    mission: str | None,
    status: str,
    response: str | None = None,
    summary: str | None = None,
    transcript: list | None = None,
    completed_at: str | None = None,
    started_at: str | None = None,
) -> None:
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                """
                INSERT INTO call_logs
                    (call_id, ts, contact, phone, mission, status, response, summary, transcript, completed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(call_id) DO UPDATE SET
                    status       = excluded.status,
                    response     = excluded.response,
                    summary      = excluded.summary,
                    transcript   = excluded.transcript,
                    completed_at = excluded.completed_at
                """,
                (
                    call_id,
                    started_at or datetime.now().isoformat(timespec="milliseconds"),
                    contact,
                    phone,
                    mission,
                    status,
                    response,
                    summary,
                    json.dumps(transcript) if transcript else None,
                    completed_at,
                ),
            )
            conn.commit()
    except Exception:
        pass


def get_call_logs(limit: int = 100) -> list[dict]:
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM call_logs ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            if d.get("transcript"):
                try:
                    d["transcript"] = json.loads(d["transcript"])
                except Exception:
                    d["transcript"] = []
            result.append(d)
        return result
    except Exception:
        return []


def log_request(
    *,
    input_type: str,
    transcript: str | None,
    reply: str | None,
    status: str,
    error: str | None = None,
    stt_ms: int = 0,
    llm_ms: int = 0,
    tts_ms: int = 0,
    total_ms: int = 0,
) -> None:
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                """
                INSERT INTO request_logs
                    (ts, input_type, transcript, reply, status, error,
                     stt_ms, llm_ms, tts_ms, total_ms)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    datetime.now().isoformat(timespec="milliseconds"),
                    input_type,
                    transcript,
                    reply,
                    status,
                    error,
                    stt_ms,
                    llm_ms,
                    tts_ms,
                    total_ms,
                ),
            )
            conn.commit()
    except Exception:
        pass  # never let logging crash the server


def get_recent_logs(limit: int = 100) -> list[dict]:
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM request_logs ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]
    except Exception:
        return []
