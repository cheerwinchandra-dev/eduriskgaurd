"""Small SQLite helper layer (standard library only)."""
import sqlite3
from contextlib import contextmanager

import pandas as pd

from .common import DATA_DIR

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);

CREATE TABLE IF NOT EXISTS students (
    student_id TEXT PRIMARY KEY,
    program TEXT, mode TEXT,
    gender TEXT, first_generation INTEGER, financial_aid INTEGER,   -- fairness audit only
    entrance_score REAL,
    synced_at TEXT, sync_age_days REAL
);

CREATE TABLE IF NOT EXISTS records (
    student_id TEXT, term TEXT, term_number INTEGER,
    credit_load REAL, credit_ratio REAL, gpa REAL, prior_gpa REAL, failed_courses REAL,
    attendance_rate REAL, attendance_change REAL,
    assignment_completion REAL, assignment_change REAL,
    missed_submissions REAL, late_submissions REAL,
    lms_days REAL, lms_change REAL, inactive_weeks REAL,
    advising_visits REAL, fee_hold REAL, registration_delay_days REAL,
    outcome TEXT,
    PRIMARY KEY (student_id, term)
);

CREATE TABLE IF NOT EXISTS weekly (
    student_id TEXT, term TEXT, week INTEGER,
    attendance REAL, lms_days REAL, assign_done REAL,
    PRIMARY KEY (student_id, term, week)
);

CREATE TABLE IF NOT EXISTS predictions (
    student_id TEXT, term TEXT, probability REAL, model_version TEXT,
    created_at TEXT, retrospective INTEGER, contributions TEXT,
    PRIMARY KEY (student_id, term)
);

CREATE TABLE IF NOT EXISTS interventions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id TEXT, created_at TEXT, updated_at TEXT,
    type TEXT, channel TEXT, status TEXT, outcome TEXT, note TEXT, author TEXT
);

CREATE TABLE IF NOT EXISTS notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id TEXT, created_at TEXT, author TEXT, body TEXT
);

CREATE TABLE IF NOT EXISTS overrides (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id TEXT, created_at TEXT, reason TEXT, note TEXT, until TEXT
);

CREATE TABLE IF NOT EXISTS audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT, role TEXT, action TEXT, student_id TEXT, detail TEXT
);

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL, full_name TEXT NOT NULL, role TEXT NOT NULL,
    password_hash TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1, must_change INTEGER NOT NULL DEFAULT 0,
    created_at TEXT, created_by TEXT, last_login TEXT
);

CREATE INDEX IF NOT EXISTS idx_records_term ON records(term);
CREATE INDEX IF NOT EXISTS idx_interventions_student ON interventions(student_id);
CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit(ts);
"""


@contextmanager
def connect():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DATA_DIR / "eduguard.db", timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def init():
    with connect() as con:
        con.executescript(SCHEMA)


def query(sql, params=()):
    with connect() as con:
        return [dict(r) for r in con.execute(sql, params).fetchall()]


def one(sql, params=()):
    rows = query(sql, params)
    return rows[0] if rows else None


def execute(sql, params=()):
    with connect() as con:
        return con.execute(sql, params).lastrowid


def frame(sql, params=()):
    with connect() as con:
        return pd.read_sql_query(sql, con, params=params)


def write_frame(table, df, replace=False):
    with connect() as con:
        if replace:
            con.execute(f"DELETE FROM {table}")
        df.to_sql(table, con, if_exists="append", index=False, chunksize=5000)


def get_meta(key, default=None):
    row = one("SELECT value FROM meta WHERE key=?", (key,))
    return row["value"] if row else default


def set_meta(key, value):
    execute("INSERT INTO meta(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, str(value)))


def clear_all():
    with connect() as con:
        for table in ("weekly", "predictions", "interventions", "notes", "overrides", "records", "students"):
            con.execute(f"DELETE FROM {table}")
