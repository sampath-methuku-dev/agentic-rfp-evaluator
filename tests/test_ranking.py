import random

from src.tools.ranking_tool import rank_suppliers
from tests.helpers import CRITERIA, supplier


def by_name(results):
    return {r["supplier_name"]: r for r in results}


def test_formulas_match_hand_calculation():
    # A: 8 / 4   B: 6 / 10   -> benchmarks: Tech 8, Price 10
    results, _ = rank_suppliers(CRITERIA, [supplier("A", 8, 4), supplier("B", 6, 10)])
    a, b = by_name(results)["A"], by_name(results)["B"]
    # absolute = sum(score/max * weight)
    assert a["absolute_score"] == 8 / 10 * 60 + 4 / 10 * 40   # 64.0
    assert b["absolute_score"] == 6 / 10 * 60 + 10 / 10 * 40  # 76.0
    # gaps are 0 for the leader, negative otherwise
    assert [c["gap"] for c in a["criteria"]] == [0, -6]
    assert [c["gap"] for c in b["criteria"]] == [-2, 0]
    # relative % = score / benchmark * 100
    assert [c["relative_pct"] for c in b["criteria"]] == [75.0, 100.0]
    # PPI = weighted average of relative %: A = (60*100 + 40*40)/100 = 76 ; B = (60*75 + 40*100)/100 = 85
    assert a["ppi"] == 76.0 and b["ppi"] == 85.0
    assert (b["final_rank"], a["final_rank"]) == (1, 2)


def test_ties_broken_by_date_then_experience_then_name():
    same = dict(s1=5, s2=5)
    suppliers = [
        supplier("Delta", **same, date="2026-10-15", exp=5),
        supplier("Alpha", **same, date="2026-10-15", exp=5),     # name decides vs Delta
        supplier("Gamma", **same, date="2026-10-15", exp=9),     # experience beats Alpha/Delta
        supplier("Beta", **same, date="2026-10-14", exp=1),      # earliest date wins overall
    ]
    results, explanations = rank_suppliers(CRITERIA, suppliers)
    assert [r["supplier_name"] for r in results] == ["Beta", "Gamma", "Alpha", "Delta"]
    assert [r["final_rank"] for r in results] == [1, 2, 3, 4]
    assert len(explanations) == 3
    assert "submission date" in explanations[0]
    assert "experience" in explanations[1]
    assert "name" in explanations[2]


def test_input_order_does_not_change_result():
    suppliers = [supplier("A", 8, 4), supplier("B", 6, 10), supplier("C", 7, 7),
                 supplier("D", 7, 7, date="2026-10-10")]
    expected, expected_notes = rank_suppliers(CRITERIA, suppliers)
    for seed in range(20):
        shuffled = suppliers[:]
        random.Random(seed).shuffle(shuffled)
        results, notes = rank_suppliers(CRITERIA, shuffled)
        assert results == expected and notes == expected_notes


def test_zero_benchmark_gives_everyone_100_percent():
    results, _ = rank_suppliers(CRITERIA, [supplier("A", 0, 5), supplier("B", 0, 10)])
    for r in results:
        assert r["criteria"][0]["relative_pct"] == 100.0
        assert r["criteria"][0]["gap"] == 0


def test_single_supplier_is_its_own_benchmark():
    results, notes = rank_suppliers(CRITERIA, [supplier("Solo", 3, 4)])
    assert results[0]["final_rank"] == 1 and results[0]["ppi"] == 100.0 and notes == []


def test_float_noise_does_not_break_a_tie():
    # 0.1 + 0.2 style noise: PPIs equal to 6 decimals must count as tied.
    a = supplier("A", 7.0, 7.0, date="2026-10-14")
    b = supplier("B", 7.0000000001, 7.0, date="2026-10-15")
    results, notes = rank_suppliers(CRITERIA, [b, a])
    assert [r["supplier_name"] for r in results] == ["A", "B"]
    assert len(notes) == 1
