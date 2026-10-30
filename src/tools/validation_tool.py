"""Schema checks and normalization of raw LLM scorecards.

The LLM output is untrusted: it can be missing criteria, contain strings
instead of numbers, or score outside the allowed range. Everything that is
changed is recorded as a warning so the result stays explainable.
"""
import math

from src.models import Criterion


def _text(value) -> str:
    return value.strip() if isinstance(value, str) else ("" if value is None else str(value))


def _as_score(value):
    """Return a finite float, or None if the value is not a usable number."""
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def validate_scorecard(raw, criteria: list[Criterion], supplier_name: str) -> dict:
    """Return {scorecard, risks, overall_summary, warnings} with every active criterion present."""
    warnings: list[str] = []
    by_id = {c.criterion_id: c for c in criteria}
    scorecard: dict[int, dict] = {}

    if not isinstance(raw, dict):
        warnings.append("LLM output was not a JSON object; all criteria set to 0.")
        raw = {}

    items = raw.get("criteria")
    if not isinstance(items, list):
        if "criteria" in raw:
            warnings.append("'criteria' was not a list; all criteria set to 0.")
        items = []

    for item in items:
        if not isinstance(item, dict):
            warnings.append("Ignored a criteria entry that was not an object.")
            continue
        cid = item.get("criterion_id")
        try:
            cid = int(cid)
        except (TypeError, ValueError):
            warnings.append(f"Ignored a result with invalid criterion_id {cid!r}.")
            continue
        criterion = by_id.get(cid)
        if criterion is None:
            warnings.append(f"Ignored a result for unknown criterion_id {cid}.")
            continue
        if cid in scorecard:
            warnings.append(f"Duplicate result for '{criterion.name}'; kept the first.")
            continue

        score = _as_score(item.get("score"))
        if score is None:
            warnings.append(
                f"'{criterion.name}': score {item.get('score')!r} is not a number; set to 0.")
            score = 0.0
        elif score < 0 or score > criterion.max_score:
            clipped = min(max(score, 0.0), criterion.max_score)
            warnings.append(
                f"'{criterion.name}': score {score:g} outside 0-{criterion.max_score:g}; "
                f"clipped to {clipped:g}.")
            score = clipped

        stated_max = _as_score(item.get("max_score"))
        if stated_max is not None and stated_max != criterion.max_score:
            warnings.append(
                f"'{criterion.name}': model used max_score {stated_max:g}, "
                f"configured max is {criterion.max_score:g}; configured value applied.")

        scorecard[cid] = {"score": score,
                          "justification": _text(item.get("justification")),
                          "evidence": _text(item.get("evidence"))}

    for c in criteria:
        if c.criterion_id not in scorecard:
            warnings.append(f"'{c.name}': no result returned; score set to 0.")
            scorecard[c.criterion_id] = {
                "score": 0.0, "justification": "No result returned by the model.",
                "evidence": ""}

    risks = raw.get("risks")
    if isinstance(risks, list):
        risks = [_text(r) for r in risks if _text(r)]
    else:
        risks = []

    returned_name = _text(raw.get("supplier_name"))
    if returned_name and returned_name.casefold() != supplier_name.casefold():
        warnings.append(
            f"Model returned supplier_name {returned_name!r}; the entered name was kept.")

    return {"scorecard": scorecard, "risks": risks,
            "overall_summary": _text(raw.get("overall_summary")), "warnings": warnings}
