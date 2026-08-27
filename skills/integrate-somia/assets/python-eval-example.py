"""Local evaluation with client.eval (external agent).

Requires dataset_id and profile_id from the Somia dashboard (or env).
agent_fn must be sync and return JSON-serializable output.
"""

from __future__ import annotations

import os

from somia import SomiaClient


def build_agent_fn(invoke_agent):
    """Adapt the project's public entrypoint to Somia's sync agent_fn contract."""

    def agent_fn(input_data):
        return invoke_agent(input_data)

    return agent_fn


def run_local_eval(*, invoke_agent) -> None:
    dataset_id = os.environ["SOMIA_DATASET_ID"]
    profile_id = os.environ["SOMIA_PROFILE_ID"]
    agent_slug = os.environ["SOMIA_AGENT_SLUG"]

    with SomiaClient(
        base_url=os.getenv(
            "SOMIA_BASE_URL", "https://platform.somiasolutions.com/api"
        ),
        api_key=os.environ["SOMIA_API_KEY"],
    ) as client:
        eval_result = client.eval(
            agent_fn=build_agent_fn(invoke_agent),
            dataset_id=dataset_id,
            profile_id=profile_id,
            agent_id=agent_slug,  # forwarded as agent_slug on the wire
            agent_version=os.getenv("SOMIA_AGENT_VERSION", "local"),
        )
        eval_result.wait(timeout=float(os.getenv("SOMIA_EVAL_TIMEOUT", "600")))
        print(
            eval_result.status,
            eval_result.overall_score,
            f"{eval_result.processed_examples}/{eval_result.total_examples}",
        )


if __name__ == "__main__":

    def invoke_agent(input_data):
        return {"text": f"Echo: {input_data}"}

    run_local_eval(invoke_agent=invoke_agent)
