"""Deterministic scoring, peer benchmarking, PPI and ranking.

Pure Python: no LLM, database or Streamlit imports. The same validated
scorecards always produce the same numbers and the same order.
"""
from src.models import Criterion

PPI_PRECISION = 6    # PPI is rounded before sorting so float noise cannot break ties
DISPLAY_PRECISION = 2


def _sort_key(s: dict) -> tuple:
    # 1) higher PPI  2) earlier date  3) higher experience  4) name ascending
    return (-round(s["ppi"], PPI_PRECISION), s["submission_date"],
            -s["experience_rating"], s["supplier_name"].casefold(), s["supplier_name"])


def _deciding_rule(a: dict, b: dict) -> str:
    """Name the first tie-break rule that separates a (ahead) from b."""
    if a["submission_date"] != b["submission_date"]:
        return (f"earlier submission date ({a['submission_date']} vs "
                f"{b['submission_date']})")
    if a["experience_rating"] != b["experience_rating"]:
        return (f"higher experience rating ({a['experience_rating']:g} vs "
                f"{b['experience_rating']:g})")
    return "supplier name in ascending order"


def rank_suppliers(criteria: list[Criterion], suppliers: list[dict]) -> tuple[list[dict], list[str]]:
    """Score, benchmark and rank suppliers.

    Each input supplier dict needs: supplier_name, submission_date (ISO string),
    experience_rating, and scorecard = {criterion_id: {score, justification, evidence}}
    where every active criterion is present (the validation tool guarantees it).

    Returns (ranked supplier results, tie-break explanations).
    """
    total_weight = sum(c.weight for c in criteria)

    benchmark = {
        c.criterion_id: max((s["scorecard"][c.criterion_id]["score"] for s in suppliers),
                            default=0.0)
        for c in criteria
    }

    results = []
    for s in suppliers:
        rows, absolute, ppi_sum = [], 0.0, 0.0
        for c in criteria:
            card = s["scorecard"][c.criterion_id]
            score, bench = card["score"], benchmark[c.criterion_id]
            # Safe handling of a zero benchmark: nobody scored, so nobody trails.
            relative = (score / bench * 100.0) if bench > 0 else 100.0
            absolute += score / c.max_score * c.weight
            ppi_sum += c.weight * relative
            rows.append({
                "criterion_id": c.criterion_id, "name": c.name,
                "weight": c.weight, "max_score": c.max_score,
                "score": score, "benchmark": bench, "gap": score - bench,
                "relative_pct": relative,
                "justification": card.get("justification", ""),
                "evidence": card.get("evidence", ""),
            })
        results.append({
            "supplier_name": s["supplier_name"],
            "submission_date": s["submission_date"],
            "experience_rating": s["experience_rating"],
            "source_file": s.get("source_file", ""),
            "absolute_score": absolute,
            "ppi": ppi_sum / total_weight if total_weight else 0.0,
            "criteria": rows,
            "risks": s.get("risks", []),
            "overall_summary": s.get("overall_summary", ""),
            "warnings": s.get("warnings", []),
        })

    results.sort(key=_sort_key)

    explanations = []
    for rank, r in enumerate(results, start=1):
        r["final_rank"] = rank
    for ahead, behind in zip(results, results[1:]):
        if round(ahead["ppi"], PPI_PRECISION) == round(behind["ppi"], PPI_PRECISION):
            explanations.append(
                f"{ahead['supplier_name']} (rank {ahead['final_rank']}) and "
                f"{behind['supplier_name']} (rank {behind['final_rank']}) tied on PPI "
                f"{ahead['ppi']:.{DISPLAY_PRECISION}f}; decided by "
                f"{_deciding_rule(ahead, behind)}.")

    # Round for storage/display only after ranking.
    for r in results:
        r["absolute_score"] = round(r["absolute_score"], 4)
        r["ppi"] = round(r["ppi"], 4)
        for row in r["criteria"]:
            row["relative_pct"] = round(row["relative_pct"], 2)
    return results, explanations
