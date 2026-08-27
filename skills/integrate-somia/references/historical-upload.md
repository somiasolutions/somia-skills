# Historical run / trace upload

Help a client upload **past** agent interactions into Somia: input/output,
optional span trees, optional feedback, and provenance metadata.

This is a **batch / backfill** path (`log_run` + optional feedback). Do **not**
use `SomiaCallbackHandler` for offline CSV/DB imports.

Always read `references/sdk-api.md` before coding. For feedback details, read
`references/feedback.md`. Shape I/O with
`references/monitoring.md` → "Eval-eligible I/O and debug-useful traces".

## When

| Client has | Use this path |
| --- | --- |
| Saved prompts/responses (and maybe labels) from production | Yes — scripted `log_run` per record |
| Optional LangSmith / custom span trees | Yes — map into `SomiaTrace` or upload I/O-only |
| Live LangGraph graph they want instrumented going forward | No — use `references/monitoring.md` instead |

One historical interaction → **one** `log_run` root run.

## End-to-end flow

```text
Map eval-eligible input/output
  → Optional sdk-1.0 SomiaTrace (or minimal / omitted)
  → client.log_run(..., metadata=..., idempotency_key=...)
  → If feedback present and result has fresh trace_id:
       traces.feedback.create → traces.feedback.update (scores)
```

## 1) Input / output format

| Layer | Field | Prefer |
| --- | --- | --- |
| Run record | `input` | Replayable task payload (dict preferred) |
| Run record | `output` | Scorable final answer / artifact |
| Run record | `status` | `"SUCCESS"` / `"FAILED"` (run-level) |

Hard rules (same as live monitoring):

1. Always set top-level `input` / `output` when you care about the run card.
2. Prefer JSON-serializable **dicts**. Non-dicts are stored as `{"value": ...}`.
3. Dump Pydantic / message objects before upload.
4. Apply the same privacy scrubbing as live runs
   (`references/privacy-and-security.md`). Historical uploads are not exempt.

Ask (or propose + confirm) when the source schema is large or ambiguous — same
design tests as monitoring (replay / judge / diagnose).

## 2) Trace format (three variants)

### A) Client has a useful span tree

Build a `SomiaTrace` and pass `trace=trace.to_dict()`:

```python
trace = SomiaTrace().start()
with trace.span(name="agent", kind="agent", inputs=safe_input) as root:
    # optional children: node / llm / tool with parent_span_id=root.span_id
    root.finish(outputs=safe_output)
trace.finish(status="OK")  # or "ERROR"
# pass trace.to_dict() to log_run
```

`to_dict()` shape (`sdk-1.0`): see `references/sdk-api.md` → `SomiaTrace`.

When mapping a **foreign** span tree:

| Rule | Detail |
| --- | --- |
| Prefer one parentless `kind="agent"` root | Mirrors top-level I/O |
| `kind="node"` | Must call `set_node_id(...)` or the converter drops it |
| Children | Set `parent_span_id` to the parent span's id |
| Status | Span/trace: `"OK"` \| `"ERROR"` — not SUCCESS/FAILED |
| Empty `spans` | Near-empty UI — include at least one finished root span if you claim to upload a tree |

Do not invent span kinds outside `agent` \| `node` \| `llm` \| `tool` \| `internal`.

### B) Client has I/O only (no spans)

Acceptable for backfills that mainly need the run card + feedback:

- Prefer a **minimal root agent span** mirroring I/O (better UI), **or**
- Omit `trace=` and upload run-only I/O

```python
trace = SomiaTrace().start()
with trace.span(name="agent", kind="agent", inputs=safe_input) as span:
    span.finish(outputs=safe_output)
trace.finish(status="OK")
```

### C) Client has partial / noisy trees

Prefer curated meaningful steps over dumping megabyte intermediates. Root-only
is fine when middle steps are missing or unsafe to upload.

## 3) Feedback for the uploaded trace

If the source row has labels / comments / ground truth:

1. `log_run` → read `result["trace_id"]`
2. `client.traces.feedback.create(trace_id, feedback=..., ground_truth=..., status=...)`
3. If there is a thumbs or 1–5 score: `client.traces.feedback.update(..., score_type=..., score=...)`

Full contract: `references/feedback.md`.

**Idempotent re-upload:** if `log_run` returns no fresh `trace_id` (run already
existed via `idempotency_key`), **skip** creating feedback again to avoid
duplicates.

```python
run_result = client.log_run(..., idempotency_key=f"import-{source_id}")
trace_id = run_result.get("trace_id")
if has_feedback and trace_id:
    created = client.traces.feedback.create(trace_id, feedback=text, status="PENDING")
    if thumbs is not None:
        client.traces.feedback.update(
            created.id,
            score_type="boolean",
            score=1 if thumbs else 0,
        )
```

## 4) Metadata (provenance)

`metadata` is an arbitrary dict on `log_run`. For historical uploads, include
enough to find the source row later:

| Key | Purpose |
| --- | --- |
| `source` | e.g. `"chat_interactions_csv"`, `"prod_export"` |
| `csv_row_id` / `external_id` | Stable id from the client's system |
| `original_timestamp` | When the interaction happened (ISO string if available) |
| Client-specific ids | e.g. commercial / account ids the client already uses |
| Thumbs label (optional) | e.g. `"thumbs": "thumbs_up"` — convenience; **scores still go through the feedback API** |

Also set top-level `agent_version` when the client knows which agent version
produced the run. Do **not** put secrets or unnecessary PII in metadata.

## 5) Batch hygiene

| Concern | Practice |
| --- | --- |
| Retries / re-runs | Stable `idempotency_key` per source row (e.g. `f"import-{row_id}"`) |
| Duplicate feedback | Only attach feedback when `trace_id` is present on this response |
| Errors | Decide with the user: stop on first failure vs continue-and-count |
| Rate / volume | Upload in a script with logging; do not wire into the live request path |
| Dual instrumentation | Never also add `SomiaCallbackHandler` for the same offline records |

`latency_ms` / `tokens` are optional on historical uploads — set them only when
the source data has reliable values (do not invent).

## Minimal example

See `assets/python-historical-upload-example.py`.

```python
from somia import SomiaClient, SomiaTrace

record = {
    "id": "42",
    "prompt": "What is Somia?",
    "response": "An agent validation platform.",
    "is_correct": True,
    "feedback_comment": "Clear answer",
}

with SomiaClient(base_url=base_url, api_key=api_key) as client:
    safe_input = {"prompt": record["prompt"]}
    safe_output = {"response": record["response"]}

    trace = SomiaTrace().start()
    with trace.span(name="agent", kind="agent", inputs=safe_input) as span:
        span.finish(outputs=safe_output)
    trace.finish(status="OK")

    run_result = client.log_run(
        agent_slug=agent_slug,
        input=safe_input,
        output=safe_output,
        trace=trace.to_dict(),
        status="SUCCESS",
        metadata={
            "source": "historical_import",
            "external_id": record["id"],
            "thumbs": "thumbs_up",
        },
        idempotency_key=f"historical-{record['id']}",
    )

    trace_id = run_result.get("trace_id")
    if trace_id:
        created = client.traces.feedback.create(
            str(trace_id),
            feedback=record["feedback_comment"],
            status="PENDING",
        )
        client.traces.feedback.update(
            created.id,
            score_type="boolean",
            score=1,
        )
```

## Checklist before coding

- [ ] Eval-eligible input/output mapping confirmed (or proposed)
- [ ] Trace depth chosen: full tree / minimal root / run-only
- [ ] Feedback fields mapped (`feedback` text, `ground_truth`, scores)
- [ ] Provenance metadata + stable `idempotency_key`
- [ ] Privacy scrub applied to I/O, spans, and metadata

## Related

- Feedback API: `references/feedback.md`
- Live monitoring: `references/monitoring.md`
- Signatures: `references/sdk-api.md`
- Privacy: `references/privacy-and-security.md`
