"""Chroma vector database of saved analyses (Gemini embeddings).

Every PDF report is also indexed here so the agent and the web app can do
semantic search over past analyses ("storms in Punjab last week").
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone
from typing import Any

from . import config

log = logging.getLogger(__name__)

COLLECTION = "weather_analyses"
_stores: dict[str, Any] = {}
_lock = threading.Lock()


def get_store(api_key: str | None = None):
    """Lazily build the Chroma store for a Gemini key.

    ``api_key`` overrides the server key (a visitor's own key). It is passed to the
    embeddings client explicitly and never written to ``os.environ``, which is shared
    by all sessions on Streamlit Cloud. Returns None when no key is available.
    """
    settings = config.get_settings()
    key = api_key or settings.google_api_key
    if not key:
        return None
    with _lock:
        store = _stores.get(key)
        if store is None:
            from langchain_chroma import Chroma
            from langchain_google_genai import GoogleGenerativeAIEmbeddings

            config.ensure_dirs()
            embeddings = GoogleGenerativeAIEmbeddings(model=settings.embedding_model, google_api_key=key)
            store = Chroma(
                collection_name=COLLECTION,
                embedding_function=embeddings,
                persist_directory=str(config.CHROMA_DIR),
            )
            _stores[key] = store
    return store


def add_analysis(
    analysis_name: str,
    city: str,
    text: str,
    pdf_file: str,
    storm_risk: str,
    extra: dict[str, Any] | None = None,
    api_key: str | None = None,
    owner: str = "",
) -> str | None:
    """Index an analysis. ``owner`` = visitor id of the session that created it (see ``search``)."""
    store = get_store(api_key)
    if store is None:
        return None
    meta: dict[str, Any] = {
        "analysis_name": analysis_name,
        "city": city,
        "pdf_file": pdf_file,
        "storm_risk": storm_risk,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "owner": owner,
    }
    for k, v in (extra or {}).items():
        if k not in meta and isinstance(v, (str, int, float, bool)):  # extra can never overwrite owner
            meta[k] = v
    doc_text = f"{analysis_name}\nCity: {city}\nStorm risk: {storm_risk}\n\n{text}"
    ids = store.add_texts([doc_text], metadatas=[meta])
    return ids[0] if ids else None


def search_filter(city: str | None, owner: str, see_all: bool) -> dict[str, Any] | None:
    """Chroma ``where`` filter: the visitor's own analyses (optionally one city); everything for the owner."""
    conds: list[dict[str, Any]] = []
    if not see_all:
        conds.append({"owner": owner})
    if city:
        conds.append({"city": city})
    if not conds:
        return None
    return conds[0] if len(conds) == 1 else {"$and": conds}


def search(query: str, k: int = 4, city: str | None = None, api_key: str | None = None,
           owner: str = "", see_all: bool = False) -> list[dict[str, Any]]:
    """Semantic search over the analyses this viewer may see (deny by default: no owner -> nothing)."""
    if not see_all and not owner:
        return []
    store = get_store(api_key)
    if store is None:
        return []
    kwargs: dict[str, Any] = {"k": k}
    where = search_filter(city, owner, see_all)
    if where:
        kwargs["filter"] = where
    results = store.similarity_search_with_relevance_scores(query, **kwargs)
    out = []
    for doc, score in results:
        out.append({
            "score": round(float(score), 3),
            "analysis_name": doc.metadata.get("analysis_name"),
            "city": doc.metadata.get("city"),
            "storm_risk": doc.metadata.get("storm_risk"),
            "created_at": doc.metadata.get("created_at"),
            "pdf_file": doc.metadata.get("pdf_file"),
            "excerpt": doc.page_content[:600],
        })
    return out


def count(api_key: str | None = None) -> int:
    store = get_store(api_key)
    if store is None:
        return 0
    return store._collection.count()  # langchain-chroma exposes no public count()
