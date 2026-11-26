"""Runtime configuration.

API keys live ONLY in the project's ``.env`` file (git-ignored), loaded into the
process environment at import time. On Streamlit Community Cloud, where there is
no ``.env`` file, the same variable names are read from the app's Secrets settings
by ``load_streamlit_secrets``. Keys are never shown in the UI, logged or written
anywhere else.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = PROJECT_ROOT / ".env"
load_dotenv(ENV_FILE, override=False)  # real environment variables win over .env
DATA_DIR = Path(os.getenv("WEATHER_AGENT_DATA_DIR", PROJECT_ROOT / "data"))
REPORTS_DIR = DATA_DIR / "reports"
CHROMA_DIR = DATA_DIR / "chroma"

# Keys copied from st.secrets into the process environment.
SECRET_KEYS = (
    "GOOGLE_API_KEY",
    "GEMINI_MODEL",
    "GEMINI_EMBEDDING_MODEL",
    "LANGSMITH_API_KEY",
    "LANGSMITH_PROJECT",
    "LANGSMITH_TRACING",
    "LANGSMITH_ENDPOINT",
    "ADMIN_PASSWORD",  # unlocks owner-only views (see access.py); never shown or logged
)

# Branding (override with env vars if the product is re-badged)
COMPANY_NAME = os.getenv("APP_COMPANY_NAME", "Neural ThinkPad")
PRODUCT_NAME = os.getenv("APP_PRODUCT_NAME", "NeuralCast")
PRODUCT_TAGLINE = os.getenv("APP_PRODUCT_TAGLINE", "Weather Intelligence & Storm Prediction")
OWNER_NAME = os.getenv("APP_OWNER_NAME", "Khurram Shahzad")

DEFAULT_MODEL = "gemini-3.5-flash-lite"  # fastest & most available free model; others are fallbacks
AVAILABLE_MODELS = (
    "gemini-3.5-flash-lite",
    "gemini-3.6-flash",
    "gemini-3.8-flash",
    "gemini-3.1-flash-lite",
)
DEFAULT_EMBEDDING_MODEL = "models/gemini-embedding-001"

# Errors that mean "Google is busy, try again / try another model" (not a bug in the request).
TRANSIENT_ERROR_MARKERS = ("503", "UNAVAILABLE", "429", "RESOURCE_EXHAUSTED", "overloaded", "high demand",
                           "504", "DEADLINE_EXCEEDED", "DeadlineExceeded", "timed out", "timeout", "500 INTERNAL")
LLM_TIMEOUT_S = 60      # fail fast: the app's own model fallback is quicker than long client retries
LLM_MAX_RETRIES = 0
MODEL_COOLDOWN_S = 600  # skip a model that just failed with overload for 10 minutes


def is_transient_error(exc: BaseException) -> bool:
    text = f"{type(exc).__name__}: {exc}"
    return any(marker.lower() in text.lower() for marker in TRANSIENT_ERROR_MARKERS)


def model_chain(selected: str, cooling: dict[str, float] | None = None, now: float | None = None) -> list[str]:
    """Selected model first, then the other free models as automatic fallbacks.

    Models that recently failed with an overload (``cooling``: model -> retry-after timestamp)
    are moved to the end, so the next question goes straight to a model that is answering.
    """
    chain = [selected, *[m for m in AVAILABLE_MODELS if m != selected]]
    if not cooling:
        return chain
    import time

    t = time.time() if now is None else now
    ready = [m for m in chain if cooling.get(m, 0) <= t]
    busy = [m for m in chain if cooling.get(m, 0) > t]
    return ready + busy


@dataclass(frozen=True)
class Settings:
    google_api_key: str | None
    model: str
    embedding_model: str
    langsmith_api_key: str | None
    langsmith_project: str
    langsmith_tracing: bool

    @property
    def has_llm(self) -> bool:
        return bool(self.google_api_key)

    @property
    def has_langsmith(self) -> bool:
        return bool(self.langsmith_api_key) and self.langsmith_tracing


def get_settings() -> Settings:
    tracing = os.getenv("LANGSMITH_TRACING", "true").strip().lower() in {"1", "true", "yes"}
    return Settings(
        google_api_key=os.getenv("GOOGLE_API_KEY") or None,
        model=os.getenv("GEMINI_MODEL", DEFAULT_MODEL),
        embedding_model=os.getenv("GEMINI_EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL),
        langsmith_api_key=os.getenv("LANGSMITH_API_KEY") or None,
        langsmith_project=os.getenv("LANGSMITH_PROJECT", "weather-storm-agent"),
        langsmith_tracing=tracing,
    )


def load_streamlit_secrets(secrets) -> None:
    """Streamlit Cloud fallback: copy known keys from ``st.secrets`` into ``os.environ``.

    Only fills variables that ``.env`` / the real environment did not set, so a local
    ``.env`` always wins. Must run before the agent is built.
    """
    for key in SECRET_KEYS:
        try:
            value = secrets.get(key)
        except FileNotFoundError:  # StreamlitSecretNotFoundError: no secrets.toml locally
            break
        if value is not None and key not in os.environ:
            os.environ[key] = str(value)
    # LangSmith tracing only makes sense with a key.
    if not os.environ.get("LANGSMITH_API_KEY"):
        os.environ["LANGSMITH_TRACING"] = "false"


def ensure_dirs() -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    CHROMA_DIR.mkdir(parents=True, exist_ok=True)
