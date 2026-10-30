"""Every workflow step is a LangChain tool; check they work alone and compose in the graph."""
import threading
from pathlib import Path

import pytest
from langchain_core.runnables import Runnable
from langchain_core.tools import BaseTool

from src import repository
from src.lc_tools import (check_submission_inputs, make_database_tools, make_evaluation_tool,
                          rank_suppliers_tool, read_proposal_pdf, validate_scorecard_tool)
from src.orchestrator import run_evaluation
from src.tools.ranking_tool import rank_suppliers
from tests.helpers import CRITERIA, FakeLLM, card, supplier
from tests.test_pipeline import replies, uploads

ROOT = Path(__file__).resolve().parent.parent


def test_every_step_is_a_langchain_tool_with_a_description_and_schema():
    llm_tool = make_evaluation_tool(FakeLLM({}))
    db = make_database_tools(None)
    tools = [check_submission_inputs, read_proposal_pdf, llm_tool, validate_scorecard_tool,
             rank_suppliers_tool, *db.values()]
    assert {t.name for t in tools} == {
        "check_submission_inputs", "read_proposal_pdf", "evaluate_proposal", "validate_scorecard",
        "rank_suppliers", "load_active_criteria", "save_run"}
    for t in tools:
        assert isinstance(t, BaseTool) and isinstance(t, Runnable)
        assert len(t.description) > 40
    assert set(rank_suppliers_tool.args) == {"criteria", "suppliers"}
    assert set(llm_tool.args) == {"supplier_name", "proposal_text", "criteria", "missing_sections"}


def test_document_tool_reads_a_sample_pdf():
    out = read_proposal_pdf.invoke({"pdf_bytes": (ROOT / "data/sample_rfps/Apex_Systems.pdf").read_bytes()})
    assert out["status"] == "ok" and "Price Table" in out["text"] and out["missing_sections"] == []


def test_ranking_tool_matches_the_plain_function_and_is_deterministic():
    suppliers = [supplier("A", 8, 4), supplier("B", 6, 10), supplier("C", 7, 7)]
    expected, notes = rank_suppliers(CRITERIA, suppliers)
    for _ in range(3):
        out = rank_suppliers_tool.invoke({"criteria": CRITERIA, "suppliers": suppliers})
        assert out == {"suppliers": expected, "tie_breaks": notes}
    assert [s["supplier_name"] for s in out["suppliers"]] == ["B", "C", "A"]


def test_validation_tool_normalises_and_reports():
    out = validate_scorecard_tool.invoke(
        {"raw": card(15), "criteria": CRITERIA, "supplier_name": "X"})
    assert out["scorecard"][1]["score"] == 10 and out["scorecard"][2]["score"] == 0
    assert len(out["warnings"]) == 2


def test_input_tool_returns_blocking_problems():
    problems = check_submission_inputs.invoke({"uploads": uploads()[:1] * 2})
    assert any("more than once" in p for p in problems)
    assert check_submission_inputs.invoke({"uploads": uploads()}) == []


def test_evaluation_tool_is_the_only_one_that_calls_the_llm():
    llm = FakeLLM({"Apex": card(9, 8)})
    out = make_evaluation_tool(llm).invoke({"supplier_name": "Apex", "proposal_text": "text",
                                            "criteria": CRITERIA, "missing_sections": ["Pricing"]})
    assert out["raw"]["criteria"][0]["score"] == 9 and out["warnings"] == [] and llm.calls == 1
    llm.calls = 0
    validate_scorecard_tool.invoke({"raw": card(1, 1), "criteria": CRITERIA, "supplier_name": "X"})
    rank_suppliers_tool.invoke({"criteria": CRITERIA, "suppliers": [supplier("A", 1, 1)]})
    assert llm.calls == 0


def test_database_tools_roundtrip(tmp_path):
    db = make_database_tools(repository.connect(tmp_path / "t.db"))
    assert len(db["load_active_criteria"].invoke({})) == 5
    run = run_evaluation(repository.connect(tmp_path / "u.db"), FakeLLM(replies()), uploads())
    saved = make_database_tools(repository.connect(tmp_path / "v.db"))["save_run"].invoke(
        {"run": {"rfp_run_id": run["rfp_run_id"], "created_at": run["created_at"],
                 "status": run["status"], "run_meta": {"model": "m"}, "suppliers": run["suppliers"]}})
    assert saved["rfp_run_id"] == run["rfp_run_id"] and len(saved["suppliers"]) == 4


def test_progress_updates_stay_on_the_calling_thread(tmp_path):
    """Streamlit can only be updated from the script thread; LCEL branches run in worker threads."""
    threads, messages = set(), []

    def progress(message):
        threads.add(threading.get_ident())
        messages.append(message)

    run_evaluation(repository.connect(tmp_path / "t.db"), FakeLLM(replies()), uploads(), progress=progress)
    assert threads == {threading.get_ident()}
    assert any(m.startswith("Evaluating") for m in messages) and any(m.startswith("Validating") for m in messages)


def test_a_failing_llm_aborts_the_run_and_saves_nothing(tmp_path):
    from src.llm_client import LLMError

    def broken(_prompt):
        raise LLMError("Authentication failed: check your OpenRouter API key.")

    conn = repository.connect(tmp_path / "t.db")
    with pytest.raises(LLMError):
        run_evaluation(conn, broken, uploads())
    assert conn.execute("SELECT COUNT(*) FROM rfp_runs").fetchone()[0] == 0
