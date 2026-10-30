"""Headless UI checks using Streamlit's AppTest (no browser, no network)."""
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from src import repository
from src.orchestrator import run_evaluation
from tests.helpers import FakeClient
from tests.test_pipeline import replies, uploads

APP = str(Path(__file__).resolve().parent.parent / "app.py")


@pytest.fixture
def db_path(tmp_path, monkeypatch):
    path = tmp_path / "ui.db"
    monkeypatch.setattr("src.repository.DB_PATH", path)
    return path


def test_app_renders_with_no_exceptions(db_path):
    at = AppTest.from_file(APP, default_timeout=30).run()
    assert not at.exception
    assert [t.label for t in at.tabs[:3]] == ["New evaluation", "Saved runs", "Criteria"]
    assert any("Weights total 100%" in s.value for s in at.success)
    assert at.sidebar.text_input[0].proto.type == 1  # TextInput.PASSWORD (masked)
    assert at.button[0].disabled  # nothing uploaded and no key yet


def test_app_shows_leaderboard_for_a_finished_run(db_path):
    run = run_evaluation(repository.connect(db_path), FakeClient(replies()), uploads())
    at = AppTest.from_file(APP, default_timeout=30)
    at.session_state["current_run_id"] = run["rfp_run_id"]
    at.run()
    assert not at.exception
    assert any(m.value == run["rfp_run_id"] for m in at.metric)
    leaderboard = at.dataframe[0].value
    assert list(leaderboard["Rank"]) == [1, 2, 3, 4]
