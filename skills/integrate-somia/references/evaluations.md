# Somia evaluations

Use `client.eval(...)` to score an agent. Read `references/sdk-api.md` for the
exact signature.

Somia’s loop is: monitor → debug from traces → build/promote a validation set →
eval after changes. This file covers the **eval** step. For how monitoring I/O
should be shaped so it can become validation examples later, see
`references/monitoring.md` → "Eval-eligible I/O and debug-useful traces".

## Prerequisites (do not invent)

Local and server evals need IDs that already exist in Somia:

- `profile_id` — eval profile UUID (dashboard or `SOMIA_PROFILE_ID`)
- `dataset_id` / `set_ids` — validation set / dataset UUID(s)

**Default:** take IDs from the user or env. Do **not** create validation sets,
criteria, or eval profiles as part of a normal integration unless the user
explicitly asks to manage those resources via the API.

## Contract with monitoring

Local eval’s `agent_fn(input_data)` should accept the **same semantic shape** as
monitored run `input`. Scorable agent results should match monitored run
`output`.

| If … | Then … |
| --- | --- |
| Monitoring was integrated first | Reuse that input/output contract for `agent_fn` and dataset examples |
| Eval is requested first | Prefer the dataset’s `input_data` shape; if also adding monitoring, log that same contract |
| Shapes disagree | Ask the user which boundary is canonical before rewriting |

Traces are for **debugging and improving** the agent between evals — not a
substitute for dataset `expected_output`.

## Two modes

| Mode | When | Key args |
| --- | --- | --- |
| Local | External agent runs in this process | `agent_fn=...`, `dataset_id=...`, `agent_id="slug"` |
| Server | Agent is a hosted Somia pipeline | no `agent_fn`, `agent_id=123`, `set_ids=[...]` |

Ambiguous / incomplete args raise `ValueError`. Requesting server eval for an
external-only agent returns HTTP 400 — switch to local mode with `agent_fn`.

## Local eval (typical for client agents)

1. Reuse the project's public invoke function; do not rewrite the agent solely
   for evals.
2. `agent_fn(input_data) -> JSON-serializable output` must be **sync**.
3. If the agent is async, wrap it (e.g. `asyncio.run` / shared loop) inside
   `agent_fn`.
4. Handle exceptions inside `agent_fn` when you want structured error outputs;
   uncaught exceptions are recorded as failed examples by the local thread pool.
5. Pass external slug as `agent_id="my-agent"` (forwarded as `agent_slug`).
6. Set `agent_version` to distinguish candidates (branch, commit, prompt rev).
7. Call `eval_result.wait(timeout=...)`.
8. Optionally pass `max_workers` to cap local `agent_fn` concurrency (default 4).
   It is not a platform setting — omit unless tuning local load / rate limits.

```python
def agent_fn(input_data):
    return invoke_agent(input_data)  # existing project entrypoint

eval_result = client.eval(
    agent_fn=agent_fn,
    dataset_id=os.environ["SOMIA_DATASET_ID"],
    profile_id=os.environ["SOMIA_PROFILE_ID"],
    agent_id=os.environ["SOMIA_AGENT_SLUG"],
    agent_version=os.getenv("SOMIA_AGENT_VERSION", "local"),
)
eval_result.wait(timeout=600)
```

Template: `assets/python-eval-example.py`.

## Server eval (hosted pipelines only)

```python
eval_result = client.eval(
    agent_id=123,  # numeric pipeline id
    profile_id=os.environ["SOMIA_PROFILE_ID"],
    set_ids=[os.environ["SOMIA_DATASET_ID"]],
)
eval_result.wait(timeout=600)
```

## Relationship to monitoring

- Running an eval does **not** require changing observability wiring.
- Do not add `log_run` / callback instrumentation solely because the user asked
  for an eval, unless they also asked for monitoring.
- Local eval submits run outputs for scoring; it is not a substitute for
  production `log_run` monitoring.
- When both exist, keep **one shared input/output contract** so production runs
  remain promotable into the validation set you eval against.

## CI notes

- Store `SOMIA_API_KEY`, dataset, and profile IDs as CI secrets / variables.
- Prefer a pinned `somia` version.
- For local eval, lower `max_workers` if your agent hits upstream rate limits
  (client-side concurrency only — unrelated to platform workers).
- Fail the job on `eval_result.status == "failed"` or a minimum score threshold
  the user defines — do not invent business thresholds.
