from src.tools.validation_tool import validate_scorecard
from tests.helpers import CRITERIA, card


def test_valid_input_has_no_warnings():
    out = validate_scorecard(card(8, 6, name="X"), CRITERIA, "X")
    assert out["warnings"] == []
    assert out["scorecard"][1]["score"] == 8 and out["scorecard"][2]["evidence"] == "e2"


def test_missing_criterion_filled_with_zero():
    out = validate_scorecard(card(8), CRITERIA, "X")
    assert out["scorecard"][2]["score"] == 0
    assert any("no result returned" in w for w in out["warnings"])


def test_out_of_range_scores_are_clipped():
    out = validate_scorecard(card(15, -3), CRITERIA, "X")
    assert out["scorecard"][1]["score"] == 10 and out["scorecard"][2]["score"] == 0
    assert sum("clipped" in w for w in out["warnings"]) == 2


def test_non_numeric_and_string_scores():
    raw = card(8, 6)
    raw["criteria"][0]["score"] = "7.5"        # numeric string is accepted
    raw["criteria"][1]["score"] = "high"       # garbage becomes 0
    out = validate_scorecard(raw, CRITERIA, "X")
    assert out["scorecard"][1]["score"] == 7.5
    assert out["scorecard"][2]["score"] == 0
    assert any("not a number" in w for w in out["warnings"])


def test_bool_nan_and_none_scores_rejected():
    raw = card(1, 1)
    raw["criteria"][0]["score"] = True
    raw["criteria"][1]["score"] = float("nan")
    out = validate_scorecard(raw, CRITERIA, "X")
    assert out["scorecard"][1]["score"] == 0 and out["scorecard"][2]["score"] == 0


def test_unknown_and_duplicate_ids_ignored():
    raw = card(8, 6)
    raw["criteria"].append({"criterion_id": 99, "score": 10})
    raw["criteria"].append({"criterion_id": 1, "score": 1})
    raw["criteria"].append({"criterion_id": "abc", "score": 1})
    out = validate_scorecard(raw, CRITERIA, "X")
    assert out["scorecard"][1]["score"] == 8
    assert len(out["warnings"]) == 3


def test_model_max_score_mismatch_uses_configured_max():
    raw = card(8, 6)
    raw["criteria"][0]["max_score"] = 100
    out = validate_scorecard(raw, CRITERIA, "X")
    assert out["scorecard"][1]["score"] == 8
    assert any("configured max" in w for w in out["warnings"])


def test_garbage_input_gives_all_zero_scorecard():
    for raw in (None, "text", [], {"criteria": "oops"}):
        out = validate_scorecard(raw, CRITERIA, "X")
        assert [out["scorecard"][c.criterion_id]["score"] for c in CRITERIA] == [0, 0]
        assert out["warnings"]
