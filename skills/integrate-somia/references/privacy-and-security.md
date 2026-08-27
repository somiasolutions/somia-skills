# Privacy and security

## Credentials

- Never hardcode API keys, tokens, or passwords in source, tests, notebooks, or
  commit messages.
- Put variable **names** in `.env.example`; keep real values in local `.env` or
  a secret manager (gitignored).
- Do not invent credentials to "make the integration work."
- Do not print `SOMIA_API_KEY` (or other secrets) during verification or in logs.

## What not to send to Somia

Avoid putting the following in `input`, `output`, `trace`, or `metadata` unless
the user explicitly accepts the risk and has a retention policy. The same rules
apply to **historical / backfill uploads** (`references/historical-upload.md`):

- API keys, bearer tokens, cookies, session secrets
- Raw authorization headers
- Passwords, private keys, connection strings
- Unnecessary PII (full personal dossiers, payment data, health data)

Prefer redacting or mapping to identifiers your app already uses.

**Do not dump full application / graph state by default.** Choose
**eval-eligible** run input/output (safe enough and shaped enough to promote into
a validation set later) and **debug-useful** spans. If that mapping is unclear,
ask the user (or propose a minimal mapping and confirm) — see
`references/monitoring.md` → "Eval-eligible I/O and debug-useful traces".
Eval-eligible does **not** mean log everything.

## Fail-open vs fail-closed

Default for **monitoring**: fail-open (log a warning; continue serving users).

Do not fail-open authentication to **your** app — only isolate Somia
observability failures from the agent path.

## Dependency and network

- Install from PyPI with the project's normal tooling.
- Default base URL: `https://platform.somiasolutions.com/api` unless the user specifies
  another environment.
- Do not disable TLS or log full HTTP payloads containing secrets.

## Diff review

Before finishing, check the diff for:

- Real secrets or `.env` files with values
- Accidental commit of local credential files
- Over-broad logging of user content
- Dual instrumentation that could duplicate sensitive payloads
