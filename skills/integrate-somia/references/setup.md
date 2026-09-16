# Somia setup

## Detect the environment

1. Confirm Python `>=3.11`.
2. Find the package manager (`uv`, `poetry`, `pip`, `pipenv`).
3. Check whether `somia` is already declared and which version is installed.
4. Detect LangGraph / LangChain imports before choosing extras.

## Install

Default (monitoring via `start_run` / `log_run`, evals, sessions):

```bash
pip install somia --pre
```

Pin when the project requires reproducibility:

```bash
pip install "somia==0.1.0a4"
```

LangGraph callback integration only:

```bash
pip install "somia[langgraph]" --pre
```

Add the dependency to the project's dependency file (`pyproject.toml`,
`requirements.txt`, etc.) using the project's usual style. Do not invent a
second dependency management system.

## Client factory

Use `SomiaClient.from_env()` — do not copy a local factory. See
`assets/python-client-factory.py`.

```python
from somia import SomiaClient

with SomiaClient.from_env() as client:
    ...
```

Optional kwargs (`api_key=`, `base_url=`) override environment values.

For long-lived apps (e.g. shared callback handler), keep one client and close on
shutdown.

## Environment configuration

Copy placeholders from `assets/env.example` into the project's `.env.example`.
Never write real API keys into the repository.

Minimum for monitoring:

- `SOMIA_API_KEY`
- `SOMIA_AGENT_SLUG` (external agents)
- `SOMIA_WORKSPACE_ID` (integer; required by `log_run` / `start_run` /
  `SomiaCallbackHandler`)

Optional: `SOMIA_BASE_URL`, `SOMIA_AGENT_VERSION`,
`SOMIA_MONITORING_ENABLED`.

For evals: `SOMIA_DATASET_ID`, `SOMIA_PROFILE_ID` (UUIDs from the Somia UI).

## Connectivity smoke check (optional)

Only with real credentials available locally (never invent them):

```python
from somia import SomiaClient

with SomiaClient.from_env() as client:
    # cheap authenticated call if available in the installed version, e.g.:
    next(client.workspaces.iter_all(per_page=1), None)
```

If credentials are missing, document the required env vars and stop — do not
fabricate keys or call production endpoints with placeholders.

## After setup

Continue with `references/monitoring.md` or `references/evaluations.md`
depending on the user's goal.
