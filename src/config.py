from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "rfp.db"

# Providers the user can choose in the UI. All are reached through LangChain's ChatOpenAI because
# each exposes an OpenAI-compatible chat API (Gemini via Google's official compatibility endpoint).
# `models` are suggestions only; the UI also accepts any model name the provider supports.
PROVIDERS = {
    "OpenRouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "key_check": "/auth/key",
        "key_url": "https://openrouter.ai/keys",
        "default_model": "openai/gpt-4o-mini",
        "models": ["openai/gpt-4o-mini", "openai/gpt-4o", "google/gemini-2.5-flash",
                   "anthropic/claude-3.5-sonnet"],
    },
    "OpenAI": {
        "base_url": "https://api.openai.com/v1",
        "key_check": "/models",
        "key_url": "https://platform.openai.com/api-keys",
        "default_model": "gpt-4o-mini",
        "models": ["gpt-4o-mini", "gpt-4o", "gpt-4.1-mini", "gpt-4.1"],
    },
    "Google Gemini": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "key_check": "/models",
        "key_url": "https://aistudio.google.com/app/apikey",
        "default_model": "gemini-2.5-flash",
        "models": ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-2.0-flash"],
    },
}
DEFAULT_PROVIDER = "OpenRouter"

MAX_SUPPLIERS = 6
MAX_DOC_CHARS = 60_000   # text sent to the LLM per proposal
MIN_DOC_CHARS = 200      # below this the PDF is treated as unreadable (e.g. scanned)
WEIGHT_TOLERANCE = 0.01  # active weights must total 100 within this tolerance

MAX_PDF_BYTES = 10 * 1024 * 1024  # reject larger uploads
MAX_PDF_PAGES = 40
MAX_NAME_LENGTH = 80
MIN_SECTIONS_FOUND = 3            # fewer expected sections than this = not an RFP response
