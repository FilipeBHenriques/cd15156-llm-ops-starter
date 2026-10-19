"""Tests for src.tracing.trace_export rendering helpers."""

import json

import pandas as pd

from src.tracing.trace_export import (
    render_json,
    render_markdown,
    summarize_traces,
)


def _two_span_trace(trace_id: str = "trace_a") -> pd.DataFrame:
    """Build a synthetic Phoenix span DataFrame: request root + 2 children.

    Mirrors the real shape produced by router.py + phoenix_backend.py:
    an outer "request" span (opened by route_query, wraps classification
    + the whole pipeline) is the true root; "rag_query" is a CHILD of
    it (opened by traced_pipeline); "rag_generation" is a grandchild.
    Nested span attributes under ``rag.*`` flatten into a single
    dict-valued column ``attributes.rag``, not into per-key flat
    columns, and live on the ``rag_query`` span specifically. Token
    counts live on the ``rag_generation`` child span.
    """
    return pd.DataFrame(
        [
            {
                "context.trace_id": trace_id,
                "name": "request",
                "parent_id": None,
                "start_time": pd.Timestamp("2026-04-29 12:00:00.000"),
                "end_time": pd.Timestamp("2026-04-29 12:00:01.000"),
                "attributes.input.value": None,
                "attributes.rag": None,
                "attributes.llm.token_count.prompt": None,
                "attributes.llm.token_count.completion": None,
            },
            {
                "context.trace_id": trace_id,
                "name": "rag_query",
                "parent_id": "request_span",
                "start_time": pd.Timestamp("2026-04-29 12:00:00.050"),
                "end_time": pd.Timestamp("2026-04-29 12:00:00.950"),
                "attributes.input.value": "How heavy is the Selkirk?",
                "attributes.rag": {
                    "model": "gpt-4o-mini",
                    "latency_ms": 850.0,
                },
                "attributes.llm.token_count.prompt": None,
                "attributes.llm.token_count.completion": None,
            },
            {
                "context.trace_id": trace_id,
                "name": "rag_generation",
                "parent_id": "rag_query_span",
                "start_time": pd.Timestamp("2026-04-29 12:00:00.100"),
                "end_time": pd.Timestamp("2026-04-29 12:00:00.900"),
                "attributes.input.value": None,
                "attributes.rag": None,
                "attributes.llm.token_count.prompt": 120,
                "attributes.llm.token_count.completion": 30,
            },
        ]
    )


# --- summarize_traces -------------------------------------------------------


def test_summarize_traces_groups_by_trace_id():
    df = _two_span_trace()
    summaries = summarize_traces(df, last_n=10)

    assert len(summaries) == 1
    s = summaries[0]
    assert s["trace_id"] == "trace_a"[:8]
    assert "How heavy" in s["question"]
    assert s["model"] == "gpt-4o-mini"
    # Root ("request") spans 12:00:00.000 -> 12:00:01.000 = 1000ms total,
    # which now covers classification + the whole pipeline — not just
    # the old rag.latency_ms attribute (850ms), which only measured the
    # inner rag_query span.
    assert s["latency_ms"] == 1000.0
    assert s["prompt_tokens"] == 120
    assert s["completion_tokens"] == 30


def test_summarize_traces_identifies_slowest_child():
    df = _two_span_trace()
    summaries = summarize_traces(df, last_n=10)

    s = summaries[0]
    # rag_query (900ms: .050 -> .950) wraps rag_generation (800ms) plus
    # retrieval, so it's the slowest *child* of the request root — this
    # matches the real seed-trace evidence where rag_query is reported
    # as the slowest step.
    assert s["slowest_span"] == "rag_query"
    assert s["slowest_ms"] == 900.0


def test_summarize_traces_handles_empty_df():
    summaries = summarize_traces(pd.DataFrame(), last_n=10)
    assert summaries == []


def test_summarize_traces_returns_at_most_last_n():
    rows = []
    for i in range(15):
        rows.extend(
            _two_span_trace(trace_id=f"trace_{i:02d}").to_dict("records")
        )
    df = pd.DataFrame(rows)

    summaries = summarize_traces(df, last_n=5)
    assert len(summaries) == 5


def test_summarize_traces_skips_traces_with_no_root():
    """A trace that only contains child spans is silently skipped."""
    df = pd.DataFrame(
        [
            {
                "context.trace_id": "orphan",
                "name": "rag_generation",  # no rag_query parent
                "parent_id": "missing_root",
                "start_time": pd.Timestamp("2026-04-29 12:00:00"),
                "end_time": pd.Timestamp("2026-04-29 12:00:01"),
                "attributes.input.value": None,
                "attributes.rag": None,
                "attributes.llm.token_count.prompt": None,
                "attributes.llm.token_count.completion": None,
            }
        ]
    )
    summaries = summarize_traces(df, last_n=10)
    assert summaries == []


# --- render_markdown --------------------------------------------------------


def test_render_markdown_with_traces():
    summaries = [
        {
            "trace_id": "abcd1234",
            "question": "test q",
            "model": "gpt-4o-mini",
            "latency_ms": 100.0,
            "prompt_tokens": 50,
            "completion_tokens": 10,
            "slowest_span": "rag_generation",
            "slowest_ms": 80.0,
            "start_time": "2026-04-29",
        }
    ]
    output = render_markdown(summaries, total=1)

    assert "# Phoenix Trace Export" in output
    assert "1 trace(s) captured" in output
    assert "abcd1234" in output
    assert "test q" in output
    assert "gpt-4o-mini" in output
    assert "rag_generation" in output


def test_render_markdown_empty():
    output = render_markdown([], total=0)
    assert "No traces found" in output


# --- render_json ------------------------------------------------------------


def test_render_json_roundtrips():
    summaries = [
        {"trace_id": "abc", "question": "q", "latency_ms": 100.0},
    ]
    parsed = json.loads(render_json(summaries))
    assert parsed == summaries