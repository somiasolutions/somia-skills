#!/usr/bin/env python3
"""Detect integration-relevant facts about a repository (read-only).

Usage:
  python detect_repository.py [PATH]

Prints JSON to stdout. Does not modify files.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

LANGGRAPH_RE = re.compile(r"\b(langgraph|StateGraph|CompiledStateGraph)\b")
LANGCHAIN_RE = re.compile(r"\b(langchain|langchain_core)\b")
SOMIA_RE = re.compile(
    r"\b(somia|SomiaClient|SomiaCallbackHandler|SomiaTrace|SomiaRun|"
    r"start_run|node_span|llm_span|tool_span|log_run)\b"
)
INVOKE_RE = re.compile(r"\b(ainvoke|astream|\.invoke\(|\.stream\()\b")
CALLBACK_RE = re.compile(r"\b(callbacks|SomiaCallbackHandler|CallbackHandler)\b")


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


def _package_manager(root: Path) -> str | None:
    if (root / "uv.lock").exists():
        return "uv"
    if (root / "poetry.lock").exists() or (
        (root / "pyproject.toml").exists()
        and "[tool.poetry]" in _read_text(root / "pyproject.toml")
    ):
        return "poetry"
    if (root / "Pipfile").exists():
        return "pipenv"
    if list(root.glob("requirements*.txt")) or (root / "pyproject.toml").exists():
        return "pip"
    return None


def _somia_declared(root: Path) -> bool:
    blobs = []
    for name in ("pyproject.toml", "Pipfile"):
        p = root / name
        if p.exists():
            blobs.append(_read_text(p))
    for p in root.glob("requirements*.txt"):
        blobs.append(_read_text(p))
    text = "\n".join(blobs).lower()
    return bool(re.search(r"\bsomia\b", text))


def _installed_somia_version() -> str | None:
    try:
        from importlib.metadata import version

        return version("somia")
    except Exception:
        return None


def _iter_python_files(root: Path) -> list[Path]:
    skip = {
        ".venv",
        "venv",
        "node_modules",
        ".git",
        "dist",
        "build",
        "__pycache__",
        ".cursor",
        "site-packages",
    }
    files: list[Path] = []
    for path in root.rglob("*.py"):
        if any(part in skip for part in path.parts):
            continue
        files.append(path)
    return files


def detect(root: Path) -> dict[str, Any]:
    py_files = _iter_python_files(root)
    frameworks: list[str] = []
    invocation_modes: set[str] = set()
    entrypoints: list[str] = []
    has_callbacks = False
    has_somia_code = False
    has_log_run = False
    has_callback_handler = False

    for path in py_files:
        text = _read_text(path)
        if not text.strip():
            continue
        rel = str(path.relative_to(root))
        if LANGGRAPH_RE.search(text) and "langgraph" not in frameworks:
            frameworks.append("langgraph")
        if LANGCHAIN_RE.search(text) and "langchain" not in frameworks:
            frameworks.append("langchain")
        if SOMIA_RE.search(text):
            has_somia_code = True
            entrypoints.append(rel)
        if "log_run" in text or "start_run" in text:
            has_log_run = True
        if "SomiaCallbackHandler" in text:
            has_callback_handler = True
        if CALLBACK_RE.search(text):
            has_callbacks = True
        for match in INVOKE_RE.finditer(text):
            token = match.group(1).strip("().")
            invocation_modes.add(token if token != "invoke" else "invoke")

    # Heuristic entrypoints when no Somia yet: files mentioning graph invoke
    if not entrypoints:
        for path in py_files:
            text = _read_text(path)
            if LANGGRAPH_RE.search(text) and INVOKE_RE.search(text):
                entrypoints.append(str(path.relative_to(root)))

    language = "python" if py_files or (root / "pyproject.toml").exists() else "unknown"

    return {
        "root": str(root.resolve()),
        "language": language,
        "package_manager": _package_manager(root),
        "frameworks": frameworks,
        "somia_declared": _somia_declared(root),
        "somia_installed_version": _installed_somia_version(),
        "somia_code_present": has_somia_code,
        "has_log_run": has_log_run,
        "has_callback_handler": has_callback_handler,
        "existing_callbacks": has_callbacks,
        "agent_entrypoints": sorted(set(entrypoints))[:50],
        "invocation_modes": sorted(invocation_modes),
        "recommended_path": (
            "langgraph_callback"
            if "langgraph" in frameworks
            else ("start_run" if language == "python" else "unknown")
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "path",
        nargs="?",
        default=".",
        help="Repository root to inspect (default: cwd)",
    )
    args = parser.parse_args()
    root = Path(args.path).resolve()
    if not root.is_dir():
        print(json.dumps({"error": f"not a directory: {root}"}), file=sys.stderr)
        return 2
    print(json.dumps(detect(root), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
