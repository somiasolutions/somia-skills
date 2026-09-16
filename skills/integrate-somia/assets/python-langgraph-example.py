"""LangGraph monitoring with SomiaCallbackHandler.

Requires: pip install "somia[langgraph]" --pre

Always merge callbacks into existing config — never replace the whole config.
"""

from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from typing import Any, Iterator

from somia import SomiaClient

logger = logging.getLogger(__name__)


def _truthy(value: str | None, default: str = "true") -> bool:
    return (value if value is not None else default).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def merge_callbacks(config: dict | None, handlers: list[Any]) -> dict:
    base = dict(config or {})
    existing = list(base.get("callbacks") or [])
    base["callbacks"] = [*existing, *handlers]
    return base


@contextmanager
def somia_langgraph_callbacks(
    *,
    agent_slug: str | None = None,
    session_id: str | None = None,
) -> Iterator[list[Any]]:
    """Yield a list of Somia handlers (possibly empty) — fail-open."""
    if not _truthy(os.getenv("SOMIA_MONITORING_ENABLED")):
        yield []
        return

    resolved_slug = (
        agent_slug
        or os.getenv("SOMIA_AGENT_SLUG")
        or os.getenv("SOMIA_AGENT_ID")  # legacy alias
    )
    api_key = os.getenv("SOMIA_API_KEY")
    if not resolved_slug or not api_key:
        logger.warning(
            "Somia monitoring skipped: missing SOMIA_AGENT_SLUG/SOMIA_AGENT_ID or SOMIA_API_KEY"
        )
        yield []
        return

    try:
        from somia.integrations import SomiaCallbackHandler
    except ImportError:
        logger.warning(
            'Somia callback unavailable. Install with: pip install "somia[langgraph]"'
        )
        yield []
        return

    client = SomiaClient(
        base_url=os.getenv(
            "SOMIA_BASE_URL", "https://platform.somiasolutions.com/api"
        ),
        api_key=api_key,
    )
    try:
        handler = SomiaCallbackHandler(
            client=client,
            agent_slug=resolved_slug,
            agent_version=os.getenv("SOMIA_AGENT_VERSION"),
            tags=["langgraph"],
            environment=os.getenv("SOMIA_ENVIRONMENT"),
            end_user_id=os.getenv("SOMIA_END_USER_ID"),
            # For multiturn conversations, pass a stable session id.
            session_id=session_id,
            # Or derive from callback context, e.g. thread_id in metadata/configurable.
            # session_id_mapper=lambda ctx: (ctx.get("metadata") or {}).get("thread_id"),
            # Prefer eval-eligible I/O (replayable input, scorable output) — not full state.
            # If keys / trace depth are non-obvious, ask (or propose + confirm) first.
            # root_input_mapper=lambda payload: payload.get("query", payload) if isinstance(payload, dict) else payload,
            # root_output_mapper=lambda payload: payload.get("final_answer", payload) if isinstance(payload, dict) else payload,
        )
        yield [handler]
    except Exception:
        logger.exception(
            "Failed to init SomiaCallbackHandler; continuing without monitoring"
        )
        yield []
    finally:
        client.close()


def invoke_with_somia(
    graph: Any, inputs: Any, config: dict | None = None
) -> Any:
    with somia_langgraph_callbacks() as handlers:
        return graph.invoke(inputs, config=merge_callbacks(config, handlers))
