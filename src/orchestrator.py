"""Orchestrator: the evaluation workflow as a LangGraph state graph of LangChain tools.

    load_criteria -> validate_input -> inspect_documents -> evaluate_suppliers -> rank -> persist

Each node calls LangChain tools (see `lc_tools.py`). Per supplier, `evaluate_suppliers` runs an LCEL
chain: evaluate_proposal | validate_scorecard. The LLM is only used inside `evaluate_proposal`;
every other step is deterministic Python.
"""
import uuid
from datetime import datetime, timezone
from typing import Callable, TypedDict

from langchain_core.runnables import RunnableLambda, RunnablePassthrough
from langgraph.graph import END, START, StateGraph

from src.config import WEIGHT_TOLERANCE
from src.lc_tools import (check_submission_inputs, make_database_tools, make_evaluation_tool,
                          rank_suppliers_tool, read_proposal_pdf, validate_scorecard_tool)
from src.models import Criterion, SupplierUpload


class EvaluationError(Exception):
    """The run cannot proceed; the message is safe to show to the user."""


class RunState(TypedDict, total=False):
    uploads: list[SupplierUpload]
    criteria: list[Criterion]
    reports: list[tuple[SupplierUpload, dict]]
    input_checks: list[dict]
    excluded: list[dict]
    run_warnings: list[str]
    ranked_input: list[dict]
    suppliers: list[dict]
    tie_breaks: list[str]
    result: dict


def build_graph(conn, llm, progress: Callable[[str], None] = lambda message: None,
                model_name: str = "", provider: str = ""):
    """Compile the workflow. `conn`, `llm` and `progress` are captured by the nodes."""

    db = make_database_tools(conn) if conn is not None else {}
    evaluate_tool = make_evaluation_tool(llm)

    def load_criteria(state: RunState) -> dict:
        # Criteria are reloaded on every run, so database changes apply immediately.
        criteria = db["load_active_criteria"].invoke({})
        if not criteria:
            raise EvaluationError("No active evaluation criteria in the database.")
        total = sum(c.weight for c in criteria)
        if abs(total - 100.0) > WEIGHT_TOLERANCE:
            raise EvaluationError(f"Active criteria weights total {total:g}%, expected 100%.")
        return {"criteria": criteria}

    def validate_input(state: RunState) -> dict:
        # Anything the user can fix blocks the run before the LLM is called.
        problems = check_submission_inputs.invoke({"uploads": state["uploads"]})
        if problems:
            raise EvaluationError("Invalid input: " + " ".join(problems))
        return {}

    def inspect_documents(state: RunState) -> dict:
        reports, input_checks, excluded, run_warnings = [], [], [], []
        for upload in state["uploads"]:
            progress(f"Checking {upload.filename}")
            report = read_proposal_pdf.invoke({"pdf_bytes": upload.pdf_bytes})
            input_checks.append({"supplier_name": upload.supplier_name, "filename": upload.filename,
                                 "status": report["status"], "messages": report["messages"],
                                 "missing_sections": report["missing_sections"]})
            if report["status"] == "rejected":
                reason = " ".join(report["messages"])
                excluded.append({"supplier_name": upload.supplier_name,
                                 "filename": upload.filename, "reason": reason})
                run_warnings.append(f"{upload.supplier_name}: excluded - {reason}")
            else:
                reports.append((upload, report))
        if not reports:
            reasons = "; ".join(f"{e['supplier_name']}: {e['reason']}" for e in excluded)
            raise EvaluationError(f"No proposals could be evaluated. {reasons}")
        return {"reports": reports, "input_checks": input_checks,
                "excluded": excluded, "run_warnings": run_warnings}

    def evaluate_suppliers(state: RunState) -> dict:
        criteria = state["criteria"]

        def start(item):
            upload, report = item
            progress(f"Evaluating {upload.supplier_name}")
            return {"upload": upload, "report": report}

        def to_evaluation_args(ctx):
            return {"supplier_name": ctx["upload"].supplier_name,
                    "proposal_text": ctx["report"]["text"], "criteria": criteria,
                    "missing_sections": ctx["report"]["missing_sections"]}

        def announce_validation(ctx):
            # Own step: `assign` branches run in worker threads, and Streamlit progress updates
            # must come from the calling thread.
            progress(f"Validating {ctx['upload'].supplier_name}")
            return ctx

        def to_validation_args(ctx):
            return {"raw": ctx["evaluation"]["raw"], "criteria": criteria,
                    "supplier_name": ctx["upload"].supplier_name}

        def to_ranking_input(ctx):
            upload, validated = ctx["upload"], ctx["validated"]
            return {
                "supplier_name": upload.supplier_name,
                "submission_date": upload.submission_date.isoformat(),
                "experience_rating": float(upload.experience_rating),
                "source_file": upload.filename,
                "scorecard": validated["scorecard"],
                "risks": validated["risks"],
                "overall_summary": validated["overall_summary"],
                "warnings": ctx["report"]["messages"] + ctx["evaluation"]["warnings"]
                            + validated["warnings"],
            }

        # LCEL: one chain per supplier, evaluation tool then validation tool.
        per_supplier = (
            RunnableLambda(start)
            | RunnablePassthrough.assign(evaluation=RunnableLambda(to_evaluation_args) | evaluate_tool)
            | RunnableLambda(announce_validation)
            | RunnablePassthrough.assign(
                validated=RunnableLambda(to_validation_args) | validate_scorecard_tool)
            | RunnableLambda(to_ranking_input))
        # Sequential `invoke` (not `batch`): stable order, gentle on rate limits, and it stays on the
        # calling thread, which Streamlit's progress updates require.
        return {"ranked_input": [per_supplier.invoke(item) for item in state["reports"]]}

    def rank(state: RunState) -> dict:
        progress("Scoring, benchmarking and ranking")
        result = rank_suppliers_tool.invoke(
            {"criteria": state["criteria"], "suppliers": state["ranked_input"]})
        return {"suppliers": result["suppliers"], "tie_breaks": result["tie_breaks"]}

    def persist(state: RunState) -> dict:
        now = datetime.now(timezone.utc)
        run = {
            "rfp_run_id": f"RFP-{now:%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:6]}",
            "created_at": now.isoformat(timespec="seconds"),
            "status": "completed",
            "run_meta": {
                "provider": provider,
                "model": model_name,
                "criteria": [{"criterion_id": c.criterion_id, "name": c.name,
                              "description": c.description, "weight": c.weight,
                              "max_score": c.max_score} for c in state["criteria"]],
                "tie_break_explanations": state["tie_breaks"],
                "input_checks": state["input_checks"],
                "excluded_suppliers": state["excluded"],
                "warnings": state["run_warnings"],
            },
            "suppliers": state["suppliers"],
        }
        progress("Saving results")
        return {"result": db["save_run"].invoke({"run": run})}

    graph = StateGraph(RunState)
    steps = [("load_criteria", load_criteria), ("validate_input", validate_input),
             ("inspect_documents", inspect_documents), ("evaluate_suppliers", evaluate_suppliers),
             ("rank", rank), ("persist", persist)]
    for name, node in steps:
        graph.add_node(name, node)
    graph.add_edge(START, steps[0][0])
    for (a, _), (b, _) in zip(steps, steps[1:]):
        graph.add_edge(a, b)
    graph.add_edge(steps[-1][0], END)
    return graph.compile()


def run_evaluation(conn, llm, uploads: list[SupplierUpload],
                   progress: Callable[[str], None] = lambda message: None,
                   model_name: str = "", provider: str = "") -> dict:
    """Run the workflow and return the saved run (the same dict the JSON download contains)."""
    final = build_graph(conn, llm, progress, model_name, provider).invoke({"uploads": uploads})
    return final["result"]


def workflow_diagram() -> str:
    """Mermaid source of the workflow graph (for documentation and the UI)."""
    return build_graph(None, None).get_graph().draw_mermaid()
