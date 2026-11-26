"""LangSmith evaluation of the weather & storm Deep Agent.

Usage:
    python -m evals.run_eval                       # LangSmith experiment (needs LANGSMITH_API_KEY)
    python -m evals.run_eval --local               # run locally, print a table, nothing uploaded
    python -m evals.run_eval --model gemini-3.5-flash-lite --limit 3

Evaluators
----------
- tool_selection   fraction of expected tools that were called (main agent or sub-agents)
- mentions_city    answer names the requested city / country
- no_tool_errors   no tool raised an exception during the run
- coverage_judge   LLM-as-judge (Gemini): does the answer cover the required facts, quote
                   concrete numbers with units, and avoid invented data? (0-1)
- total_tokens / llm_calls / latency_s   cost & efficiency metrics (also visible in traces)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Any
from uuid import UUID

from langchain_core.callbacks import BaseCallbackHandler
from pydantic import BaseModel, Field

from weather_agent import agent as wagent
from weather_agent.config import get_settings
from weather_agent.usage import UsageTracker

from .dataset import DATASET_NAME, EXAMPLES


class ToolRecorder(BaseCallbackHandler):
    """Records every tool invocation, including those made inside sub-agents."""

    def __init__(self) -> None:
        self.tools: list[str] = []
        self.errors: list[str] = []

    def on_tool_start(self, serialized: dict[str, Any], input_str: str, **kwargs: Any) -> None:
        self.tools.append((serialized or {}).get("name") or kwargs.get("name", "?"))

    def on_tool_error(self, error: BaseException, *, run_id: UUID, **kwargs: Any) -> None:
        self.errors.append(f"{type(error).__name__}: {error}")


def make_target(model: str):
    def target(inputs: dict) -> dict:
        graph = wagent.build_agent(model_name=model, owner="eval", see_all=True)  # run by the owner
        usage, recorder = UsageTracker(), ToolRecorder()
        start = time.perf_counter()
        result = graph.invoke(
            {"messages": [{"role": "user", "content": inputs["question"]}]},
            config={"callbacks": [usage, recorder], "recursion_limit": 80,
                    "run_name": "weather-agent-eval", "tags": ["eval", model]},
        )
        u = usage.summary()
        return {
            "answer": wagent.final_text(result),
            "tools": recorder.tools,
            "tool_errors": recorder.errors,
            "total_tokens": u.total_tokens,
            "input_tokens": u.input_tokens,
            "output_tokens": u.output_tokens,
            "llm_calls": u.llm_calls,
            "latency_s": round(time.perf_counter() - start, 2),
        }

    return target


# ------------------------------------------------------------------ evaluators
def tool_selection(outputs: dict, reference_outputs: dict) -> dict:
    expected = reference_outputs.get("expected_tools", [])
    used = set(outputs.get("tools", []))
    hit = sum(1 for t in expected if t in used)
    return {"key": "tool_selection", "score": hit / len(expected) if expected else 1.0,
            "comment": f"expected={expected} used={sorted(used)}"}


def mentions_city(outputs: dict, reference_outputs: dict) -> dict:
    city = reference_outputs.get("city", "")
    ok = city.lower().split("-")[0] in (outputs.get("answer") or "").lower()
    return {"key": "mentions_city", "score": int(ok)}


def no_tool_errors(outputs: dict) -> dict:
    errs = outputs.get("tool_errors", [])
    return {"key": "no_tool_errors", "score": int(not errs), "comment": "; ".join(errs)[:500]}


def cost_metrics(outputs: dict) -> list[dict]:
    return [
        {"key": "total_tokens", "score": outputs.get("total_tokens", 0)},
        {"key": "llm_calls", "score": outputs.get("llm_calls", 0)},
        {"key": "latency_s", "score": outputs.get("latency_s", 0)},
    ]


class Grade(BaseModel):
    reasoning: str = Field(description="One or two sentences explaining the grade.")
    score: float = Field(ge=0, le=1, description="0 = fails, 1 = fully meets the criteria.")


JUDGE_PROMPT = """You grade a weather assistant's answer.
Question: {question}
Required coverage: {must_cover}
Answer:
---
{answer}
---
Tools used: {tools}

Score 1.0 if the answer covers every required item, quotes concrete values with units where
relevant, gives a clear risk/conclusion, and does not invent data the tools could not provide.
Deduct for missing items, vague statements, or numbers with no tool call behind them."""


def make_judge(model: str):
    judge = wagent.build_llm(model, temperature=0).with_structured_output(Grade)

    def coverage_judge(inputs: dict, outputs: dict, reference_outputs: dict) -> dict:
        grade: Grade = judge.invoke(JUDGE_PROMPT.format(
            question=inputs["question"],
            must_cover=", ".join(reference_outputs.get("must_cover", [])),
            answer=(outputs.get("answer") or "")[:6000],
            tools=", ".join(outputs.get("tools", [])),
        ))
        return {"key": "coverage_judge", "score": grade.score, "comment": grade.reasoning}

    return coverage_judge


# ------------------------------------------------------------------ runners
def ensure_dataset(client) -> None:
    if client.has_dataset(dataset_name=DATASET_NAME):
        return
    client.create_dataset(DATASET_NAME, description="Behavioural eval set for the weather & storm agent")
    client.create_examples(dataset_name=DATASET_NAME, examples=EXAMPLES)


def run_langsmith(model: str, judge_model: str, limit: int | None) -> None:
    from langsmith import Client, evaluate

    client = Client()
    ensure_dataset(client)
    data = client.list_examples(dataset_name=DATASET_NAME, limit=limit) if limit else DATASET_NAME
    results = evaluate(
        make_target(model),
        data=data,
        evaluators=[tool_selection, mentions_city, no_tool_errors, cost_metrics, make_judge(judge_model)],
        experiment_prefix=f"weather-agent-{model}",
        metadata={"model": model, "judge": judge_model},
        max_concurrency=1,  # stay within Gemini free-tier rate limits
        client=client,
    )
    print(f"Experiment: {results.experiment_name} - open it at https://smith.langchain.com")


def run_local(model: str, judge_model: str, limit: int | None) -> None:
    target, judge = make_target(model), make_judge(judge_model)
    rows = []
    for ex in EXAMPLES[:limit] if limit else EXAMPLES:
        out = target(ex["inputs"])
        ref = ex["outputs"]
        scores = {
            "tool_selection": tool_selection(out, ref)["score"],
            "mentions_city": mentions_city(out, ref)["score"],
            "no_tool_errors": no_tool_errors(out)["score"],
            "coverage_judge": judge(ex["inputs"], out, ref)["score"],
        }
        rows.append({"question": ex["inputs"]["question"][:60], **scores,
                     "tokens": out["total_tokens"], "llm_calls": out["llm_calls"], "latency_s": out["latency_s"]})
        print(json.dumps(rows[-1]))
    n = len(rows)
    if n:
        print("\nAVERAGES:", json.dumps({k: round(sum(r[k] for r in rows) / n, 3) for k in
                                         ("tool_selection", "mentions_city", "no_tool_errors",
                                          "coverage_judge", "tokens", "latency_s")}))


def main(argv: list[str] | None = None) -> int:
    settings = get_settings()
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--model", default=settings.model)
    p.add_argument("--judge-model", default=settings.model)
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--local", action="store_true", help="Run without uploading to LangSmith")
    args = p.parse_args(argv)

    if not settings.google_api_key:
        print("GOOGLE_API_KEY is not set (.env or environment).", file=sys.stderr)
        return 2
    if args.local or not os.getenv("LANGSMITH_API_KEY"):
        if not args.local:
            print("LANGSMITH_API_KEY not set - running locally.", file=sys.stderr)
        os.environ["LANGSMITH_TRACING"] = "false"
        run_local(args.model, args.judge_model, args.limit)
    else:
        run_langsmith(args.model, args.judge_model, args.limit)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
