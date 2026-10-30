"""The workflow's tools, as LangChain tools.

Every step of the evaluation is a LangChain `StructuredTool` (a Runnable), so the steps can be
invoked on their own, piped together in LCEL, and inspected by name, description and schema.
The tools wrap the plain functions in `src/tools/`. Only `evaluate_proposal` talks to the LLM;
validation and ranking contain no LLM calls, so the same scorecards always give the same result.
"""
from dataclasses import asdict
from typing import Any

from langchain_core.tools import StructuredTool, tool

from src import repository
from src.models import Criterion, SupplierUpload
from src.tools.evaluation_agent import evaluate_supplier
from src.tools.input_validation import inspect_pdf, validate_batch, validate_metadata
from src.tools.ranking_tool import rank_suppliers
from src.tools.validation_tool import validate_scorecard


@tool("check_submission_inputs")
def check_submission_inputs(uploads: list[SupplierUpload]) -> list[str]:
    """Input tool: validate supplier names, dates, ratings, duplicate names and duplicate files.
    Returns a list of blocking problems (empty when the submission is acceptable)."""
    problems = validate_batch(uploads)
    for u in uploads:
        errors, _ = validate_metadata(u.supplier_name, u.submission_date, u.experience_rating)
        problems += [f"{u.filename}: {e}" for e in errors]
    return problems


@tool("read_proposal_pdf")
def read_proposal_pdf(pdf_bytes: bytes) -> dict:
    """Document tool: extract clean text from one proposal PDF and check it against the expected
    six-section template. Returns status (ok, warning or rejected), text, messages and missing sections."""
    return asdict(inspect_pdf(pdf_bytes))


def make_evaluation_tool(llm) -> StructuredTool:
    """Evaluation agent as a tool: an LLM chain that scores one proposal against the criteria."""
    def evaluate_proposal(supplier_name: str, proposal_text: str, criteria: list[Criterion],
                          missing_sections: list[str]) -> dict:
        raw, warnings = evaluate_supplier(llm, criteria, supplier_name, proposal_text,
                                          tuple(missing_sections))
        return {"raw": raw, "warnings": warnings}

    return StructuredTool.from_function(
        evaluate_proposal, name="evaluate_proposal",
        description="Evaluation agent: ask the LLM to score one supplier proposal against the active "
                    "criteria and return JSON with scores, justifications and evidence. The only tool "
                    "that calls the LLM.")


@tool("validate_scorecard")
def validate_scorecard_tool(raw: Any, criteria: list[Criterion], supplier_name: str) -> dict:
    """Validation tool: check the LLM scorecard against the schema, fill missing criteria with 0,
    clip out-of-range scores and record a warning for every change."""
    return validate_scorecard(raw, criteria, supplier_name)


@tool("rank_suppliers")
def rank_suppliers_tool(criteria: list[Criterion], suppliers: list[dict]) -> dict:
    """Ranking tool: absolute weighted scores, per-criterion benchmarks, gaps, relative percentages,
    Peer Performance Index, deterministic tie-breaks and final ranks. Pure Python, no LLM."""
    ranked, tie_breaks = rank_suppliers(criteria, suppliers)
    return {"suppliers": ranked, "tie_breaks": tie_breaks}


def make_database_tools(conn) -> dict[str, StructuredTool]:
    """Database tools bound to one SQLite connection."""
    @tool("load_active_criteria")
    def load_active_criteria() -> list[Criterion]:
        """Database tool: load the active evaluation criteria with weights and max scores."""
        return repository.load_active_criteria(conn)

    @tool("save_run")
    def save_run(run: dict) -> dict:
        """Database tool: persist a finished run and its supplier results in one transaction,
        then return the stored run."""
        repository.save_run(conn, run)
        return repository.load_run(conn, run["rfp_run_id"])

    return {"load_active_criteria": load_active_criteria, "save_run": save_run}
