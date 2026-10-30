"""Create the SQLite schema and seed sample evaluation criteria.

Safe to run repeatedly: tables use IF NOT EXISTS and criteria are inserted
only when a criterion with the same name is missing.

    python db/seed.py
"""
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = ROOT / "data" / "rfp.db"
SCHEMA = Path(__file__).resolve().parent / "schema.sql"

# (name, description, weight, max_score) - active weights total 100.
SAMPLE_CRITERIA = [
    ("Technical Capability",
     "Architecture, integrations, scalability, technical fit", 30, 10),
    ("Implementation Plan",
     "Timeline, milestones, staffing, risk plan", 20, 10),
    ("Commercial Value",
     "Pricing clarity, total cost, assumptions", 20, 10),
    ("Security & Compliance",
     "Controls, certifications, privacy, auditability", 20, 10),
    ("Support & Experience",
     "Support model, similar projects, references", 10, 10),
]


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA.read_text())
    for name, description, weight, max_score in SAMPLE_CRITERIA:
        conn.execute(
            "INSERT OR IGNORE INTO evaluation_criteria "
            "(name, description, weight, max_score, is_active) VALUES (?, ?, ?, ?, 1)",
            (name, description, weight, max_score),
        )
    conn.commit()


if __name__ == "__main__":
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_DB
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as connection:
        init_db(connection)
    print(f"Database ready: {path}")
