# Feedback on traces

Attach human (or imported) feedback to a Somia **trace** after a run exists.
Read `references/sdk-api.md` for exact signatures.

For batch / past-run uploads, also read `references/historical-upload.md`.

## When

| Situation | Path |
| --- | --- |
| Live agent just called `log_run` | Use `result["trace_id"]`, then feedback APIs |
| LangGraph `SomiaCallbackHandler` | Handler submits `log_run` async — obtain `trace_id` from the API / dashboard if you need feedback later; do not dual `log_run` |
| Historical CSV / DB backfill | `references/historical-upload.md` |

Feedback is **not** part of `log_run`. It is always a separate call on
`client.traces.feedback`.

## API surface

```python
# Create (text / ground truth / status only — NO scores)
fb = client.traces.feedback.create(
    trace_id,
    feedback="thumbs_up",           # required str
    ground_truth=None,              # optional str
    status="PENDING",               # default; see statuses below
)

# Set scores via update (create cannot take score fields)
fb = client.traces.feedback.update(
    fb.id,
    score_type="boolean",           # "boolean" | "score_1_5"
    score=1,                        # boolean: 0|1; score_1_5: 1..5
)

client.traces.feedback.get(fb.id)
client.traces.feedback.list(trace_id, page=1, per_page=50)
client.traces.feedback.delete(fb.id)
```

Wire:

- Create / list: `POST|GET /v1/external/traces/{trace_id}/feedback`
- Get / update / delete: `GET|PUT|DELETE /v1/external/feedback/{feedback_id}`

## Fields

| Field | On create | On update | Notes |
| --- | --- | --- | --- |
| `feedback` | required `str` | optional | Free text; use a placeholder like `"Reaction"` when you only have a thumbs score |
| `ground_truth` | optional | optional | Correct / expected answer text when available |
| `status` | optional (default `PENDING`) | optional | `PENDING` \| `DRAFT` \| `APPROVED` |
| `score_type` | **not accepted** | optional | `boolean` \| `score_1_5` |
| `score` | **not accepted** | optional | With `boolean`: `0` or `1`. With `score_1_5`: `1`–`5`. Integer only |

## Status vocabulary

| Status | Use when |
| --- | --- |
| `PENDING` | Default for new / imported feedback awaiting review |
| `DRAFT` | Work-in-progress review |
| `APPROVED` | Client already reviewed / trusts this label |

Do not invent other status strings.

## Two-step pattern (thumbs / rating)

External `create` does **not** accept `score` / `score_type`. Always:

1. `create(...)` with text (+ optional `ground_truth` / `status`)
2. `update(..., score_type=..., score=...)` when you have a numeric signal

```python
result = client.log_run(
    agent_slug=agent_slug,
    input=user_input,
    output=agent_output,
    trace=trace.to_dict(),
    status="SUCCESS",
)
trace_id = result["trace_id"]

created = client.traces.feedback.create(
    trace_id,
    feedback=comment or "Reaction",
    status="PENDING",
)
client.traces.feedback.update(
    created.id,
    score_type="boolean",
    score=1 if thumbs_up else 0,
)
```

For a 1–5 rating, use `score_type="score_1_5"` and `score` in `1..5`.

## Hard rules

1. You need a **trace_id** from a successful `log_run` (or an existing trace).
2. Never pass score fields to `create` — they are ignored / invalid on that path.
3. `score` must be an **int** (not `bool`, not float).
4. On idempotent re-uploads, skip creating feedback again when `log_run` does not
   return a fresh `trace_id` (see `references/historical-upload.md`).
5. Do not invent imports or methods; only use `client.traces.feedback.*`.

## Anti-patterns

- Putting feedback text only in `log_run(metadata=...)` and skipping the feedback API
- Calling `create` twice on every retry (duplicates)
- Using run `status` / trace span status vocabulary for feedback status
- Mixing `boolean` scores with values other than `0` / `1`

## Related

- Signatures: `references/sdk-api.md` → `client.traces.feedback`
- Past runs: `references/historical-upload.md`
- Live monitoring contract: `references/monitoring.md`
