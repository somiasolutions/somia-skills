---
name: integrate-somia
description: Inspect this repository and integrate the Somia Python SDK with the smallest safe change.
---

Inspect this repository and integrate Somia with the smallest safe change.

Somia validates and improves AI agents: monitor runs → debug from traces →
promote production I/O into validation sets → eval after changes. Shape logged
input/output so they are **eval-eligible** (replayable as dataset examples /
`agent_fn` args) and traces so they are **debug-useful** (what the agent did
and how). Do not create validation sets unless explicitly asked.

Determine whether the repository should use:

1. LangGraph / LangChain callbacks via `SomiaCallbackHandler`, or
2. Manual instrumentation via `start_run` + typed spans (preferred over raw
   `SomiaTrace` + `log_run`), or
3. Evaluation-only via `client.eval` (if the user only asked for evals), or
4. Hosted sessions via `client.sessions` (if calling a Somia pipeline), or
5. Child-pipeline linking via `link_child_pipeline_run` (if this agent calls
   another Somia agent or hosted pipeline).

Use the `integrate-somia` skill. Read `references/sdk-api.md` before writing
SDK code. Do not invent imports or parameters. Do not dual-instrument the same
execution path. Do not hardcode secrets. Do not create validation sets, criteria,
or eval profiles unless explicitly requested. Nested `start_run` is not a child
agent — use `link_child_pipeline_run` for composition.

Prefer merging callbacks into existing config. Keep monitoring fail-open.

If eval-eligible input/output or trace depth is non-obvious (large state dicts,
multiple candidate fields, multi-step agent, sensitive intermediates), ask — or
propose a default mapping and confirm — before writing instrumentation. Do not
dump full application state by default. If dataset keys differ from `agent_fn`,
use `mapping_input` / `input_fields` rather than rewriting the agent.

Verify with `scripts/verify_integration.py --offline` when practical, then report:

- Integration method selected
- Eval-eligible input/output mapping and trace depth
- Composition / eval-mapping / ad-hoc choices when applicable
- Files modified
- Dependency / version
- Required environment variables
- Verification results and any remaining risks
