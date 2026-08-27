"""Manual monitoring with start_run + typed spans.

Use for non-LangGraph agents, or LangGraph graphs that call custom LLMs/tools
(not LangChain callbacks). Keep Somia failures fail-open.

Contract (start_run implements this):
- One user-visible execution → one log_run.
- Top-level input/output on the run card AND mirrored on the root span.
- Prefer eval-eligible input/output (replayable as validation examples / agent_fn)
  and debug-useful spans (what/how). Ask if that mapping is non-obvious.
- log_run status: SUCCESS|FAILED; trace/span status: OK|ERROR.
- Prefer JSON-serializable dicts for input/output.
"""

from __future__ import annotations

import os
from typing import Any, Callable

from somia import llm_span, node_span, start_run, tool_span


def run_agent_with_somia(
    *,
    user_input: Any,
    invoke_agent: Callable[[Any], Any],
    agent_slug: str | None = None,
    agent_version: str | None = None,
    metadata: dict | None = None,
) -> Any:
    """Invoke ``invoke_agent(user_input)`` and log one Somia root run."""
    run = start_run(
        user_input,
        agent_slug=agent_slug,
        agent_version=agent_version,
        metadata=metadata,
    )
    try:
        with node_span("agent"):
            result = invoke_agent(user_input)
        run.submit_success(output=result)
        return result
    except Exception as exc:
        run.submit_failure(exc)
        raise


def example() -> None:
    def invoke_agent(payload: Any) -> dict:
        with tool_span("echo", inputs={"payload": payload}) as span:
            answer = f"echo: {payload}"
            span.finish(outputs={"answer": answer})
        with llm_span(provider="example", model="echo") as span:
            span.set_usage(prompt_tokens=1, completion_tokens=1)
            span.finish(outputs={"text": answer})
        return {"answer": answer}

    out = run_agent_with_somia(
        user_input={"question": "hello"},
        invoke_agent=invoke_agent,
        agent_slug=os.environ.get("SOMIA_AGENT_SLUG"),
        agent_version=os.getenv("SOMIA_AGENT_VERSION"),
        metadata={"environment": os.getenv("ENV", "dev")},
    )
    print(out)


if __name__ == "__main__":
    example()
