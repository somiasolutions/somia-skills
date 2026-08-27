# Somia SDK API reference

Documented against SDK version **0.1.0a3** (`pip install somia --pre`).
If the installed package differs, prefer `inspect.signature(...)` on the
installed symbols over this file.

**Rule:** Never invent imports, parameters, or method names.

## Package and imports

```python
from somia import (
    SomiaClient,
    SomiaTrace,
    Span,
    start_run,
    node_span,
    llm_span,
    tool_span,
    clip_text,
)
from somia.integrations import SomiaCallbackHandler  # requires somia[langgraph]
```

Optional extras:

```bash
pip install somia --pre
pip install "somia[langgraph]"   # langchain-core for SomiaCallbackHandler
```

Requires Python `>=3.11`.

## Identifiers

| Name | Shape | APIs |
| --- | --- | --- |
| `agent_slug` | `str` | `log_run`, `SomiaCallbackHandler`, local eval (wire) |
| `agent_id` | `int` (pipeline) or `str` (slug for local eval arg) | `sessions.*`, `client.eval` |

## `SomiaClient`

```python
SomiaClient(
    *,
    base_url: str,
    api_key: str,
    timeout: float = 60.0,
    retries: int = 2,
    retry_backoff_seconds: float = 0.5,
)
```

Context manager supported: `with SomiaClient(...) as client:`.

```python
SomiaClient.from_env(
    *,
    api_key: str | None = None,       # else SOMIA_API_KEY
    base_url: str | None = None,      # else SOMIA_BASE_URL or platform default
    timeout: float = 60.0,
    retries: int = 2,
    retry_backoff_seconds: float = 0.5,
)
```

Raises `RuntimeError` if no API key is available.

Call `client.close()` when not using a context manager.

### `client.log_run` — external agent monitoring

```python
client.log_run(
    *,
    agent_slug: str,
    input: Any = None,               # prefer JSON-serializable dict
    output: Any = None,              # prefer JSON-serializable dict
    trace: dict | None = None,       # ALWAYS SomiaTrace(...).to_dict() — never the object
    agent_version: str | None = None,
    status: str = "SUCCESS",         # "SUCCESS" | "FAILED"  (run-level only)
    latency_ms: float | None = None,
    tokens: dict | None = None,      # see token shapes below
    tags: list[str] | None = None,   # user-defined tags (filterable)
    environment: str | None = None,  # e.g. dev/staging/prod
    end_user_id: str | None = None,  # your own end-user identifier
    occurred_at: str | datetime | None = None,  # event time (ISO-8601)
    metadata: dict | None = None,    # arbitrary key/value properties
    session_id: str | None = None,   # conversation/session key (group turns)
    idempotency_key: str | None = None,
) -> dict  # run_id, trace_id, pipeline_id, agent_slug, created_at
```

Wire: `POST /v1/external/runs`.

Return keys used by follow-up feedback / backfill scripts:

| Key | Use |
| --- | --- |
| `run_id` | Dashboard / idempotent bookkeeping |
| `trace_id` | Required for `client.traces.feedback.create(...)` |

On an idempotent replay (same `idempotency_key`), `trace_id` may be absent —
do not create feedback again in that case. See `references/historical-upload.md`.

Session semantics:

- Use `session_id` to group multiple turns/traces under one conversation run.
- If omitted, each `log_run` is treated as a new run boundary.
- Keep `idempotency_key` unique per turn/retry event; do not reuse it across
  different turns.

There is **no** context-manager or decorator wrapper for runs. Build a
`SomiaTrace`, run the agent, then call `log_run` with `trace=trace.to_dict()`.

#### Run payload vs trace (two layers)

| Layer | Fields | Purpose |
| --- | --- | --- |
| Run record | `input`, `output`, `status`, `latency_ms`, `tokens`, `metadata` | What the dashboard shows for the run |
| Trace tree | `trace` (`sdk-1.0` dict) | Span graph, nodes, LLM/tool detail |

Hard rules:

1. Always set top-level `input` / `output` when you care about the run card.
   Putting I/O only inside spans is not enough for the run record.
2. Prefer **dicts**. Non-dicts are stored as `{"value": <payload>}` server-side.
3. Values must be **JSON-serializable** (dump Pydantic / LangChain objects first).
4. `trace=` must be a **dict** from `SomiaTrace.to_dict()`, never a `SomiaTrace`
   instance.
5. Status vocabularies differ (do not mix):
   - `log_run(status=...)` → `"SUCCESS"` | `"FAILED"`
   - `trace.finish(status=...)` / span `status` → `"OK"` | `"ERROR"`

#### Token shapes (do not mix)

```text
# Top-level log_run(tokens=...)
{"prompt": 10, "completion": 5, "total": 15}

# Inside span.attributes["usage"] (Span.set_usage)
{"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
```

### `client.eval` — evaluation

```python
client.eval(
    *,
    agent_id: str | int,
    profile_id: str,
    agent_fn: Callable[[Any], Any] | None = None,  # sync only
    dataset_id: str | None = None,
    set_ids: list[str] | None = None,
    agent_version: str | None = None,
    pipeline_version_id: int | None = None,
    max_workers: int | None = None,  # local eval only; default 4
) -> EvalRunResult
```

| Mode | Required | Behavior |
| --- | --- | --- |
| Local (external agent) | `agent_fn`, `dataset_id`, `agent_id` as slug string | Runs `agent_fn` in-process; submits outputs |
| Server (hosted pipeline) | no `agent_fn`; `set_ids` or `dataset_id`; `agent_id` as pipeline id | Platform executes the pipeline |

`max_workers` is optional and **local-only**: it caps in-process `ThreadPoolExecutor`
concurrency when calling `agent_fn`. It is never sent to the platform. Omit it
unless you need to tune local load / rate limits. Passing it on a server eval
raises `ValueError`.

```python
result = client.eval(...)
result.wait(timeout=600.0, poll_interval=3.0)
# result.status, overall_score, processed_examples, failed_examples, results, ...
```

`agent_fn` must be a **sync** `Callable[[Any], Any]` returning JSON-serializable
output. Wrap async agents yourself.

### Hosted sessions (optional mode)

```python
client.sessions.create_session(agent_id: int, *, input_data=None, stream=False,
    pipeline_version="production", trace_enabled=False, test=False,
    tags=None, environment=None, end_user_id=None, metadata=None)
client.sessions.interact_session(agent_id: int, session_id: str, *, ...)
client.sessions.run(agent_id: int, *, session_id=None, ...)  # create or continue
```

`agent_id` here is a **numeric** internal pipeline id. Not for external monitoring.

Streaming returns an iterator of `StreamEvent` when `stream=True`.

### `client.traces.feedback` — feedback on a trace

Use after `log_run` (or for an existing `trace_id`). Full playbook:
`references/feedback.md`. Historical / batch: `references/historical-upload.md`.

```python
from somia import Feedback  # optional; methods return Feedback models

client.traces.feedback.create(
    trace_id: str,
    *,
    feedback: str,
    ground_truth: str | None = None,
    status: str | None = "PENDING",   # "PENDING" | "DRAFT" | "APPROVED"
) -> Feedback

client.traces.feedback.update(
    feedback_id: str,
    *,
    feedback=...,           # optional
    ground_truth=...,       # optional
    status=...,             # optional
    score=...,              # optional int — set scores HERE, not on create
    score_type=...,         # "boolean" | "score_1_5"
) -> Feedback

client.traces.feedback.get(feedback_id: str) -> Feedback
client.traces.feedback.list(trace_id: str, *, page: int = 1, per_page: int = 50)
client.traces.feedback.delete(feedback_id: str) -> None
```

Score contract:

| `score_type` | Allowed `score` |
| --- | --- |
| `boolean` | `0` or `1` (int, not bool) |
| `score_1_5` | `1` … `5` |

`create` accepts only `feedback` / `ground_truth` / `status`. Always `update`
to attach scores.

Related (when the user asks): `client.traces.get`, `client.traces.review`,
`client.traces.update_labels`, `client.traces.list`, `client.traces.delete`.

### Other client attributes (out of default integrate)

`validation_sets`, `criteria`, `eval_profiles`, `knowledge_bases`, `documents`,
`workspaces`, and `pipelines` exist on `SomiaClient` but are **not** part of the
default monitoring integration. Use them only when the user explicitly asks to
manage those platform resources via the API.

`client.traces.feedback` **is** in scope when the user asks for feedback or
historical upload.

## `start_run` / typed spans

Preferred manual monitoring path (no `langchain-core`). Fail-open. Nested
`start_run` does not submit a second root run.

```python
from somia import start_run, node_span, llm_span, tool_span, clip_text

run = start_run(
    input,
    *,
    client: SomiaClient | None = None,          # else SomiaClient.from_env()
    agent_slug: str | None = None,              # else SOMIA_AGENT_SLUG / SOMIA_AGENT_ID
    agent_version: str | None = None,           # else SOMIA_AGENT_VERSION
    input_mapper: Callable[[Any], Any] | None = None,
    output_mapper: Callable[[Any], Any] | None = None,
    end_user_id: str | None = None,
    session_id: str | None = None,
    tags: list[str] | None = None,
    metadata: dict | None = None,
    root_span_name: str = "agent",
    environment: str | None = None,             # else SOMIA_ENVIRONMENT
)

run.submit_success(output=None, *, tokens: dict | None = None) -> None
run.submit_failure(error, output=None, *, tokens: dict | None = None) -> None
run.discard() -> None   # close without log_run

with node_span(name: str, *, inputs: dict | None = None) as span:
    ...
with llm_span(
    name: str | None = None,
    *,
    provider: str | None = None,
    model: str | None = None,
    parameters: dict | None = None,
    inputs: dict | None = None,
) as span:
    ...
with tool_span(name: str, *, inputs: dict | None = None) as span:
    ...

clip_text(text, limit: int = 2000)  # truncate strings for payloads
```

Honors `SOMIA_MONITORING_ENABLED` (default on). Span helpers no-op when no run
is active. `node_span` sets `node_id`. Exceptions inside a span mark it `ERROR`.
Call `span.finish(outputs=...)` when you want outputs; otherwise the span
auto-finishes.

Do **not** also attach `SomiaCallbackHandler` on the same execution path.

## `SomiaTrace` / `Span`

### Lifecycle

```python
trace = SomiaTrace().start()
with trace.span(name="agent", kind="agent", inputs={"q": "hello"}) as span:
    span.finish(outputs={"answer": "hi"})
    # raised inside `with`: span is marked ERROR automatically
trace.finish(status="OK")  # or "ERROR"
payload = trace.to_dict()  # MUST pass this dict to log_run(trace=...)
```

### `to_dict()` shape (`sdk-1.0`)

```text
{
  "version": "sdk-1.0",
  "trace_id": "<uuid>",
  "started_at_iso": "<iso8601>",
  "finished_at_iso": "<iso8601>",
  "status": "OK" | "ERROR",
  "spans": [ { span... }, ... ]
}
```

Each span:

```text
{
  "span_id": "<uuid>",
  "parent_span_id": "<uuid>" | null,   # null = root candidate
  "kind": "agent" | "node" | "llm" | "tool" | "internal",
  "name": "<string>",
  "started_at_iso": "<iso8601>",
  "finished_at_iso": "<iso8601>",
  "status": "OK" | "ERROR",
  "inputs": <json> | omitted,
  "outputs": <json> | omitted,
  "attributes": { ... },
  "error": "<string>" | omitted
}
```

An empty `spans` list yields a near-empty converted trace on the server. Always
include at least one finished root span for useful UI, or accept run-only I/O.

### Span kinds

| Kind | Role | Notes |
| --- | --- | --- |
| `agent` | Root of a manual run | Prefer exactly one parentless `kind="agent"` mirroring top-level I/O |
| `node` | Graph step | **Requires** `span.set_node_id("...")`. Without `node_id`, converter drops it |
| `llm` | Model call | Use `set_llm_metadata(provider=..., model=..., parameters=...)` and `set_usage(...)` |
| `tool` | Tool call | Name = tool name; parent should be the node/agent that invoked it |
| `internal` | Framework noise | Often filtered unless it is the root |

Helpers: `set_node_id`, `set_llm_metadata`, `set_usage`, `set_error`, `finish`.

Children must set `parent_span_id` to the parent span's `span_id` (use nested
`trace.span(..., parent_span_id=parent.span_id)`).

## `SomiaCallbackHandler`

```python
from somia.integrations import SomiaCallbackHandler

SomiaCallbackHandler(
    *,
    client: SomiaClient,
    agent_slug: str,
    agent_version: str | None = None,
    metadata: dict | None = None,
    tags: list[str] | None = None,
    environment: str | None = None,
    end_user_id: str | None = None,
    occurred_at: str | datetime | None = None,
    session_id: str | None = None,
    session_id_mapper: Callable[[dict], str | None] | None = None,
    ignore_nodes: Sequence[str] | None = None,
    root_input_mapper: Callable[[Any], Any] | None = None,
    root_output_mapper: Callable[[Any], Any] | None = None,
    debug: bool = False,
)
```

- Requires `pip install "somia[langgraph]"`.
- `raise_error = False` — monitoring failures do not fail the agent.
- On root chain end/error, submits via `client.log_run` on a background thread.
- `ignore_nodes` filters out specific node names (for example, framework middleware
  like `ModelCallLimitMiddleware`) from trace spans.
- **Do not** also call `log_run` for the same graph invocation.
- Holds mutable per-run state; prefer a fresh handler per concurrent invoke when
  runs may overlap.
- Session grouping options:
  - `session_id`: force one conversation id for every handler submission.
  - `session_id_mapper`: derive session id from callback context (metadata/kwargs).
  - If both are omitted, handler falls back to metadata keys such as
    `session_id` / `thread_id` / `conversation_id` when available.

Pass via LangGraph/LangChain config (always **merge** existing callbacks):

```python
config = {**(config or {}), "callbacks": [*(config or {}).get("callbacks") or [], handler]}
graph.invoke(inputs, config=config)
```

## Errors

Catch from `somia`:

- `BadRequestError`, `AuthError`, `PermissionDeniedError`, `NotFoundError`
- `RateLimitError`, `ServiceUnavailableError`, `ServerError`
- `TransportError`, `StreamParseError`
- Base: `SomiaError`, `ApiError`

## Environment variables

| Variable | Required | Default / notes |
| --- | --- | --- |
| `SOMIA_API_KEY` | yes | — |
| `SOMIA_BASE_URL` | no | `https://platform.somiasolutions.com/api` |
| `SOMIA_AGENT_SLUG` | for monitoring | preferred external slug |
| `SOMIA_AGENT_ID` | legacy | alias for slug in some projects |
| `SOMIA_AGENT_VERSION` | no | version string |
| `SOMIA_MONITORING_ENABLED` | no | `"true"` / `"false"` |
| `SOMIA_DATASET_ID` | for local eval | UUID from dashboard |
| `SOMIA_PROFILE_ID` | for eval | UUID from dashboard |
