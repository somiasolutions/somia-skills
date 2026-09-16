"""Local evaluation with client.eval (external agent).

Requires profile_id from the Somia dashboard (or env). Local mode also needs
dataset_id. agent_fn must be sync and return JSON-serializable output.

Optional: mapping_input / input_fields remap dataset examples onto agent_fn
fields (SDK-side only). Ad-hoc runs= submits already-produced rows.
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
            eval_result.mapping_coverage,
        )


def run_local_eval_with_mapping(*, invoke_agent) -> None:
    """Use when dataset keys differ from agent_fn fields."""
    with SomiaClient.from_env() as client:
        eval_result = client.eval(
            agent_fn=build_agent_fn(invoke_agent),
            dataset_id=os.environ["SOMIA_DATASET_ID"],
            profile_id=os.environ["SOMIA_PROFILE_ID"],
            agent_id=os.environ["SOMIA_AGENT_SLUG"],
            input_fields=[
                {"name": "question", "type": "string", "required": True},
                {"name": "locale", "type": "string", "required": False},
            ],
            mapping_input={
                "question": "q",
                "locale": {"constant": "en-US"},
            },
            force=True,
        )
        eval_result.wait(timeout=float(os.getenv("SOMIA_EVAL_TIMEOUT", "600")))
        print(eval_result.status, eval_result.mapping_coverage)


def run_adhoc_eval(*, runs: list[dict]) -> None:
    """Score already-produced {input, output} rows. No agent_fn."""
    with SomiaClient.from_env() as client:
        eval_result = client.eval(
            agent_id=os.environ["SOMIA_AGENT_SLUG"],
            profile_id=os.environ["SOMIA_PROFILE_ID"],
            runs=runs,
        )
        eval_result.wait(timeout=float(os.getenv("SOMIA_EVAL_TIMEOUT", "600")))
        print(eval_result.status, eval_result.overall_score)


if __name__ == "__main__":

    def invoke_agent(input_data):
        return {"text": f"Echo: {input_data}"}

    run_local_eval(invoke_agent=invoke_agent)
