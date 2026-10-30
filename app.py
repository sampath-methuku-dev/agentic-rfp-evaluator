"""Streamlit UI for the Agentic RFP Evaluation & Supplier Ranking project."""
from dataclasses import asdict
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

from src import repository
from src.config import DEFAULT_PROVIDER, MAX_SUPPLIERS, PROVIDERS
from src.llm_client import LLMError, build_llm, check_key
from src.models import SupplierUpload
from src.orchestrator import EvaluationError, run_evaluation, workflow_diagram
from src.tools.input_validation import inspect_pdf, validate_batch, validate_metadata
from src.ui import hero, render_run

st.set_page_config(page_title="Agentic RFP Evaluation", page_icon="📄", layout="wide")

@st.cache_data(max_entries=24, show_spinner=False)
def inspect_cached(pdf_bytes: bytes) -> dict:
    """Readability and template check, cached so widget reruns do not re-parse the PDF."""
    return asdict(inspect_pdf(pdf_bytes))


conn = repository.connect()
criteria = repository.load_active_criteria(conn)


# ---------------------------------------------------------------- sidebar
with st.sidebar:
    st.header("Configuration")
    provider = st.selectbox("Provider", list(PROVIDERS), index=list(PROVIDERS).index(DEFAULT_PROVIDER),
                            key="provider", help="The proposal text is sent to the provider you choose.")
    provider_cfg = PROVIDERS[provider]
    # One key field per provider, so switching providers never mixes or loses keys during the session.
    api_key = st.text_input(
        f"{provider} API key", type="password", key=f"api_key_{provider}", persist_state="session",
        help="Kept only in this browser session. It is never saved to disk, the database, "
             "logs or the exported JSON, and it is sent only to the selected provider.")
    st.markdown(f"[Get a {provider} key]({provider_cfg['key_url']})")
    model = st.selectbox(
        "Model", provider_cfg["models"], key=f"model_{provider}", accept_new_options=True,
        persist_state="session",
        index=provider_cfg["models"].index(provider_cfg["default_model"]),
        help="Pick a suggestion or type any model name your provider supports "
             "(it must be able to return JSON).") or ""
    if api_key.strip():
        st.badge("API key set for this session", icon=":material/key:", color="green")
    else:
        st.badge("API key not set", icon=":material/key_off:", color="orange")
    st.divider()
    st.subheader("Active evaluation criteria")
    if criteria:
        st.dataframe(pd.DataFrame(
            [{"Criterion": c.name, "Weight (%)": c.weight, "Max": c.max_score} for c in criteria]),
            hide_index=True, width="stretch")
        total_weight = sum(c.weight for c in criteria)
        (st.success if abs(total_weight - 100) < 0.01 else st.error)(
            f"Weights total {total_weight:g}%")


# ---------------------------------------------------------------- page
hero()

tab_new, tab_saved, tab_criteria = st.tabs(["New evaluation", "Saved runs", "Criteria"])

with tab_new:
    st.header("1. Upload supplier proposals")
    files = st.file_uploader(f"Upload up to {MAX_SUPPLIERS} supplier RFP response PDFs",
                             type=["pdf"], accept_multiple_files=True, key="pdfs")
    errors: list[str] = []
    entries = []
    if len(files) > MAX_SUPPLIERS:
        errors.append(f"Too many files: {len(files)} uploaded, maximum is {MAX_SUPPLIERS}.")
        files = files[:MAX_SUPPLIERS]
    if files:
        st.write("Enter metadata for each uploaded proposal.")
    statuses = []
    for i, f in enumerate(files, start=1):
        fid = f"{f.name}-{f.size}-{i}"
        with st.expander(f"Supplier {i}: {f.name}", expanded=True):
            col1, col2, col3 = st.columns(3)
            name = col1.text_input("Supplier name", value=Path(f.name).stem.replace("_", " ").replace("-", " "),
                                   key=f"name_{fid}").strip()
            submitted = col2.date_input("Submission date", value=date.today(), key=f"date_{fid}")
            rating = col3.number_input("Historical experience rating (0-10)", 0.0, 10.0, 5.0,
                                       step=0.5, key=f"rating_{fid}")
            report = inspect_cached(f.getvalue())
            statuses.append(report["status"])
            if report["status"] == "ok":
                st.badge("Template check passed: all 6 expected sections found",
                         icon=":material/check_circle:", color="green")
            elif report["status"] == "warning":
                st.warning(" ".join(report["messages"]), icon=":material/warning:")
            else:
                st.error(" ".join(report["messages"]) + " This file will be excluded from the run.",
                         icon=":material/block:")
            meta_errors, meta_warnings = validate_metadata(name, submitted, rating)
            for m in meta_errors:
                st.error(m)
                errors.append(f"{f.name}: {m}")
            for m in meta_warnings:
                st.warning(m)
        entries.append((name, submitted, rating, f))

    if entries:
        errors += validate_batch([SupplierUpload(n, d, float(r), f.name, f.getvalue())
                                  for n, d, r, f in entries])
        if all(st_ == "rejected" for st_ in statuses):
            errors.append("None of the uploaded files can be evaluated.")
        elif "rejected" in statuses:
            st.info(f"{statuses.count('rejected')} file(s) will be excluded; the others will still be ranked.")
    if not criteria:
        errors.append("There are no active evaluation criteria.")
    elif abs(sum(c.weight for c in criteria) - 100) >= 0.01:
        errors.append("Active criteria weights must total 100%.")
    for e in errors:
        st.error(e)
    if not files:
        st.info("Upload at least one PDF to begin. Sample proposals are in `data/sample_rfps/`.")
    if files and not api_key.strip():
        st.info(f"Enter your {provider} API key in the sidebar to enable evaluation.")

    st.header("2. Evaluate")
    ready = bool(files) and not errors and bool(api_key.strip()) and bool(model.strip())
    if st.button("Evaluate suppliers", type="primary", disabled=not ready):
        try:
            check_key(api_key, provider)
            llm = build_llm(api_key, model, provider)
            uploads = [SupplierUpload(n, d, float(r), f.name, f.getvalue()) for n, d, r, f in entries]
            with st.status("Running evaluation...", expanded=True) as status:
                run = run_evaluation(conn, llm, uploads, progress=lambda m: status.write(m),
                                     model_name=model.strip(), provider=provider)
                status.update(label="Evaluation complete", state="complete")
            st.session_state["current_run_id"] = run["rfp_run_id"]
            st.toast(f"Run {run['rfp_run_id']} complete", icon=":material/check_circle:")
        except (LLMError, EvaluationError) as exc:
            st.session_state.pop("current_run_id", None)
            st.error(str(exc))

    current = st.session_state.get("current_run_id")
    if current:
        run = repository.load_run(conn, current)
        if run:
            st.header("3. Results")
            render_run(run, "new")

with tab_saved:
    runs = repository.list_runs(conn)
    if not runs:
        st.info("No saved runs yet.")
    else:
        run_id = st.selectbox("Run", [r["rfp_run_id"] for r in runs], key="saved_run_id",
                              format_func=lambda rid: f"{rid}  ({next(r['created_at'] for r in runs if r['rfp_run_id'] == rid)})")
        render_run(repository.load_run(conn, run_id), "saved")

with tab_criteria:
    st.write("Criteria live in the SQLite table `evaluation_criteria`. Change weights or "
             "`is_active` there and the next run uses them (no code or prompt changes).")
    st.dataframe(pd.DataFrame([dict(r) for r in repository.load_all_criteria(conn)]),
                 hide_index=True, width="stretch")
    with st.expander("Workflow graph (LangGraph)", icon=":material/account_tree:"):
        st.caption("Each node is one step of the evaluation. Only `evaluate_suppliers` calls the LLM.")
        st.mermaid_chart(workflow_diagram(), width="stretch")
