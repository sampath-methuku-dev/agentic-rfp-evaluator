"""All SQLite reads and writes live here."""
import json
import sqlite3
from pathlib import Path

from db.seed import init_db
from src.config import DB_PATH
from src.models import Criterion


def connect(path: Path | None = None) -> sqlite3.Connection:
    """Open the database, creating and seeding it if it does not exist yet."""
    path = Path(path or DB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    init_db(conn)
    return conn


def _to_criterion(row: sqlite3.Row) -> Criterion:
    return Criterion(row["criterion_id"], row["name"], row["description"],
                     float(row["weight"]), float(row["max_score"]))


def load_active_criteria(conn: sqlite3.Connection) -> list[Criterion]:
    rows = conn.execute(
        "SELECT * FROM evaluation_criteria WHERE is_active = 1 ORDER BY criterion_id"
    ).fetchall()
    return [_to_criterion(r) for r in rows]


def load_all_criteria(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM evaluation_criteria ORDER BY criterion_id").fetchall()


def save_run(conn: sqlite3.Connection, run: dict) -> None:
    """Persist a finished run and all of its supplier rows in one transaction."""
    with conn:
        conn.execute(
            "INSERT INTO rfp_runs (rfp_run_id, created_at, status, run_meta_json) "
            "VALUES (?, ?, ?, ?)",
            (run["rfp_run_id"], run["created_at"], run["status"],
             json.dumps(run["run_meta"])),
        )
        for s in run["suppliers"]:
            conn.execute(
                "INSERT INTO supplier_results (rfp_run_id, supplier_name, submission_date, "
                "experience_rating, absolute_score, ppi, final_rank, result_json) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (run["rfp_run_id"], s["supplier_name"], s["submission_date"],
                 s["experience_rating"], s["absolute_score"], s["ppi"],
                 s["final_rank"], json.dumps(s)),
            )


def list_runs(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM rfp_runs ORDER BY created_at DESC").fetchall()


def load_run(conn: sqlite3.Connection, run_id: str) -> dict | None:
    """Rebuild the full run dict (the downloadable JSON) from stored rows."""
    head = conn.execute(
        "SELECT * FROM rfp_runs WHERE rfp_run_id = ?", (run_id,)).fetchone()
    if head is None:
        return None
    rows = conn.execute(
        "SELECT result_json FROM supplier_results WHERE rfp_run_id = ? ORDER BY final_rank",
        (run_id,)).fetchall()
    suppliers = [json.loads(r["result_json"]) for r in rows]
    return {"rfp_run_id": head["rfp_run_id"], "created_at": head["created_at"],
            "status": head["status"], **json.loads(head["run_meta_json"]),
            "suppliers": suppliers}
