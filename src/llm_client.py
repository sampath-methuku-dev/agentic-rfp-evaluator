"""The only module that talks to an LLM provider, through LangChain's ChatOpenAI.

Supported providers are listed in `config.PROVIDERS` (OpenRouter, OpenAI, Google Gemini). The API
key is passed in by the caller for the chosen provider. It is never read from the environment or
files, and error messages shown to the user never contain it.
"""
import json
import urllib.error
import urllib.request

import openai
from langchain_core.runnables import Runnable
from langchain_openai import ChatOpenAI

from src.config import DEFAULT_PROVIDER, PROVIDERS

# Reasoning-style models reject a custom temperature, so it is left at the provider default for them.
_NO_TEMPERATURE_PREFIXES = ("o1", "o3", "o4", "gpt-5")


class LLMError(Exception):
    """A provider failure with a message that is safe to show (no key, no raw payload)."""


def provider_config(provider: str) -> dict:
    if provider not in PROVIDERS:
        raise LLMError(f"Unknown provider '{provider}'. Choose one of: {', '.join(PROVIDERS)}.")
    return PROVIDERS[provider]


def _temperature(model: str) -> dict:
    short_name = model.lower().rsplit("/", 1)[-1]
    return {} if short_name.startswith(_NO_TEMPERATURE_PREFIXES) else {"temperature": 0}


def build_llm(api_key: str, model: str, provider: str = DEFAULT_PROVIDER,
              base_url: str | None = None) -> Runnable:
    """A LangChain chat model for the chosen provider that asks for JSON output.

    If a model does not support JSON mode, the call falls back to a plain request; the
    prompt itself still demands JSON only. `base_url` overrides the provider's URL (for tests).
    """
    config = provider_config(provider)
    key, name = (api_key or "").strip(), (model or "").strip()
    if not key:
        raise LLMError(f"No {provider} API key provided.")
    if not name:
        raise LLMError("No model provided.")
    chat = ChatOpenAI(model=name, api_key=key, base_url=(base_url or config["base_url"]).rstrip("/"),
                      timeout=90, max_retries=1, **_temperature(name))
    return chat.bind(response_format={"type": "json_object"}).with_fallbacks(
        [chat], exceptions_to_handle=(openai.BadRequestError,))


def check_key(api_key: str, provider: str = DEFAULT_PROVIDER, base_url: str | None = None) -> None:
    """Free, token-less check that the provider accepts this key."""
    config = provider_config(provider)
    request = urllib.request.Request(
        f"{(base_url or config['base_url']).rstrip('/')}{config['key_check']}",
        headers={"Authorization": f"Bearer {(api_key or '').strip()}"})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            json.load(response)
    except urllib.error.HTTPError as exc:
        # Google answers an invalid key with 400; the others use 401/403.
        if exc.code in (400, 401, 403):
            raise LLMError(f"Authentication failed: check your {provider} API key.") from None
        raise LLMError(f"{provider} key check failed with HTTP {exc.code}.") from None
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        raise LLMError(f"Could not reach {provider} to verify the key.") from None


def to_llm_error(exc: Exception) -> LLMError | None:
    """Translate a provider exception into a safe message; None if it is not a provider error."""
    if isinstance(exc, openai.AuthenticationError):
        return LLMError("Authentication failed: check your API key for the selected provider.")
    if isinstance(exc, openai.PermissionDeniedError):
        return LLMError("The selected provider denied access: check the key's permissions.")
    if isinstance(exc, openai.RateLimitError):
        return LLMError("Rate limit or quota reached with the selected provider.")
    if isinstance(exc, openai.NotFoundError):
        return LLMError("The selected model was not found for this provider.")
    if isinstance(exc, openai.BadRequestError):
        return LLMError("The provider rejected the request for this model.")
    if isinstance(exc, openai.APIError):
        return LLMError(f"LLM request failed ({type(exc).__name__}).")
    return None
