"""Upload one historical agent interaction to Somia (run + optional feedback).

Use for CSV/DB backfills — not for live LangGraph callback wiring.

Contract:
- Eval-eligible top-level input/output (dicts preferred).
- Optional sdk-1.0 trace via SomiaTrace.to_dict() (minimal root span is fine).
- Stable idempotency_key per source row.
- Feedback: create text/status, then update for scores (create has no score fields).
- Skip feedback when log_run returns no fresh trace_id (idempotent replay).
"""

from __future__ import annotations

import os
from typing import Any

from somia import SomiaClient, SomiaTrace


def attach_thumbs_feedback(
    client: SomiaClient,
    *,
    trace_id: str,
    thumbs_up: bool,
    comment: str | None = None,
    ground_truth: str | None = None,
    status: str = "PENDING",
) -> Any:
    """Create feedback text, then set boolean score via update."""
    created = client.traces.feedback.create(
        trace_id,
        feedback=(comment or "").strip() or "Reaction",
        ground_truth=ground_truth,
        status=status,
    )
    return client.traces.feedback.update(
        created.id,
        score_type="boolean",
        score=1 if thumbs_up else 0,
    )


def upload_historical_record(
    client: SomiaClient,
    *,
    agent_slug: str,
    record_id: str,
    user_input: Any,
    agent_output: Any,
    agent_version: str | None = None,
    thumbs_up: bool | None = None,
    feedback_comment: str | None = None,
    ground_truth: str | None = None,
    extra_metadata: dict[str, Any] | None = None,
    include_minimal_trace: bool = True,
) -> dict[str, Any]:
    """Log one past interaction; optionally attach thumbs feedback."""
    metadata: dict[str, Any] = {
        "source": "historical_import",
        "external_id": record_id,
    }
    if thumbs_up is not None:
        metadata["thumbs"] = "thumbs_up" if thumbs_up else "thumbs_down"
    if extra_metadata:
        metadata.update(extra_metadata)

    trace_payload = None
    if include_minimal_trace:
        trace = SomiaTrace().start()
        with trace.span(name="agent", kind="agent", inputs=user_input) as span:
            span.finish(outputs=agent_output)
        trace.finish(status="OK")
        trace_payload = trace.to_dict()

    run_result = client.log_run(
        agent_slug=agent_slug,
        input=user_input,
        output=agent_output,
        trace=trace_payload,
        agent_version=agent_version,
        status="SUCCESS",
        metadata=metadata,
        idempotency_key=f"historical-{record_id}",
    )

    feedback_id = None
    trace_id = run_result.get("trace_id")
    if thumbs_up is not None and trace_id:
        fb = attach_thumbs_feedback(
            client,
            trace_id=str(trace_id),
            thumbs_up=thumbs_up,
            comment=feedback_comment,
            ground_truth=ground_truth,
        )
        feedback_id = getattr(fb, "id", None)

    return {
        "run_id": run_result.get("run_id"),
        "trace_id": trace_id,
        "feedback_id": feedback_id,
    }


def example() -> None:
    with SomiaClient(
        base_url=os.getenv(
            "SOMIA_BASE_URL", "https://platform.somiasolutions.com/api"
        ),
        api_key=os.environ["SOMIA_API_KEY"],
    ) as client:
        result = upload_historical_record(
            client,
            agent_slug=os.environ["SOMIA_AGENT_SLUG"],
            record_id="42",
            user_input={"prompt": "What is Somia?"},
            agent_output={"response": "An agent validation platform."},
            agent_version=os.getenv("SOMIA_AGENT_VERSION"),
            thumbs_up=True,
            feedback_comment="Clear answer",
            extra_metadata={"original_timestamp": "2026-08-01T12:00:00Z"},
        )
        print(result)


if __name__ == "__main__":
    example()
