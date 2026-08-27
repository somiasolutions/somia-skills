"""Somia client from environment variables.

Prefer ``SomiaClient.from_env()`` — do not copy a local factory.
"""

from __future__ import annotations

from somia import SomiaClient


if __name__ == "__main__":
    # Local smoke check only — requires real credentials in the environment.
    with SomiaClient.from_env() as client:
        print("SomiaClient created OK", type(client).__name__)
