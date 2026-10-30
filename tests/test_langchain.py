"""The LangChain pieces: chat model setup, the evaluation chain, error mapping and the graph."""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import httpx
import openai
import pytest
from langchain_core.runnables import RunnableWithFallbacks

from src import repository
from src.config import PROVIDERS
from src.llm_client import LLMError, build_llm, check_key, to_llm_error
from src.orchestrator import build_graph, run_evaluation, workflow_diagram
from src.tools.evaluation_agent import build_chain, evaluate_supplier
from tests.helpers import CRITERIA, FakeLLM, card
from tests.test_pipeline import replies, uploads


def api_error(cls, status):
    request = httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions")
    return cls("boom", response=httpx.Response(status, request=request), body=None)


def test_build_llm_targets_openrouter_with_json_mode_and_fallback():
    llm = build_llm("sk-test", "openai/gpt-4o-mini")
    assert isinstance(llm, RunnableWithFallbacks)
    chat = llm.fallbacks[0]                    # the plain model used as the fallback
    assert str(chat.openai_api_base).startswith("https://openrouter.ai/api/v1")
    assert chat.model_name == "openai/gpt-4o-mini" and chat.temperature == 0
    assert llm.runnable.kwargs == {"response_format": {"type": "json_object"}}


@pytest.mark.parametrize("key,model", [("", "m"), ("  ", "m"), ("k", ""), (None, "m")])
def test_build_llm_requires_key_and_model(key, model):
    with pytest.raises(LLMError):
        build_llm(key, model)


def test_provider_errors_are_translated_without_leaking_details():
    for cls, status, text in [(openai.AuthenticationError, 401, "Authentication failed"),
                              (openai.PermissionDeniedError, 403, "denied access"),
                              (openai.RateLimitError, 429, "Rate limit"),
                              (openai.NotFoundError, 404, "not found"),
                              (openai.BadRequestError, 400, "rejected")]:
        err = to_llm_error(api_error(cls, status))
        assert isinstance(err, LLMError) and text in str(err) and "boom" not in str(err)
    assert to_llm_error(ValueError("x")) is None


def test_chain_is_prompt_model_parser_and_returns_parsed_json():
    chain = build_chain(FakeLLM({"Apex": card(9, 8)}))
    out = chain.invoke({"supplier_name": "Apex", "gap_note": "", "criteria_lines": "-",
                        "schema": "{}", "proposal_text": "text with {braces}", "retry_note": ""})
    assert out["criteria"][0]["score"] == 9


def test_invalid_json_gets_exactly_one_retry():
    llm = FakeLLM({"Apex": "definitely not json"})
    parsed, warnings = evaluate_supplier(llm, CRITERIA, "Apex", "proposal")
    assert parsed is None and llm.calls == 2
    assert "after a retry" in warnings[0]


def test_provider_error_inside_the_chain_aborts_with_a_safe_message():
    def failing(_prompt):
        raise api_error(openai.AuthenticationError, 401)
    with pytest.raises(LLMError, match="Authentication failed"):
        evaluate_supplier(failing, CRITERIA, "Apex", "proposal")


def test_graph_has_one_node_per_workflow_step_in_order():
    nodes = list(build_graph(None, None).get_graph().nodes)
    steps = ["load_criteria", "validate_input", "inspect_documents",
             "evaluate_suppliers", "rank", "persist"]
    assert [n for n in nodes if n in steps] == steps
    diagram = workflow_diagram()
    assert "evaluate_suppliers" in diagram and "persist" in diagram


def test_graph_run_matches_run_evaluation_and_records_model(tmp_path):
    conn = repository.connect(tmp_path / "g.db")
    llm = FakeLLM(replies())
    final = build_graph(conn, llm, model_name="vendor/model").invoke({"uploads": uploads()})
    run = final["result"]
    assert run["model"] == "vendor/model" and len(run["suppliers"]) == 4
    assert repository.load_run(conn, run["rfp_run_id"]) == run
    assert run_evaluation(conn, FakeLLM(replies()), uploads())["suppliers"][0]["final_rank"] == 1


# ---- a real HTTP round trip against a local OpenAI-compatible server (no network, no key)
class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self.server.seen.append({"path": self.path, "auth": self.headers.get("Authorization"), "body": body})
        if self.server.reject_json_mode and "response_format" in body:
            self.send_response(400)
            payload = {"error": {"message": "response_format unsupported", "type": "invalid_request_error"}}
        else:
            self.send_response(200)
            payload = {"id": "x", "object": "chat.completion", "created": 0, "model": body["model"],
                       "choices": [{"index": 0, "finish_reason": "stop",
                                    "message": {"role": "assistant", "content": json.dumps(card(7, 6, name="Apex"))}}],
                       "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}}
        data = json.dumps(payload).encode()
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


@pytest.fixture
def local_provider():
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    server.seen, server.reject_json_mode = [], False
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield server, f"http://127.0.0.1:{server.server_port}/v1"
    server.shutdown()


def test_real_http_request_shape_and_parsed_result(local_provider):
    server, url = local_provider
    llm = build_llm("sk-secret", "vendor/model", base_url=url)
    parsed, warnings = evaluate_supplier(llm, CRITERIA, "Apex", "proposal text")
    assert warnings == [] and parsed["criteria"][0]["score"] == 7
    sent = server.seen[0]
    assert sent["path"] == "/v1/chat/completions" and sent["auth"] == "Bearer sk-secret"
    assert sent["body"]["model"] == "vendor/model" and sent["body"]["temperature"] == 0
    assert sent["body"]["response_format"] == {"type": "json_object"}
    assert [m["role"] for m in sent["body"]["messages"]] == ["system", "user"]
    assert "Supplier: Apex" in sent["body"]["messages"][1]["content"]


def test_model_without_json_mode_falls_back_to_a_plain_request(local_provider):
    server, url = local_provider
    server.reject_json_mode = True
    llm = build_llm("sk-secret", "vendor/model", base_url=url)
    parsed, _ = evaluate_supplier(llm, CRITERIA, "Apex", "proposal text")
    assert parsed["criteria"][0]["score"] == 7
    assert "response_format" in server.seen[0]["body"] and "response_format" not in server.seen[1]["body"]


# ---- provider selection
@pytest.mark.parametrize("provider,expected_url", [
    ("OpenRouter", "https://openrouter.ai/api/v1"),
    ("OpenAI", "https://api.openai.com/v1"),
    ("Google Gemini", "https://generativelanguage.googleapis.com/v1beta/openai")])
def test_each_provider_builds_a_chat_model_for_its_own_endpoint(provider, expected_url):
    model = PROVIDERS[provider]["default_model"]
    llm = build_llm("key", model, provider)
    chat = llm.fallbacks[0]
    assert str(chat.openai_api_base).rstrip("/") == expected_url
    assert chat.model_name == model


def test_unknown_provider_and_missing_key_name_the_provider():
    with pytest.raises(LLMError, match="Unknown provider"):
        build_llm("k", "m", "Nope")
    with pytest.raises(LLMError, match="OpenAI API key"):
        build_llm("", "gpt-4o-mini", "OpenAI")


@pytest.mark.parametrize("model,has_temperature", [("gpt-4o-mini", True), ("openai/gpt-4o", True),
                                                   ("gemini-2.5-flash", True), ("o3-mini", False),
                                                   ("openai/o1", False), ("gpt-5", False)])
def test_reasoning_models_do_not_get_a_custom_temperature(model, has_temperature):
    chat = build_llm("k", model, "OpenAI").fallbacks[0]
    assert (chat.temperature == 0) is has_temperature


class _KeyServer(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        self.server.paths.append(self.path)
        ok = self.headers.get("Authorization") == "Bearer good"
        self.send_response(200 if ok else self.server.bad_status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"data": []}')


@pytest.fixture
def key_server():
    server = HTTPServer(("127.0.0.1", 0), _KeyServer)
    server.paths, server.bad_status = [], 401
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield server, f"http://127.0.0.1:{server.server_port}"
    server.shutdown()


@pytest.mark.parametrize("provider,path", [("OpenRouter", "/auth/key"), ("OpenAI", "/models"),
                                           ("Google Gemini", "/models")])
def test_key_check_uses_each_providers_endpoint(key_server, provider, path):
    server, url = key_server
    check_key("good", provider, base_url=url)
    assert server.paths == [path]


@pytest.mark.parametrize("status", [400, 401, 403])
def test_rejected_key_is_reported_with_the_provider_name(key_server, status):
    server, url = key_server
    server.bad_status = status
    with pytest.raises(LLMError, match="Google Gemini API key"):
        check_key("bad", "Google Gemini", base_url=url)


def test_unreachable_provider_is_reported():
    with pytest.raises(LLMError, match="Could not reach OpenAI"):
        check_key("k", "OpenAI", base_url="http://127.0.0.1:1")
