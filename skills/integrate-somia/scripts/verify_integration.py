#!/usr/bin/env python3
"""Verify a Somia integration in a target repository.

Usage:
  python verify_integration.py [--root PATH] [--offline|--live]

--offline (default): no network, no credentials required.
--live: optional authenticated smoke call (needs SOMIA_API_KEY).
"""

from __future__ import annotations

import argparse
import ast
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Finding:
    level: str  # ok | warn | error
    code: str
    message: str


@dataclass
class Report:
    findings: list[Finding] = field(default_factory=list)

    def add(self, level: str, code: str, message: str) -> None:
        self.findings.append(Finding(level, code, message))

    @property
    def ok(self) -> bool:
        return not any(f.level == "error" for f in self.findings)


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


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


SECRET_PATTERNS = [
    re.compile(
        r"""SOMIA_API_KEY\s*=\s*['\"](?!your_|changeme|xxx|placeholder)[^'\"]{8,}['\"]"""
    ),
    re.compile(r"""api_key\s*=\s*['\"]sk-[^'\"]+['\"]"""),
]


def check_dependency(report: Report) -> None:
    try:
        import somia  # noqa: F401
        from importlib.metadata import version

        report.add(
            "ok", "import", f"somia importable (version {version('somia')})"
        )
    except Exception as exc:
        report.add("error", "import", f"somia not importable: {exc}")
        return

    try:
        import inspect
        from somia import SomiaClient

        sig = str(inspect.signature(SomiaClient.log_run))
        if "agent_slug" not in sig:
            report.add(
                "warn", "signature", f"log_run signature unexpected: {sig}"
            )
        else:
            report.add("ok", "signature", "SomiaClient.log_run has agent_slug")
    except Exception as exc:
        report.add("warn", "signature", f"could not inspect log_run: {exc}")


def check_secrets(root: Path, report: Report) -> None:
    for path in _iter_python_files(root):
        text = _read(path)
        for pattern in SECRET_PATTERNS:
            if pattern.search(text):
                report.add(
                    "error",
                    "secret",
                    f"possible hardcoded secret in {path.relative_to(root)}",
                )
                return
    env = root / ".env"
    if env.exists():
        report.add(
            "warn",
            "dotenv",
            ".env exists — ensure it is gitignored and not committed",
        )
    example = root / ".env.example"
    if example.exists() and "SOMIA_API_KEY" in _read(example):
        report.add("ok", "env_example", ".env.example mentions SOMIA_API_KEY")
    report.add(
        "ok",
        "secret_scan",
        "no obvious hardcoded Somia secrets in Python sources",
    )


def check_instrumentation(root: Path, report: Report) -> None:
    files = _iter_python_files(root)
    callback_files: list[str] = []
    log_run_files: list[str] = []
    start_run_files: list[str] = []
    replace_config = False

    def _is_app_code(rel: str) -> bool:
        parts = Path(rel).parts
        if "tests" in parts or "test" in parts:
            return False
        # Skip the published package sources when verifying inside the SDK repo.
        if parts[:2] == ("src", "somia"):
            return False
        return True

    for path in files:
        text = _read(path)
        rel = str(path.relative_to(root))
        # SDK implementation itself calls log_run from the handler — skip it.
        if "class SomiaCallbackHandler" in text:
            continue
        if not _is_app_code(rel):
            continue
        if "SomiaCallbackHandler" in text:
            callback_files.append(rel)
        if re.search(r"\.log_run\s*\(", text):
            log_run_files.append(rel)
        if re.search(r"\b(start_run|start_aisa_run)\s*\(", text):
            start_run_files.append(rel)
        # crude anti-pattern: config={"callbacks": [...]} without merge helpers
        if re.search(r"""config\s*=\s*\{\s*['\"]callbacks['\"]\s*:""", text):
            if "SomiaCallbackHandler" in text or "somia" in text.lower():
                replace_config = True

    manual_files = sorted(set(log_run_files) | set(start_run_files))
    if callback_files and manual_files:
        # Same file is a strong smell; different files may be different agents
        overlap = set(callback_files) & set(manual_files)
        if overlap:
            report.add(
                "error",
                "dual_instrument",
                "same file uses SomiaCallbackHandler and start_run/log_run: "
                + ", ".join(sorted(overlap)),
            )
        else:
            report.add(
                "warn",
                "dual_instrument",
                "repo has both SomiaCallbackHandler and start_run/log_run — confirm they "
                "are not on the same execution path",
            )
    elif callback_files:
        report.add(
            "ok",
            "instrumentation",
            "SomiaCallbackHandler present in: "
            + ", ".join(callback_files[:5]),
        )
    elif start_run_files:
        report.add(
            "ok",
            "instrumentation",
            "start_run present in: " + ", ".join(start_run_files[:5]),
        )
    elif log_run_files:
        report.add(
            "ok",
            "instrumentation",
            "log_run present in: " + ", ".join(log_run_files[:5]),
        )
    else:
        report.add(
            "warn",
            "instrumentation",
            "no application SomiaCallbackHandler, start_run, or log_run found "
            "(ok if this repo only vendors the SDK)",
        )

    if replace_config:
        report.add(
            "warn",
            "config_replace",
            "found config={'callbacks': ...} near Somia usage — ensure existing "
            "callbacks/thread_id are merged, not replaced",
        )

    # Count handler constructions in application code only
    handler_count = 0
    for path in files:
        rel = str(path.relative_to(root))
        if not _is_app_code(rel):
            continue
        try:
            tree = ast.parse(_read(path))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                name = ""
                if isinstance(node.func, ast.Name):
                    name = node.func.id
                elif isinstance(node.func, ast.Attribute):
                    name = node.func.attr
                if name == "SomiaCallbackHandler":
                    handler_count += 1
    if handler_count > 3:
        report.add(
            "warn",
            "handler_count",
            f"SomiaCallbackHandler constructed {handler_count} times — check for duplicates",
        )


def check_live(report: Report) -> None:
    api_key = os.getenv("SOMIA_API_KEY")
    if not api_key:
        report.add("error", "live", "SOMIA_API_KEY missing for --live mode")
        return
    try:
        from somia import SomiaClient

        with SomiaClient(
            base_url=os.getenv(
                "SOMIA_BASE_URL", "https://platform.somiasolutions.com/api"
            ),
            api_key=api_key,
            timeout=30.0,
        ) as client:
            # Cheap authenticated call when available
            try:
                next(client.workspaces.iter_all(per_page=1), None)
                report.add(
                    "ok", "live", "authenticated workspaces.iter_all succeeded"
                )
            except Exception as exc:
                report.add("warn", "live", f"workspaces call failed: {exc}")
    except Exception as exc:
        report.add("error", "live", f"live check failed: {exc}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root", default=".", help="Repository root (default: cwd)"
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--offline", action="store_true", default=True)
    mode.add_argument("--live", action="store_true")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    report = Report()
    if not root.is_dir():
        print(f"ERROR not a directory: {root}", file=sys.stderr)
        return 2

    check_dependency(report)
    check_secrets(root, report)
    check_instrumentation(root, report)
    if args.live:
        check_live(report)

    for finding in report.findings:
        print(f"{finding.level.upper():5} [{finding.code}] {finding.message}")

    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
