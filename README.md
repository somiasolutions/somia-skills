# Integrate Somia

Agent Skill that teaches Cursor how to integrate [Somia](https://somia-platform.com) into an existing agent repository with the smallest safe change.

## Skill

| Skill | Description |
| --- | --- |
| [integrate-somia](./skills/integrate-somia) | Inspect the current repository and integrate the Somia Python SDK (`somia`). Use when installing or configuring Somia, logging runs, adding `SomiaCallbackHandler` to LangGraph, linking child pipeline runs, attaching feedback, uploading historical traces, running evals (including `mapping_input` / ad-hoc `runs=`), or troubleshooting monitoring. |

## Command

| Command | Description |
| --- | --- |
| [`/integrate-somia`](./commands/integrate-somia.md) | Invoke the skill on the current repository. |

## Installation

### Cursor Plugin

Install as a [Cursor plugin](https://cursor.com/docs/plugins):

```
/add-plugin integrate-somia
```

### skills CLI

Install via the [skills CLI](https://github.com/vercel-labs/skills):

```bash
npx skills add somia-platform/integrate-somia --skill "integrate-somia"
```

### Manual symlink

Clone this repo and symlink the skill into Cursor's skills directory:

```bash
git clone https://github.com/somia-platform/integrate-somia.git /path/to/integrate-somia
ln -s /path/to/integrate-somia/skills/integrate-somia ~/.cursor/skills/integrate-somia
```

## Prerequisites

You need a [Somia](https://somia-platform.com) account and API key:

```bash
export SOMIA_API_KEY=
export SOMIA_AGENT_SLUG=
export SOMIA_WORKSPACE_ID=
export SOMIA_BASE_URL=https://platform.somiasolutions.com/api
```

Never commit real secrets. Copy placeholders into the project's `.env.example` only.

## Usage

Once installed, the agent will automatically use this skill when relevant — for example:

- Setting up Somia monitoring in a Python agent
- Wiring `SomiaCallbackHandler` into LangGraph
- Logging runs with `start_run` / `SomiaTrace` / `log_run`
- Linking child pipeline runs with `link_child_pipeline_run`
- Attaching feedback on traces
- Uploading historical runs
- Running `client.eval` (including `mapping_input` / ad-hoc `runs=`)
- Troubleshooting an existing Somia integration

You can also invoke it directly in chat with `/integrate-somia`.
