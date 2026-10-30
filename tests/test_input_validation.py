from datetime import date, timedelta
from pathlib import Path

import pytest

from src import repository
from src.config import MAX_PDF_BYTES
from src.models import SupplierUpload
from src.orchestrator import EvaluationError, run_evaluation
from src.tools.evaluation_agent import build_prompt
from src.tools.input_validation import (check_template, inspect_pdf, validate_batch,
                                        validate_metadata)
from tests.helpers import CRITERIA, FakeClient
from tests.test_pipeline import replies, uploads

ROOT = Path(__file__).resolve().parent.parent
SAMPLES, ERRORS = ROOT / "data" / "sample_rfps", ROOT / "data" / "error_cases"


def read(path):
    return path.read_bytes()


def upload(name, pdf, filename="x.pdf"):
    return SupplierUpload(name, date(2026, 10, 15), 5, filename, pdf)


# ---- files
def test_every_sample_proposal_passes_the_template_check():
    for pdf in SAMPLES.glob("*.pdf"):
        report = inspect_pdf(read(pdf))
        assert report.status == "ok" and report.sections_found == 6, pdf.name


def test_text_renamed_to_pdf_is_rejected():
    report = inspect_pdf(read(ERRORS / "Not_Really_A_PDF.pdf"))
    assert report.status == "rejected" and "not a PDF" in report.messages[0]


def test_scanned_pdf_is_rejected():
    assert inspect_pdf(read(ERRORS / "Scanned_No_Text.pdf")).status == "rejected"


def test_unrelated_document_is_rejected_as_not_an_rfp():
    report = inspect_pdf(read(ERRORS / "Not_An_RFP.pdf"))
    assert report.status == "rejected" and "Does not look like an RFP" in report.messages[0]


def test_partial_proposal_is_accepted_with_missing_sections_listed():
    report = inspect_pdf(read(ERRORS / "Partial_Proposal.pdf"))
    assert report.status == "warning" and report.sections_found == 3
    assert "Timeline and milestones" in report.missing_sections


def test_oversized_file_is_rejected():
    huge = b"%PDF-1.4\n" + b"0" * (MAX_PDF_BYTES + 1)
    assert "larger than" in inspect_pdf(huge).messages[0]


def test_check_template_counts_sections():
    found, missing = check_template("Our price is 5 USD. Security is strong. We offer support.")
    assert found == 3 and "Executive summary" in missing


# ---- metadata
def test_valid_metadata_has_no_errors():
    assert validate_metadata("Apex", date(2026, 10, 1), 7.5, today=date(2026, 10, 29)) == ([], [])


@pytest.mark.parametrize("name,rating", [("", 5), ("   ", 5), ("x" * 81, 5), ("bad\x00name", 5),
                                          ("ok", -1), ("ok", 10.5), ("ok", float("nan")), ("ok", "abc")])
def test_invalid_metadata_is_an_error(name, rating):
    errors, _ = validate_metadata(name, date(2026, 10, 1), rating)
    assert errors


def test_future_date_is_a_warning_not_an_error():
    today = date(2026, 10, 29)
    errors, warnings = validate_metadata("ok", today + timedelta(days=3), 5, today=today)
    assert errors == [] and "future" in warnings[0]


# ---- batch
def test_duplicate_names_and_duplicate_files_are_blocked():
    pdf = read(SAMPLES / "Apex_Systems.pdf")
    other = read(SAMPLES / "NexaWorks.pdf")
    assert any("more than once" in e for e in validate_batch([upload("A", pdf), upload("a ", other)]))
    assert any("same content" in e for e in validate_batch([upload("A", pdf, "1.pdf"), upload("B", pdf, "2.pdf")]))
    assert validate_batch([upload("A", pdf), upload("B", other)]) == []


def test_too_many_files_is_blocked():
    pdfs = [read(p) for p in sorted(SAMPLES.glob("*.pdf"))]
    batch = [upload(f"S{i}", pdfs[i % len(pdfs)] + bytes([i]), f"{i}.pdf") for i in range(7)]
    assert any("Too many" in e for e in validate_batch(batch))


# ---- orchestrator behaviour
@pytest.fixture
def conn(tmp_path):
    return repository.connect(tmp_path / "t.db")


def test_run_is_blocked_before_any_llm_call_on_bad_input(conn):
    client = FakeClient(replies())
    pdf = read(SAMPLES / "Apex_Systems.pdf")
    with pytest.raises(EvaluationError, match="Invalid input"):
        run_evaluation(conn, client, [upload("A", pdf, "1.pdf"), upload("a", pdf + b" ", "2.pdf")])
    assert client.calls == 0
    assert conn.execute("SELECT COUNT(*) FROM rfp_runs").fetchone()[0] == 0


def test_rejected_files_are_excluded_and_recorded_in_input_checks(conn):
    bad = [upload("Soup Co", read(ERRORS / "Not_An_RFP.pdf"), "soup.pdf"),
           upload("Fake Co", read(ERRORS / "Not_Really_A_PDF.pdf"), "fake.pdf")]
    run = run_evaluation(conn, FakeClient(replies()), uploads() + bad)
    assert len(run["suppliers"]) == 4
    assert {e["supplier_name"] for e in run["excluded_suppliers"]} == {"Soup Co", "Fake Co"}
    statuses = {c["supplier_name"]: c["status"] for c in run["input_checks"]}
    assert statuses["Soup Co"] == statuses["Fake Co"] == "rejected"
    assert statuses["Apex Systems"] == "ok"


def test_partial_proposal_is_scored_but_flagged_and_model_is_told(conn):
    partial = upload("Partial Co", read(ERRORS / "Partial_Proposal.pdf"), "partial.pdf")
    prompts = []

    class Spy(FakeClient):
        def __call__(self, prompt_value):
            prompts.append(prompt_value.to_string())
            return super().__call__(prompt_value)

    from tests.helpers import card
    client = Spy({**replies(), "Partial Co": card(4, 3, 5, 4, 2)})
    run = run_evaluation(conn, client, uploads() + [partial])
    s = next(x for x in run["suppliers"] if x["supplier_name"] == "Partial Co")
    assert any("Expected sections not found" in w for w in s["warnings"])
    assert any("were not detected: Proposed solution" in p for p in prompts)
    assert not any("were not detected" in p for p in prompts if "Supplier: Apex Systems" in p)


def test_build_prompt_only_adds_note_when_sections_are_missing():
    assert "not detected" not in build_prompt(CRITERIA, "A", "text")
    assert "not detected: Pricing" in build_prompt(CRITERIA, "A", "text", ("Pricing",))
