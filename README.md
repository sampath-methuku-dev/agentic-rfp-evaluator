# Agentic RFP Evaluation & Supplier Ranking

Upload supplier RFP proposal PDFs. An LLM scores each one against configurable criteria
(with justification and evidence). Python then validates the output, calculates weighted
scores, benchmarks suppliers against their peers, and produces a ranked, explainable
leaderboard stored in SQLite.

**Design rule:** the LLM only judges proposal content. Totals, benchmarks, PPI, tie-breaks and
ranks are plain Python, so the same validated scorecards always give the same ranking.

## Run locally

Requires Python 3.11+ and an API key for one supported provider (see below).

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt     # requirements.txt is enough to just run the app
python db/seed.py                       # optional: the app also creates/seeds the DB on start
python scripts/make_sample_pdfs.py      # optional: sample PDFs are already committed
streamlit run app.py
```

Open http://localhost:8501, choose a provider and model, paste that provider's key in the sidebar, upload the PDFs in
`data/sample_rfps/`, and click **Evaluate suppliers**.

**Privacy:** the key is typed into the sidebar each session. It lives only in that browser
session's memory; it is not read from `.env` or environment variables and is never written
to disk, the database, logs or the exported JSON.

## Choosing a provider, model and key

In the sidebar pick a **provider**, a **model** (a suggestion, or type any model name the provider
supports) and enter **that provider's API key**. Each provider has its own key field, and the keys
stay in memory for the browser session only (never on disk, in the database, logs or exported JSON).
The key is checked with a free call to the provider before any run.

| Provider | Endpoint used | Default model | Get a key |
|---|---|---|---|
| OpenRouter | `https://openrouter.ai/api/v1` | `openai/gpt-4o-mini` | https://openrouter.ai/keys |
| OpenAI | `https://api.openai.com/v1` | `gpt-4o-mini` | https://platform.openai.com/api-keys |
| Google Gemini | `https://generativelanguage.googleapis.com/v1beta/openai` (Google's OpenAI-compatible API) | `gemini-2.5-flash` | https://aistudio.google.com/app/apikey |

All three are called through LangChain's `ChatOpenAI`. To add another OpenAI-compatible provider, add
an entry to `PROVIDERS` in `src/config.py`.

## Architecture

```
app.py (Streamlit UI)
  └─ src/orchestrator.py        LangGraph StateGraph, one node per step:
       load_criteria -> validate_input -> inspect_documents -> evaluate_suppliers -> rank -> persist
       └─ src/lc_tools.py       every step is a LangChain tool (StructuredTool):
            check_submission_inputs   input tool: names, dates, ratings, duplicates
            read_proposal_pdf         document tool: PDF -> text + template check (LangChain PyPDFParser)
            evaluate_proposal         evaluation agent: LCEL chain ChatPromptTemplate | ChatOpenAI | JSON parser
            validate_scorecard        validation tool: schema check, fill, clip, warnings
            rank_suppliers            ranking tool: scores, benchmarks, PPI, tie-breaks, ranks
            load_active_criteria / save_run   database tools (SQLite)
```

**How LangChain is used**
- **LangGraph** runs the workflow as a state graph (drawn in the app, Criteria tab).
- **Tools:** each step above is a `StructuredTool` with a name, description and argument schema,
  invoked with `tool.invoke(...)`.
- **LCEL:** per supplier, `evaluate_proposal | validate_scorecard` is composed as a runnable chain
  (`RunnablePassthrough.assign`); the evaluation tool itself wraps a prompt | model | parser chain.
- **`ChatOpenAI`** (langchain-openai) is the only LLM call, pointed at the provider you choose, with JSON mode and a
  plain-request fallback for models that reject it.

**Deliberate design choice:** the order of steps is fixed by the graph, not chosen by an LLM agent, and
only `evaluate_proposal` calls the LLM. Validation and ranking are LangChain tools whose bodies are plain
Python, so the same validated scorecards always give the same ranks (a requirement of the brief).
The only things outside LangChain are the SQLite access inside the database tools, the key check
(a free HTTP call to the provider's key endpoint) and the Streamlit UI.
This app does not configure LangSmith tracing. Proposal text is sent to the provider you select
for evaluation.

Data flow: load criteria -> upload PDFs + metadata -> extract text -> prompt LLM -> parse JSON
-> validate/normalize -> weighted scores -> benchmarks -> PPI and ranking -> save under one
`RFP_RUN_ID` -> show leaderboard, scorecards and JSON download.

## Formulas

| Metric | Definition |
|---|---|
| Absolute weighted score | Σ (score / max_score × weight), 0-100 when weights total 100 |
| Criterion benchmark | Highest valid score for that criterion across all suppliers in the run |
| Criterion gap | supplier score − benchmark (0 for the leader, otherwise negative) |
| Relative performance % | supplier score / benchmark × 100 (100 for everyone if the benchmark is 0) |
| Peer Performance Index (PPI) | Σ (weight × relative %) / Σ weights |

**Tie-break order** (applied after a stable sort; ranks 1, 2, 3… assigned only afterwards):
higher PPI -> earlier submission date -> higher experience rating -> supplier name ascending.
PPI is rounded to 6 decimals before comparing so floating-point noise cannot decide a rank.
Each PPI tie is explained on the Run details screen.

## Input validation (what happens when a file does not match the template)

The expected proposal has six sections: executive summary, proposed solution, timeline and
milestones, pricing, security and compliance, support and experience. Each is detected by
keywords, so this is a heuristic check, not a layout parser. Checks run in the UI before you
click Evaluate and again in the orchestrator before any LLM call.

| Situation | What the system does |
|---|---|
| Not a real PDF (e.g. text renamed to .pdf), password protected, over 10 MB or 40 pages, scanned images with no text | **Excluded** with the reason shown; the other files are still ranked |
| Readable but fewer than 3 of the 6 sections found (e.g. a recipe) | **Excluded** as "does not look like an RFP response" |
| 3 to 5 sections found | **Accepted with a warning**: the missing sections are listed, the model is told they are absent so it scores dependent criteria low, and the note appears in the scorecard |
| All 6 sections found | Passed |
| Empty/over-long/control-character name, rating outside 0-10, duplicate supplier names, same file uploaded twice, more than 6 files | **Blocks Evaluate** until fixed; nothing is sent to the LLM |
| Submission date in the future | Warning only |
| None of the files can be evaluated | Run is refused; nothing is saved |

Every file's result is stored with the run and shown in **Run details > Input checks**.
Try them with the files in `data/error_cases/`: `Not_An_RFP.pdf`, `Not_Really_A_PDF.pdf`,
`Scanned_No_Text.pdf` (excluded) and `Partial_Proposal.pdf` (accepted with warnings).

## Validation rules (LLM output is untrusted)

Missing criterion -> score 0; score outside 0..max -> clipped; non-numeric/NaN/boolean -> 0;
unknown or duplicate criterion IDs -> ignored; reply not valid JSON -> one retry, then all zeros.
The configured `max_score` always wins over the model's. Every change is recorded as a warning.
A PDF with no extractable text (e.g. scanned) or an unreadable file is excluded and reported.

## Database (`data/rfp.db`, created automatically)

`evaluation_criteria`, `rfp_runs` (plus `run_meta_json`: criteria snapshot, tie-break notes,
warnings), `supplier_results` (`result_json` holds the full scorecard). To change criteria,
edit the table; the next run uses them with no code changes:

```sql
UPDATE evaluation_criteria SET is_active = 0 WHERE name = 'Support & Experience';
UPDATE evaluation_criteria SET weight = 30 WHERE name = 'Commercial Value';  -- keep total at 100
```

## Sample data and suggested metadata

Six fictional proposals in `data/sample_rfps/` (2 pages each; six is the upload limit). Suggested metadata for a demo:

| File | Supplier | Date | Experience |
|---|---|---|---|
| Apex_Systems.pdf | Apex Systems | 2026-10-15 | 7 |
| BrightPath_Tech.pdf | BrightPath Tech | 2026-10-14 | 4 |
| NexaWorks.pdf | NexaWorks | 2026-10-16 | 8 |
| Orbit_Digital.pdf | Orbit Digital | 2026-10-15 | 9 |
| Summit_Cloud.pdf | Summit Cloud | 2026-10-16 | 6 |
| Vertex_Solutions.pdf | Vertex Solutions | 2026-10-17 | 5 |

Files in `data/error_cases/` demonstrate the input-validation paths (see above).

## Tests

```bash
pytest -q        # 97 tests, no API key or network needed (LLM replaced by a fake client)
```

## Deploy to Streamlit Community Cloud

1. Push this folder as the root of a GitHub repo (`app.py` and `requirements.txt` at the root).
2. On share.streamlit.io choose the repo, branch `main`, main file `app.py`.
3. No secrets to configure: each visitor picks a provider and enters their own key in the sidebar.

The cloud disk is ephemeral: the database is recreated and seeded on start, so saved runs can
reset when the app restarts.

## Assumptions

- Active criteria weights must total 100%; otherwise the run is blocked.
- Up to 6 PDFs per run; proposal text is truncated at 60,000 characters.
- No OCR: scanned PDFs are rejected.
- The suggested models in the list are only suggestions and providers retire models over time; type any model name your provider supports (it must be able to return JSON).
