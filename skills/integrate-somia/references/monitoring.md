# Somia monitoring

One user-visible agent execution must produce **one Somia root run**.

| Stack | Use | Do not use on the same path |
| --- | --- | --- |
| LangGraph / LangChain callbacks | `SomiaCallbackHandler` | manual `log_run` |
| Everything else | `start_run` + `node_span` / `llm_span` / `tool_span` | `SomiaCallbackHandler` |

Always read `references/sdk-api.md` for exact signatures.

---

## Eval-eligible I/O and debug-useful traces

Monitoring feeds the Somia loop: **debug from traces**, then **promote run
input/output into validation examples**, then **eval** after changes. Shape
logged data for that future — even when you are only wiring monitoring today.

| Field | Job | Prefer | Avoid |
| --- | --- | --- | --- |
| Run `input` | Future validation `input_data` / `agent_fn` argument | Stable task payload at the public invoke boundary | Full graph/app state, auth, HTTP scaffolding |
| Run `output` | Scorable result / future `expected_output` | Final user-visible or task artifact | Whole state, tool dumps, scratchpads |
| Trace spans | Explain *what* and *how* to improve the agent | Meaningful nodes / LLM / tools with curated payloads | Megabyte intermediates, secrets, duplicate root-only noise |

Semantic fit matters more than wire type: use the same **shape** you would later
put in a validation example and pass to `agent_fn` (see
`references/evaluations.md`).

### Design tests (apply before coding)

1. **Replay:** Could this `input` be fed back into the same agent entrypoint as a
   dataset example?
2. **Judge:** Is this `output` what you would score or set as expected output?
3. **Diagnose:** Do spans show the steps that matter for debugging (e.g. retrieve
   → reason → tools), without drowning in noise?

### When to proceed without asking

- Clear `str` or small dict like `{"question": "..."}` → `{"answer": "..."}`
- A single `invoke(user_message) -> reply` boundary
- The user already named the fields to log / evaluate on

### When to ask (or propose + confirm)

Ask before wiring if any of these apply:

- Large LangGraph / app **state dicts** with many keys
- Unclear which field is the **replayable task input** vs scaffolding
- Unclear which field is the **scorable final result** vs intermediate state
- Multiple plausible outputs (message, structured result, tool dump)
- Multi-step agent where trace depth is unclear (root-only vs key steps)
- Middle steps could log **huge or sensitive** data (full retrieval corpus,
  raw tool payloads, auth context)

Keep the question short. Prefer **one proposed default**, then confirm:

> For validation later I'd treat `state["company_url"]` as input and
> `state["company_profile"]` as output, and put retrieval + LLM steps in the
> trace (doc ids, not full pages). Does that match how you'd evaluate this agent?

If the user is unsure, default to:

1. **Input** = primary user/task payload at the public invoke boundary.
2. **Output** = primary final answer / artifact.
3. **Trace** = meaningful steps only when the agent is multi-step; prefer ids /
   summaries over raw corpora. Root-only is OK for trivial single-step agents.
4. Never log secrets, tokens, or unnecessary PII
   (`references/privacy-and-security.md`).

### Anti-patterns

- Dumping full application / graph state "just in case"
- Making run `output` the entire state dict
- Logging only root I/O when the agent has multi-step behavior worth debugging
  and the user cares about improvement (propose at least key node/llm/tool spans)
- Inventing a rigid universal schema (e.g. always `query`/`answer`) — use the
  three design tests and ask when unclear

### How to implement

| Path | Mechanism |
| --- | --- |
| LangGraph | `root_input_mapper` / `root_output_mapper` on `SomiaCallbackHandler` |
| Manual `start_run` | `input_mapper` / `output_mapper` on `start_run`; span `finish(outputs=...)` |

Example mappers:

```python
SomiaCallbackHandler(
    client=client,
    agent_slug=agent_slug,
    root_input_mapper=lambda s: s.get("query", s) if isinstance(s, dict) else s,
    root_output_mapper=lambda s: s.get("final_answer", s) if isinstance(s, dict) else s,
)
```

Manual equivalent:

```python
run = start_run(
    state,
    input_mapper=lambda s: s.get("query", s) if isinstance(s, dict) else s,
    output_mapper=lambda s: s.get("final_answer", s) if isinstance(s, dict) else s,
)
result = invoke_agent(state)
run.submit_success(output=result)
```

Report the chosen mapping (and that it is eval-eligible / debug-useful) in the
final integration summary.

---

## A) LangGraph / LangChain — `SomiaCallbackHandler`

### When

The agent is invoked via `graph.invoke` / `ainvoke` / `stream` / `astream` (or
another runner that accepts LangChain `callbacks` in config).

### Install

```bash
pip install "somia[langgraph]" --pre
```

### Wire-up rules

1. Build `SomiaClient` from env (see `references/setup.md`).
2. Construct `SomiaCallbackHandler(client=..., agent_slug=..., ...)`.
   - Use `ignore_nodes=[...]` to drop known framework-noise nodes from trace
     analysis (for example `ModelCallLimitMiddleware`).
3. **Merge** into existing config — never replace the whole `config` dict.
4. Keep fail-open: missing env / import errors → log warning, run without Somia.
5. Do **not** also call `client.log_run` for that same invocation (the handler
   already submits on root chain end/error via a background thread).
6. Handler state is mutable. For concurrent overlapping runs, create a handler
   per invoke (or otherwise isolate state). Reusing one handler for strictly
   sequential invokes is fine.
7. For multiturn grouping, set `session_id` (or `session_id_mapper`) on the
   handler so repeated invokes append traces to the same conversation run.

### Merge pattern (required)

```python
def with_somia_callbacks(config: dict | None, handler) -> dict:
    base = dict(config or {})
    existing = list(base.get("callbacks") or [])
    base["callbacks"] = [*existing, handler]
    return base

result = graph.invoke(inputs, config=with_somia_callbacks(config, handler))
```

Wrong (drops `thread_id`, checkpointing, other callbacks):

```python
graph.invoke(inputs, config={"callbacks": [handler]})  # DO NOT
```

### Mappers

Use `root_input_mapper` / `root_output_mapper` when the graph state is a large
dict and Somia should store an **eval-eligible** subset. **If the right keys are
non-obvious, ask (or propose a default and confirm)** — see "Eval-eligible I/O
and debug-useful traces" above. Do not log the full state by default.

Keep mappers pure and fail-safe — the handler falls back to the raw payload if
a mapper raises.

### Session continuity (multiturn)

Use one of these patterns when you want callback logging to behave like manual
`log_run(..., session_id=...)` across turns:

```python
# 1) Fixed session id (explicit)
handler = SomiaCallbackHandler(
    client=client,
    agent_slug=agent_slug,
    session_id="conversation-123",
)

# 2) Derived session id (preferred for reusable wrappers)
handler = SomiaCallbackHandler(
    client=client,
    agent_slug=agent_slug,
    session_id_mapper=lambda ctx: (ctx.get("metadata") or {}).get("thread_id"),
)
```

Keep `idempotency_key` per invoke/turn. Do not reuse one idempotency key across
different turns unless you want deduplication.

### Templates

See `assets/python-langgraph-example.py`.

### Async and streaming

- HTTP client APIs are sync; the callback still works under `ainvoke` / `astream`
  because LangChain invokes callback methods from the runner.
- Do not convert streaming calls into a single blocking collect unless the user
  asks.
- Preserve whatever invoke API the repository already uses.

---

## B) Manual instrumentation — `start_run`

### When

Custom Python agents, FastAPI handlers, scripts, LangGraph graphs that call
non-LangChain LLMs/tools, or any stack without LangChain callbacks. Do **not**
add `somia[langgraph]` only to force the handler.

Prefer `start_run` + `node_span` / `llm_span` / `tool_span`. Raw `SomiaTrace` +
`client.log_run` remains the low-level escape hatch (same run construction
contract below).

### Run construction contract (read before coding)

One `log_run` call = one user-visible root run. `start_run` / `submit_success`
/ `submit_failure` implement this contract. Data has **two layers**:

| Layer | How you set it | What breaks if wrong |
| --- | --- | --- |
| Run record | `log_run(input=..., output=..., status=..., latency_ms=..., tokens=...)` | Empty/wrong run card in the dashboard |
| Trace tree | `log_run(trace=trace.to_dict())` | Empty/broken span graph; LLM facets missing |

**Hard rules — past integrations failed when these were ignored:**

1. Pass `trace=trace.to_dict()` — **never** `trace=trace` (the live object).
   `start_run` does this for you.
2. Always set top-level `input` and `output` for the run card. Prefer
   **eval-eligible** shapes (replayable input, scorable output). Mirroring them
   on the root span is recommended; span-only I/O is not enough. See
   "Eval-eligible I/O and debug-useful traces".
3. Prefer JSON-serializable **dicts**. Strings/lists are wrapped server-side as
   `{"value": ...}`. Dump Pydantic / message objects before logging.
4. Use two status vocabularies correctly:
   - `log_run(status=...)` → `"SUCCESS"` \| `"FAILED"`
   - `trace.finish(status=...)` / span status → `"OK"` \| `"ERROR"`
5. Call `trace.start()`, finish every span, then `trace.finish(...)` before
   `to_dict()`. An empty `spans` list produces a near-empty server trace.
   `start_run` owns this lifecycle.
6. Token keys differ by layer — see `references/sdk-api.md` (do not mix
   `prompt` vs `prompt_tokens`). `submit_success(tokens=...)` accepts either.
7. For graph nodes use `span.set_node_id("...")`. `kind="node"` alone is dropped.
   `node_span("...")` sets `node_id` for you.

### Minimal correct pattern

```python
from somia import start_run, node_span, llm_span, tool_span

run = start_run(
    user_input,
    input_mapper=lambda payload: payload,
    output_mapper=lambda payload: payload,
)
try:
    with node_span("agent"):
        result = invoke_agent(user_input)
    run.submit_success(output=result)
    return result
except Exception as exc:
    run.submit_failure(exc)
    raise
```

Honor `SOMIA_MONITORING_ENABLED`, `SOMIA_API_KEY`, and `SOMIA_AGENT_SLUG`.
Span helpers no-op when no run is active. Nested `start_run` shares the outer
run (no second `log_run`). Call `run.discard()` if a probe decides not to handle
the request.

There is no `async with log_run(...)` in the SDK. Same pattern for async: await
the agent inside the span, still call sync `submit_success` afterward.

### Multi-span example (optional detail)

```python
from somia import llm_span, node_span, start_run, tool_span

run = start_run(user_input, root_span_name="agent")
with node_span("retrieve", inputs={"query": user_input}) as node:
    docs = retrieve(user_input)
    node.finish(outputs={"docs": docs})

with llm_span(provider="openai", model="gpt-4o") as llm:
    text = call_llm(...)
    llm.set_usage(prompt_tokens=10, completion_tokens=5)
    llm.finish(outputs={"text": text})

with tool_span("lookup", inputs={"q": user_input}) as tool:
    tool.finish(outputs={"ok": True})

result = {"answer": text}
run.submit_success(
    output=result,
    tokens={"prompt": 10, "completion": 5, "total": 15},
)
```

Raw `SomiaTrace.span(..., parent_span_id=...)` is still valid when you cannot
use the contextvar helpers.

### Anti-patterns

```python
# WRONG — passes SomiaTrace object instead of dict
client.log_run(..., trace=trace)

# WRONG — I/O only in spans; run card loses input/output
client.log_run(agent_slug=..., trace=trace.to_dict(), status="SUCCESS")

# WRONG — run status used on the trace
trace.finish(status="SUCCESS")

# WRONG — node without node_id (dropped by converter)
trace.span(name="step", kind="node")

# WRONG — dual root runs for one user request
client.log_run(...)  # outer
client.log_run(...)  # inner helper
# Also wrong: SomiaCallbackHandler AND start_run on the same path
```

### Templates

See `assets/python-log-run-example.py`.

Instrument the **highest-level** boundary that represents one complete
user-visible run. Do not also log every internal helper as a separate root run.

`start_run` measures `latency_ms`. Pass `session_id` for multiturn grouping.
Keep Somia submission fail-open unless the user wants hard failures.

### Attach feedback after `log_run`

Feedback is a **separate** API — not a `log_run` field. After a successful
`log_run`, use `result["trace_id"]` with `client.traces.feedback.create` (and
`update` for scores). See `references/feedback.md`.

For uploading **past** runs/traces (CSV/DB backfill), see
`references/historical-upload.md` instead of live callback wiring.

---

## Recommended metadata (conventions)

`metadata` on `log_run` / the handler is an **arbitrary dict**. Suggested keys:

| Key | Level |
| --- | --- |
| `release` / `git_commit` | recommended |
| `session_id` / `thread_id` / `user_id` | optional (app-specific) |
| `framework` / `model` | optional |

Top-level API fields (not metadata): `agent_slug`, `agent_version`, `status`,
`latency_ms`, `tokens`, `tags`, `environment`, `end_user_id`, `occurred_at`,
`session_id`, `idempotency_key`.

Never put API keys, auth headers, or unnecessary PII in `input`, `output`, or
`metadata`. See `references/privacy-and-security.md`.

---

## Already integrated?

If `SomiaCallbackHandler` or `log_run` is already present on the target path:

1. Do not add a second root instrumentation.
2. Fix merge/fail-open/env issues if broken.
3. Run `scripts/verify_integration.py --offline`.
