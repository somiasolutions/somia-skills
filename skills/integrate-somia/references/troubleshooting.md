# Troubleshooting

## Import errors

| Symptom | Fix |
| --- | --- |
| `ModuleNotFoundError: somia` | `pip install somia --pre` (or pin) and sync lockfile |
| `SomiaCallbackHandler` ImportError / None | `pip install "somia[langgraph]" --pre` |
| Wrong Python | Use `>=3.11` |

## Auth and config

| Symptom | Fix |
| --- | --- |
| `AuthError` / 401 | Check `SOMIA_API_KEY` |
| `ValueError: workspace_id is required` | Set `SOMIA_WORKSPACE_ID` (integer), or pass `workspace_id` explicitly to monitoring APIs |
| `ValueError: SOMIA_WORKSPACE_ID must be an integer` | Use an integer value for `SOMIA_WORKSPACE_ID` (for example `7`) |
| Monitoring silently skipped | Ensure `SOMIA_AGENT_SLUG` (or legacy `SOMIA_AGENT_ID`) and API key; check `SOMIA_MONITORING_ENABLED` |
| Wrong environment | Confirm `SOMIA_BASE_URL` |

## Instrumentation bugs

| Symptom | Fix |
| --- | --- |
| Duplicate runs for one request | Remove either callback or `log_run` / `start_run` on that path — keep one |
| Lost `thread_id` / checkpoints | Merge callbacks into existing config; do not replace `config` |
| Runs missing for async graph | Confirm handler is in `config["callbacks"]` for `ainvoke`/`astream` |
| Concurrent runs corrupted | Do not share one mutable handler across overlapping invokes |
| `log_run` with empty / broken trace | Call `trace.start()`, finish spans, `trace.finish(...)`, pass `trace.to_dict()` (not the object) |
| Run card missing input/output | Set top-level `log_run(input=..., output=...)`; do not rely on spans alone |
| Status rejected / confusing UI | `log_run` uses SUCCESS/FAILED; trace/spans use OK/ERROR |
| Node steps missing in UI | Call `span.set_node_id(...)`; `kind="node"` without `node_id` is dropped |
| Token counts missing | Top-level tokens use `prompt`/`completion`/`total`; span usage uses `*_tokens` |
| Non-JSON / Pydantic payloads fail | Dump to dict/str before `log_run` / span finish |
| Child run not nested in Monitor | Call `link_child_pipeline_run` inside the parent span that made the call; do not use nested `start_run` as composition |
| `link_child_pipeline_run` seems ignored | No active `start_run` (fail-open no-op), or the handler path was used — composition needs `start_run` |
| `caller_*` missing on the child run | Pass them on the child's `start_run` / `log_run` / `sessions.*`; unresolvable IDs are dropped server-side — do not invent them |

## Identifiers

| Symptom | Fix |
| --- | --- |
| 400 on server eval for external agent | Use local eval with `agent_fn` + slug |
| Confused slug vs pipeline id | External monitoring/eval local → string slug; hosted sessions/server eval → numeric pipeline id |

## Eval

| Symptom | Fix |
| --- | --- |
| `ValueError: dataset_id is required` | Pass `dataset_id` with `agent_fn` |
| `ValueError: Provide agent_fn ... or set_ids` | Pass one complete mode: `agent_fn`, `runs=`, or `set_ids`/`dataset_id` |
| `ValueError: runs cannot be combined with agent_fn` | Ad-hoc `runs=` cannot be mixed with local `agent_fn` |
| `ValueError: mapping_input and input_fields apply only to local evals` | Mapping is local-only — drop it on ad-hoc / server eval |
| `mapping_coverage.resolvable == 0` | Nothing was submitted; fix `mapping_input` / `input_fields` (or dataset keys) |
| Unresolved required fields with `force=False` | Supply mapping, or pass `force=True` to skip those examples |
| `TimeoutError` on `wait` | Raise timeout, check run in UI, verify network |
| Async agent fails in local thread pool | Wrap with sync `agent_fn` |

## Version skew

If installed `somia` differs from this skill's `sdk-doc-version` (`0.1.0a4`):

1. Prefer `inspect.signature` on the installed package.
2. Do not invent APIs from memory.
3. Tell the user about the mismatch.

## Verify

```bash
python scripts/verify_integration.py --offline
python scripts/verify_integration.py --live   # needs real credentials
```
