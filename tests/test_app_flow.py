"""Drives the real Streamlit script end to end (upload -> evaluate -> results) with a fake LLM."""
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from tests.helpers import FakeLLM, card

ROOT = Path(__file__).resolve().parent.parent
APP = str(ROOT / "app.py")
SAMPLES, ERRORS = ROOT / "data" / "sample_rfps", ROOT / "data" / "error_cases"

SCORES = {"Apex Systems": (9, 8, 5, 9, 7), "BrightPath Tech": (5, 6, 9, 3, 3),
          "NexaWorks": (7, 9, 7, 7, 9), "Orbit Digital": (6, 4, 6, 8, 9),
          "Summit Cloud": (8, 5, 3, 10, 5), "Vertex Solutions": (8, 4, 7, 5, 4),
          "Partial Proposal": (3, 2, 5, 4, 2)}


CALLS = {"build": [], "check": []}


def fake_build_llm(api_key, model, provider="OpenRouter"):
    CALLS["build"].append((api_key, model, provider))
    return FakeLLM({n: card(*sc) for n, sc in SCORES.items()})


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setattr("src.repository.DB_PATH", tmp_path / "ui.db")
    monkeypatch.setattr("src.llm_client.build_llm", fake_build_llm)
    monkeypatch.setattr("src.llm_client.check_key",
                        lambda api_key, provider="OpenRouter": CALLS["check"].append((api_key, provider)))
    CALLS["build"].clear(); CALLS["check"].clear()
    at = AppTest.from_file(APP, default_timeout=60).run()
    at.sidebar.text_input[0].set_value("sk-or-test-key").run()
    return at


def upload(at, *paths):
    at.file_uploader[0].set_value([(p.name, p.read_bytes(), "application/pdf") for p in paths]).run()
    return at


def evaluate(at):
    next(b for b in at.button if b.label == "Evaluate suppliers").click().run()
    return at


def test_full_ui_flow_with_six_samples_and_three_bad_files(app):
    good = sorted(SAMPLES.glob("*.pdf"))
    bad = [ERRORS / "Not_An_RFP.pdf", ERRORS / "Not_Really_A_PDF.pdf"]
    # Six samples plus two bad files = 8 > 6 uploads, so the UI must block.
    at = upload(app, *good, *bad)
    assert any("Too many files" in e.value for e in at.error)
    # Re-upload within the limit: 4 good + the two bad ones.
    at = upload(app, *good[:4], *bad)
    assert not any("Too many files" in e.value for e in at.error)
    assert any("will be excluded" in e.value for e in at.error)
    at = evaluate(at)
    assert not at.exception
    assert at.session_state["current_run_id"].startswith("RFP-")
    assert list(at.dataframe[0].value["Rank"]) == [1, 2, 3, 4]   # bad files excluded, 4 ranked


def test_all_six_samples_rank_and_ties_are_explained(app):
    at = evaluate(upload(app, *sorted(SAMPLES.glob("*.pdf"))))
    assert not at.exception
    board = at.dataframe[0].value
    assert len(board) == 6 and list(board["Rank"]) == [1, 2, 3, 4, 5, 6]
    assert list(board["PPI"]) == sorted(board["PPI"], reverse=True)


def test_partial_proposal_runs_with_warning(app):
    at = upload(app, SAMPLES / "Apex_Systems.pdf", ERRORS / "Partial_Proposal.pdf")
    assert any("Expected sections not found" in w.value for w in at.warning)
    at = evaluate(at)
    assert not at.exception and at.session_state["current_run_id"]


def test_only_bad_files_disables_evaluate(app):
    at = upload(app, ERRORS / "Not_An_RFP.pdf", ERRORS / "Not_Really_A_PDF.pdf")
    assert any("None of the uploaded files can be evaluated" in e.value for e in at.error)
    assert next(b for b in at.button if b.label == "Evaluate suppliers").disabled


def test_duplicate_names_block_evaluate(app):
    at = upload(app, SAMPLES / "Apex_Systems.pdf", SAMPLES / "NexaWorks.pdf")
    at.text_input[1].set_value("Apex Systems").run()   # rename 2nd supplier to match the 1st
    assert any("more than once" in e.value for e in at.error)
    assert next(b for b in at.button if b.label == "Evaluate suppliers").disabled


def test_key_is_required_to_evaluate(tmp_path, monkeypatch):
    monkeypatch.setattr("src.repository.DB_PATH", tmp_path / "ui.db")
    at = AppTest.from_file(APP, default_timeout=60).run()
    at = upload(at, SAMPLES / "Apex_Systems.pdf")
    assert next(b for b in at.button if b.label == "Evaluate suppliers").disabled


def test_provider_choice_uses_that_providers_key_and_model(app):
    at = app
    assert at.sidebar.selectbox[0].options == ["OpenRouter", "OpenAI", "Google Gemini"]
    assert at.sidebar.text_input[0].label == "OpenRouter API key"
    at.sidebar.selectbox[0].select("Google Gemini").run()
    assert at.sidebar.text_input[0].label == "Google Gemini API key"
    assert at.sidebar.text_input[0].value == ""             # the OpenRouter key is not reused
    assert at.sidebar.selectbox[1].value == "gemini-2.5-flash"
    at.sidebar.text_input[0].set_value("gemini-key").run()
    at = evaluate(upload(at, SAMPLES / "Apex_Systems.pdf", SAMPLES / "NexaWorks.pdf"))
    assert not at.exception
    assert CALLS["check"] == [("gemini-key", "Google Gemini")]
    assert CALLS["build"] == [("gemini-key", "gemini-2.5-flash", "Google Gemini")]
    run = at.session_state["current_run_id"]
    assert run.startswith("RFP-")


def test_each_provider_keeps_its_own_key_when_switching(app):
    at = app                                                 # OpenRouter key already entered
    at.sidebar.selectbox[0].select("OpenAI").run()
    at.sidebar.text_input[0].set_value("openai-key").run()
    at.sidebar.selectbox[0].select("OpenRouter").run()
    assert at.sidebar.text_input[0].value == "sk-or-test-key"
    at.sidebar.selectbox[0].select("OpenAI").run()
    assert at.sidebar.text_input[0].value == "openai-key"


def test_chosen_model_is_passed_to_the_provider(app):
    at = app
    at.sidebar.selectbox[0].select("OpenAI").run()
    at.sidebar.text_input[0].set_value("k").run()
    at.sidebar.selectbox[1].select("gpt-4.1").run()
    evaluate(upload(at, SAMPLES / "Apex_Systems.pdf"))
    assert CALLS["build"][-1] == ("k", "gpt-4.1", "OpenAI")
