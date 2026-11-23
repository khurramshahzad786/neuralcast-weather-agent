"""LangSmith usage meter: project statistics and recent traces, read with the LangSmith API.

Only metadata is returned (counts, tokens, latency, status, short error text); API keys are read
from the environment by the LangSmith client and never exposed.
"""

from __future__ import annotations

import warnings
from datetime import timedelta
from typing import Any

from .config import get_settings


def _secs(value: Any) -> float | None:
    if isinstance(value, timedelta):
        return round(value.total_seconds(), 2)
    return None


def project_stats(project: str | None = None) -> dict[str, Any]:
    """Totals for the LangSmith project, or {'error': ...} when unavailable."""
    settings = get_settings()
    if not settings.has_langsmith:
        return {"error": "LangSmith is not configured (add LANGSMITH_API_KEY to .env)."}
    from langsmith import Client

    name = project or settings.langsmith_project
    try:
        p = Client().read_project(project_name=name, include_stats=True)
    except Exception as exc:  # noqa: BLE001 - network/auth/not-found are all "unavailable" for the UI
        msg = str(exc)
        if "not found" in msg.lower() or "404" in msg:
            return {"error": f"No traces yet: project '{name}' will appear after the first agent run."}
        return {"error": f"LangSmith unavailable: {type(exc).__name__}: {msg[:200]}"}
    return {
        "project": p.name,
        "url": getattr(p, "url", None),
        "run_count": p.run_count or 0,
        "total_tokens": p.total_tokens or 0,
        "prompt_tokens": p.prompt_tokens or 0,
        "completion_tokens": p.completion_tokens or 0,
        "total_cost": float(p.total_cost or 0),
        "error_rate": float(p.error_rate or 0),
        "latency_p50_s": _secs(p.latency_p50),
        "latency_p99_s": _secs(p.latency_p99),
        "last_run": p.last_run_start_time.isoformat() if p.last_run_start_time else None,
    }


def recent_runs(project: str | None = None, limit: int = 15) -> list[dict[str, Any]]:
    """Most recent root traces (one per agent question)."""
    settings = get_settings()
    if not settings.has_langsmith:
        return []
    from langsmith import Client

    name = project or settings.langsmith_project
    client = Client()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # list_runs deprecation notice (still supported)
        try:
            runs = list(client.list_runs(project_name=name, is_root=True, limit=limit))
        except Exception:  # noqa: BLE001 - meter is optional
            return []
    out = []
    for r in runs:
        latency = (r.end_time - r.start_time).total_seconds() if r.end_time and r.start_time else None
        meta = (r.extra or {}).get("metadata", {}) if isinstance(r.extra, dict) else {}
        out.append({
            "id": str(r.id),
            "name": r.name,
            "status": r.status,
            "start_time": r.start_time,
            "latency_s": round(latency, 1) if latency is not None else None,
            "total_tokens": r.total_tokens or 0,
            "model": meta.get("model", ""),
            "agent": meta.get("agent", ""),
            "error": (r.error or "")[:120],
        })
    return out
