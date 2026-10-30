import json

from src.models import Criterion

CRITERIA = [Criterion(1, "Tech", "d", 60, 10), Criterion(2, "Price", "d", 40, 10)]


def supplier(name, s1, s2, date="2026-10-15", exp=5.0):
    return {"supplier_name": name, "submission_date": date, "experience_rating": exp,
            "scorecard": {1: {"score": s1, "justification": "j", "evidence": "e"},
                          2: {"score": s2, "justification": "j", "evidence": "e"}}}


class FakeLLM:
    """Stands in for the chat model: a callable the LCEL chain accepts after the prompt.

    Picks a canned reply by the supplier named in the prompt and counts calls.
    """

    def __init__(self, replies: dict[str, object]):
        self.replies = replies
        self.calls = 0

    def __call__(self, prompt_value):
        from langchain_core.messages import AIMessage
        self.calls += 1
        text = prompt_value.to_string()
        for name, reply in self.replies.items():
            if f"Supplier: {name}" in text:
                return AIMessage(content=reply if isinstance(reply, str) else json.dumps(reply))
        raise AssertionError("unexpected supplier in prompt")


FakeClient = FakeLLM  # old name, kept so existing tests read the same


def card(*scores, name="X"):
    return {"supplier_name": name, "criteria": [
        {"criterion_id": i + 1, "score": s, "max_score": 10,
         "justification": f"j{i + 1}", "evidence": f"e{i + 1}"} for i, s in enumerate(scores)],
        "risks": ["r"], "overall_summary": "s"}
