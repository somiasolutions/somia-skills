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

Ad-hoc eval (`runs=`) still needs `profile_id`; `dataset_id` is optional.

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
| Shapes disagree | Ask which boundary is canonical, **or** keep `agent_fn` as-is and pass `mapping_input` / `input_fields` |

Traces are for **debugging and improving** the agent between evals — not a
substitute for dataset `expected_output`. Dataset `input_data` /
`expected_output` may be strings or structured JSON (dicts).

## Three modes

| Mode | When | Key args |
| --- | --- | --- |
| Local | External agent runs in this process | `agent_fn=...`, `dataset_id=...`, `agent_id="slug"`; optional mapping |
| Ad-hoc | Already-produced `{input, output}` rows | `runs=[...]`, no `agent_fn`; `dataset_id` optional |
| Server | Agent is a hosted Somia pipeline | no `agent_fn` / no `runs`, `agent_id=123`, `set_ids=[...]` |

Ambiguous / incomplete args raise `ValueError`. Requesting server eval for an
external-only agent returns HTTP 400 — switch to local mode with `agent_fn`.

Do **not** combine `runs` with `agent_fn` or `set_ids`. Mapping args
(`mapping_input`, `input_fields`) and `max_workers` are local-only.

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
9. If dataset keys differ from `agent_fn` fields, pass `mapping_input` /
   `input_fields` (below). Do not silently reshape `agent_fn`.

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

## SDK-side input mapping (local only)

`mapping_input` remaps each dataset example onto the fields `agent_fn` expects.
This is **SDK-side only** — platform saved mappings are not applied on
`/v1/external/eval/submit`.

Pass-through: if neither `input_fields` nor `mapping_input` is given, each
example’s `input_data` is handed to `agent_fn` unchanged.

```python
eval_result = client.eval(
    agent_fn=agent_fn,
    dataset_id=os.environ["SOMIA_DATASET_ID"],
    profile_id=os.environ["SOMIA_PROFILE_ID"],
    agent_id=os.environ["SOMIA_AGENT_SLUG"],
    input_fields=[
        {"name": "question", "type": "string", "required": True},
        {"name": "locale", "type": "string", "required": False},
    ],
    mapping_input={
        "question": "q",                   # shorthand: pull from set field "q"
        "locale": {"constant": "en-US"},   # fixed value, not from the set
    },
    force=True,  # default: skip unresolved required fields
)
print(eval_result.mapping_coverage)
# {"total": N, "resolvable": M, "unresolved_fields": [...]}
```

Mapping entries:

| Shape | Meaning |
| --- | --- |
| `"question": "q"` | Pull agent field `question` from dataset field `q` |
| `"locale": {"constant": "en-US"}` | Constant, not from the set |
| `"question": {"set_field": "q"}` | Explicit set-field form of the shorthand |

When `input_fields` is set and a field is omitted from `mapping_input`, the SDK
auto-matches by name against the example’s keys.

Resolution rules:

- Unresolved **required** fields skip that example when `force=True` (default).
- Unresolved **optional** fields are omitted from the payload (never a failure).
- `force=False` raises `ValueError` if any required field is unresolved.
- If `mapping_coverage.resolvable == 0`, nothing is POSTed (the API rejects an
  empty `runs` list) and `wait()` returns immediately with `status="finished"`.
  Always print `mapping_coverage`.

Ask (or propose one default and confirm) before inventing a mapping when dataset
keys vs `agent_fn` keys are unclear — same style as monitoring I/O.

Optionally persist the same fields on an **external** pipeline version when the
user asks:

```python
client.pipelines.versions.create(
    pipeline_id,
    version="v1.1.3",
    input_fields=[
        {"name": "question", "type": "string", "required": True},
        {"name": "locale", "type": "string", "required": False},
    ],
)
```

Do not set `input_fields` on internal pipelines (derived from the Begin node;
the platform rejects it).

## Ad-hoc eval (already-produced runs)

Use when the user already has `{input, output}` rows (a batch, a notebook, a
CI artifact) and does not want the SDK to call `agent_fn`.

```python
eval_result = client.eval(
    agent_id=os.environ["SOMIA_AGENT_SLUG"],
    profile_id=os.environ["SOMIA_PROFILE_ID"],
    runs=[
        {"input": {"question": "hello"}, "output": {"answer": "hi"}},
        {"input": {"question": "bye"}, "output": {"answer": "goodbye"}},
    ],
    # dataset_id=...  # optional
)
eval_result.wait(timeout=600)
```

`runs` must be a non-empty list. Each row is submitted as-is to
`POST /v1/external/eval/submit`. Mapping is not applied.

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
  remain promotable into the validation set you eval against. Use mapping when
  the dataset shape differs from that contract — do not fork `agent_fn`.

## CI notes

- Store `SOMIA_API_KEY`, dataset, and profile IDs as CI secrets / variables.
- Prefer a pinned `somia` version.
- For local eval, lower `max_workers` if your agent hits upstream rate limits
  (client-side concurrency only — unrelated to platform workers).
- Fail the job on `eval_result.status == "failed"` or a minimum score threshold
  the user defines — do not invent business thresholds.
- Inspect `mapping_coverage` in CI logs when mapping is used; treat
  `resolvable == 0` as a mapping failure, not a successful empty eval.
