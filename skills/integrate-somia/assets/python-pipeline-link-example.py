"""Parent agent linking a child Somia pipeline run.

Use when this agent calls another Somia agent (external log_run / start_run)
or a hosted pipeline (sessions.run). Nested start_run in the same process is
NOT composition — it shares the outer run.

Contract:
- One root run per agent.
- Call link_child_pipeline_run inside the span that made the child call.
- Hosted: child.session_id is the run id. External: log_run result["run_id"].
- Prefer the helper; do not hand-build span links.
"""

from __future__ import annotations

from typing import Any

from somia import SomiaClient, link_child_pipeline_run, node_span, start_run


def run_orchestrator(
    *,
    payload: Any,
    child_agent_id: int,
    child_pipeline_id: int | None = None,
) -> Any:
    """Invoke a hosted child pipeline and nest it under this run."""
    run = start_run(payload, agent_slug="orchestrator")
    try:
        with SomiaClient.from_env() as client:
            with node_span("call_child", inputs={"payload": payload}):
                child = client.sessions.run(
                    child_agent_id,
                    input_data=payload,
                    caller_agent_slug="orchestrator",
                )
                link_child_pipeline_run(
                    child.session_id,
                    pipeline_id=child_pipeline_id or child_agent_id,
                )
                result = {"child_message": child.message}
        run.submit_success(output=result)
        return result
    except Exception as exc:
        run.submit_failure(exc)
        raise


def link_external_child(child_log_run_result: dict) -> None:
    """Call inside an active parent span after an external child's log_run."""
    run_id = child_log_run_result.get("run_id")
    if run_id:
        link_child_pipeline_run(run_id)


if __name__ == "__main__":
    print("Template only — wire child_agent_id from the target repo.")
