import sqlite3
from datetime import date
from pathlib import Path

import pytest

from db.seed import init_db
from src import repository
from src.models import SupplierUpload
from src.orchestrator import EvaluationError, run_evaluation
from src.tools.document_tool import DocumentError, extract_text
from langchain_core.exceptions import OutputParserException

from src.tools.evaluation_agent import parse_json_reply
from tests.helpers import FakeClient, card

ROOT = Path(__file__).resolve().parent.parent
SAMPLES = ROOT / "data" / "sample_rfps"


@pytest.fixture
def conn(tmp_path):
    return repository.connect(tmp_path / "test.db")


def upload(stem, name, day, rating):
    return SupplierUpload(name, date(2026, 10, day), rating, f"{stem}.pdf",
                          (SAMPLES / f"{stem}.pdf").read_bytes())


def uploads():
    return [upload("Apex_Systems", "Apex Systems", 15, 7),
            upload("BrightPath_Tech", "BrightPath Tech", 14, 4),
            upload("NexaWorks", "NexaWorks", 16, 8),
            upload("Orbit_Digital", "Orbit Digital", 15, 9)]


def replies():
    return {"Apex Systems": card(9, 8, 5, 9, 7), "BrightPath Tech": card(5, 6, 9, 3, 3),
            "NexaWorks": card(7, 9, 7, 7, 9), "Orbit Digital": card(6, 4, 6, 8, 9)}


def test_seed_is_idempotent_and_weights_total_100(tmp_path):
    c = sqlite3.connect(tmp_path / "x.db")
    init_db(c); init_db(c)
    rows = c.execute("SELECT weight FROM evaluation_criteria WHERE is_active=1").fetchall()
    assert len(rows) == 5 and sum(r[0] for r in rows) == 100


def test_sample_pdfs_are_readable_and_error_pdf_is_rejected():
    for pdf in SAMPLES.glob("*.pdf"):
        text, _ = extract_text(pdf.read_bytes())
        assert "Price Table" in text
    with pytest.raises(DocumentError):
        extract_text((ROOT / "data" / "error_cases" / "Scanned_No_Text.pdf").read_bytes())
    with pytest.raises(DocumentError):
        extract_text(b"not a pdf")


def test_parse_json_reply_handles_fences_and_chatter():
    assert parse_json_reply('```json\n{"a": 1}\n```') == {"a": 1}
    assert parse_json_reply('Sure! {"a": 1} hope it helps') == {"a": 1}
    with pytest.raises(OutputParserException):
        parse_json_reply("no json here")


def test_full_run_persists_and_reloads(conn):
    run = run_evaluation(conn, FakeClient(replies()), uploads())
    assert run["status"] == "completed" and run["rfp_run_id"].startswith("RFP-")
    names = [s["supplier_name"] for s in run["suppliers"]]
    assert sorted(names) == sorted(["Apex Systems", "BrightPath Tech", "NexaWorks", "Orbit Digital"])
    assert [s["final_rank"] for s in run["suppliers"]] == [1, 2, 3, 4]
    assert run["suppliers"] == sorted(run["suppliers"], key=lambda s: -s["ppi"])
    assert conn.execute("SELECT COUNT(*) FROM supplier_results").fetchone()[0] == 4
    assert len(run["criteria"]) == 5
    assert repository.load_run(conn, run["rfp_run_id"]) == run


def test_same_scorecards_always_give_same_ranking(conn):
    first = run_evaluation(conn, FakeClient(replies()), uploads())
    second = run_evaluation(conn, FakeClient(replies()), list(reversed(uploads())))
    strip = lambda r: [(s["supplier_name"], s["final_rank"], s["ppi"], s["absolute_score"])
                       for s in r["suppliers"]]
    assert strip(first) == strip(second)


def test_malformed_llm_output_is_normalised_with_warnings(conn):
    bad = replies()
    bad["Apex Systems"] = card(15, 8)                     # out of range + missing criteria
    bad["BrightPath Tech"] = "this is not json at all"    # unusable after retry
    client = FakeClient(bad)
    run = run_evaluation(conn, client, uploads())
    apex = next(s for s in run["suppliers"] if s["supplier_name"] == "Apex Systems")
    bright = next(s for s in run["suppliers"] if s["supplier_name"] == "BrightPath Tech")
    assert apex["criteria"][0]["score"] == 10
    assert any("clipped" in w for w in apex["warnings"])
    assert bright["absolute_score"] == 0
    assert any("valid JSON" in w for w in bright["warnings"])
    assert client.calls == 4 + 1  # one retry for the non-JSON reply


def test_unreadable_pdf_is_excluded_not_fatal(conn):
    bad = SupplierUpload("Scanned Co", date(2026, 10, 15), 5, "Scanned_No_Text.pdf",
                         (ROOT / "data" / "error_cases" / "Scanned_No_Text.pdf").read_bytes())
    run = run_evaluation(conn, FakeClient(replies()), uploads() + [bad])
    assert len(run["suppliers"]) == 4
    assert run["excluded_suppliers"][0]["supplier_name"] == "Scanned Co"


def test_only_unreadable_pdfs_raises(conn):
    bad = SupplierUpload("Scanned Co", date(2026, 10, 15), 5, "x.pdf", b"nope")
    with pytest.raises(EvaluationError):
        run_evaluation(conn, FakeClient({}), [bad])


def test_criteria_changes_apply_without_code_changes(conn):
    conn.execute("UPDATE evaluation_criteria SET is_active=0 WHERE name='Support & Experience'")
    conn.execute("UPDATE evaluation_criteria SET weight=30 WHERE name='Commercial Value'")
    conn.commit()
    four = {k: card(*[c["score"] for c in v["criteria"][:4]]) for k, v in replies().items()}
    run = run_evaluation(conn, FakeClient(four), uploads())
    assert len(run["criteria"]) == 4 and all(len(s["criteria"]) == 4 for s in run["suppliers"])


def test_bad_weight_total_is_rejected(conn):
    conn.execute("UPDATE evaluation_criteria SET weight=50 WHERE name='Technical Capability'")
    conn.commit()
    with pytest.raises(EvaluationError, match="weights total"):
        run_evaluation(conn, FakeClient(replies()), uploads())
