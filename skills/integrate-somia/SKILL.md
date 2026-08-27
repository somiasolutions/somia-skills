---
name: integrate-somia
description: >-
  Integrates the Somia Python SDK (`somia`) into agent repositories. Use when
  installing or configuring Somia, logging runs with start_run /
  SomiaClient.log_run / SomiaTrace, adding SomiaCallbackHandler to LangGraph,
  attaching feedback on traces (client.traces.feedback), uploading historical /
  past runs or traces (backfill), running client.eval, calling hosted Somia
  sessions, or troubleshooting Somia monitoring. Triggers on Somia,
  SOMIA_API_KEY, SOMIA_AGENT_SLUG, SomiaClient, SomiaCallbackHandler, SomiaTrace,
  start_run, SomiaRun, node_span, llm_span, tool_span, feedback, historical
  upload, backfill, integrate-somia. Do not use for generic LangGraph
  explanations unrelated to Somia.
metadata:
  author: somia
  version: "0.1.0"
  sdk-doc-version: "0.1.0a3"
---

# Integrate Somia

When invoked (including via `/integrate-somia`), inspect **this** repository and
integrate Somia with the smallest safe change. Preserve the existing
architecture and avoid unrelated changes. Do not create validation sets,
criteria, or eval profiles unless asked.

This skill is for **clients installing `somia` from PyPI** — never assume the
SDK source repository is available.

## Why Somia (product loop)

Somia is for **validating and improving AI agents**:

```text
Monitor runs (input / output / trace)
  → Debug failures and understand behavior from the trace
  → Promote production I/O into a validation set
  → Change the agent
  → Eval against that set
  → Ship when quality is good enough
```

When instrumenting, choose **eval-eligible** run `input`/`output` (payloads you
could later turn into validation examples and feed to `agent_fn`) and
**debug-useful** traces (what the agent did and how). See
`references/monitoring.md` → "Eval-eligible I/O and debug-useful traces".

Do **not** create validation sets during a normal integrate unless the user
asks — but **shape** monitoring so that path stays open.

## Non-goals

- Do not create validation sets, criteria, eval profiles, knowledge bases, or
  pipelines unless the user explicitly asks to manage those resources via the API.
- Prefer dataset/profile IDs from the Somia dashboard (or existing env vars).
- Do not turn this into a general Somia platform API tutorial.
- Feedback on traces and historical run/trace upload **are in scope** when the
  user asks — use `references/feedback.md` and
  `references/historical-upload.md`.

## Core rules

1. Inspect the repository before modifying files.
2. Never invent Somia SDK imports, methods, or parameters.
3. Read `references/sdk-api.md` before writing SDK code. Prefer signatures from
   the installed package (`inspect`) when they differ from this skill.
4. Pick exactly one primary integration path (see decision table).
5. One user-visible agent execution → one Somia root run. Do not dual-instrument
   the same path with both `SomiaCallbackHandler` and `log_run`.
6. For manual monitoring prefer `start_run` + `node_span` / `llm_span` /
   `tool_span`. If using raw `log_run`: pass `trace.to_dict()` (never the
   object); set top-level `input`/`output`; use `SUCCESS`/`FAILED` on the run
   and `OK`/`ERROR` on the trace. Read the run construction contract in
   `references/monitoring.md`.
7. Choose **eval-eligible** run input/output and **debug-useful** traces. Prefer
   payloads you could later add to a validation set and replay via `agent_fn`.
   If that mapping is non-obvious, **ask** (or propose a default and confirm).
   Do not dump full application state by default. See `references/monitoring.md`
   → "Eval-eligible I/O and debug-useful traces".
8. Preserve existing callbacks, config (`thread_id`, checkpointing, tags), and
   sync / async / streaming behavior.
9. Never hardcode credentials. Update `.env.example` only with placeholders.
10. Keep monitoring fail-open: agent execution must continue if Somia is down or
    misconfigured (when the chosen API supports it).
11. Make the integration idempotent: re-running this skill must not duplicate wiring.

## Identifiers (critical)

| Identifier | Type | Use for |
| --- | --- | --- |
| `agent_slug` | string, e.g. `"support-bot"` | External agents: `log_run`, `SomiaCallbackHandler`, local eval |
| `agent_id` (numeric) | int, e.g. `123` | Internal hosted pipelines: `sessions.*`, server-side eval |

Local eval takes `agent_id="my-slug"` and the SDK forwards it as `agent_slug` on
the wire. Do not mix slug and numeric pipeline id conventions.

## Repository inspection

Identify language, package manager, existing `somia` version, agent framework,
top-level execution boundary, sync/async/streaming, existing callbacks/tracing,
env conventions, and tests.

Optionally run:

```bash
python scripts/detect_repository.py
```

(from this skill directory, or copy the script into the target repo temporarily).

For Python, inspect when present: `pyproject.toml`, lockfiles, `requirements*.txt`,
agent entry points, and framework imports (`langgraph`, `langchain`).

## Decision table

| Situation | Preferred path | Read |
| --- | --- | --- |
| Somia not installed / not configured | Setup | `references/setup.md`, `references/privacy-and-security.md` |
| LangGraph (or LangChain callback-compatible) agent | `SomiaCallbackHandler` | `references/monitoring.md`, `references/sdk-api.md` |
| Custom / non-LangGraph agent | `start_run` + typed spans | `references/monitoring.md` (run construction contract), `references/sdk-api.md` |
| User wants feedback on a trace (thumbs, rating, ground truth) | `client.traces.feedback` after `log_run` | `references/feedback.md`, `references/sdk-api.md` |
| User wants to upload past / historical runs or traces | Batch `log_run` + optional feedback | `references/historical-upload.md`, `references/feedback.md` |
| User asks to validate / eval / dataset experiment | `client.eval` | `references/evaluations.md`, `references/sdk-api.md` |
| User asks to call a hosted Somia pipeline | `client.sessions.*` | `references/sdk-api.md` (hosted sessions) |
| Somia already integrated | Verify or repair — do not duplicate | `references/troubleshooting.md` |

## Implementation workflow

1. Inspect the repository (or run `detect_repository.py`).
2. Select exactly one primary path from the table.
3. Read the required references (and `references/sdk-api.md` before any SDK code).
4. Check installed SDK version vs `metadata.sdk-doc-version` in this frontmatter.
5. Install or update dependencies only when necessary (`pip install somia --pre`;
   add `[langgraph]` only for callback integration).
6. Apply the smallest coherent code change. Prefer a small module such as
   `integrations/somia/`. If eval-eligible I/O or trace depth is non-obvious,
   ask or confirm before coding.
7. Add env placeholders to `.env.example` — never real secrets.
8. Add or update tests when the project already has them.
9. Run formatter / type checker / tests when available.
10. Run `scripts/verify_integration.py --offline` when practical.
11. Review the diff for duplicated instrumentation, over-broad logged state, and
    exposed data.

## Verification checklist

- SDK import resolves for the chosen APIs.
- Existing callbacks/config were merged, not replaced.
- Async stays async; streaming stays streaming.
- Success and failure paths both close / submit the run (or handler does).
- Run input/output are eval-eligible (replayable / scorable); traces are useful
  for debugging multi-step behavior when applicable.
- Missing credentials produce documented fail-open or clear errors — no invented keys.
- No secrets committed.
- Re-running this skill would not add a second handler or second `log_run` on the same path.

## Final report

Report: integration method selected, **eval-eligible input/output mapping and
trace depth**, feedback / historical-upload choices when applicable, files
modified, dependency/version, required env vars, verification commands run,
checks skipped, and any privacy or duplication risks.

## Assets and scripts

- Copy-paste templates: `assets/` (including `python-historical-upload-example.py`)
- Detection: `scripts/detect_repository.py`
- Verification: `scripts/verify_integration.py --offline` (default) or `--live`
