"""Token accounting for every LLM call (main agent and sub-agents)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from langchain_core.callbacks import UsageMetadataCallbackHandler


@dataclass
class RunUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    llm_calls: int = 0
    by_model: dict[str, dict[str, int]] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "llm_calls": self.llm_calls,
            "by_model": self.by_model,
        }


class UsageTracker(UsageMetadataCallbackHandler):
    """Collects ``usage_metadata`` from every chat-model response in a run."""

    def __init__(self) -> None:
        super().__init__()
        self.llm_calls = 0

    def on_llm_end(self, response, **kwargs: Any) -> None:  # noqa: ANN001
        self.llm_calls += 1
        super().on_llm_end(response, **kwargs)

    def summary(self) -> RunUsage:
        u = RunUsage(llm_calls=self.llm_calls)
        for model, meta in (self.usage_metadata or {}).items():
            inp = int(meta.get("input_tokens", 0) or 0)
            out = int(meta.get("output_tokens", 0) or 0)
            tot = int(meta.get("total_tokens", inp + out) or 0)
            u.by_model[model] = {"input_tokens": inp, "output_tokens": out, "total_tokens": tot}
            u.input_tokens += inp
            u.output_tokens += out
            u.total_tokens += tot
        return u
