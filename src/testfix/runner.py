"""Test runner — executes test commands and parses failure output."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# ── Data models ──────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class TestFailure:
    """A single failing test case."""

    test_name: str
    file_path: Optional[str]
    line_number: Optional[int]
    error_type: Optional[str]
    error_message: str
    traceback: str


@dataclass(frozen=True)
class RunResult:
    """Result from a single test runner execution."""

    exit_code: int
    stdout: str
    stderr: str
    failures: list = field(default_factory=list)
    passed: int = 0
    failed: int = 0
    framework: str = "unknown"

    @property
    def all_passed(self) -> bool:
        return self.exit_code == 0 and self.failed == 0


# ── Framework detection ───────────────────────────────────────────────────────


def detect_framework(command: list) -> str:
    """Guess the test framework from the command."""
    cmd_str = " ".join(command).lower()
    if "pytest" in cmd_str or "py.test" in cmd_str:
        return "pytest"
    if "jest" in cmd_str:
        return "jest"
    if "vitest" in cmd_str:
        return "vitest"
    if "cargo" in cmd_str and "test" in cmd_str:
        return "cargo"
    if "go" in cmd_str and "test" in cmd_str:
        return "go"
    if ("npm" in cmd_str or "npx" in cmd_str) and "test" in cmd_str:
        return "jest"
    if "rspec" in cmd_str:
        return "rspec"
    if command:
        base = Path(command[0]).name.lower()
        if base in ("pytest", "py.test"):
            return "pytest"
        if base in ("jest", "vitest"):
            return base
    return "pytest"


# ── Output parsers ────────────────────────────────────────────────────────────


def _parse_pytest(output: str) -> list:
    """Parse pytest failure output."""
    failures = []
    sections = re.split(r"_{5,}\s+(.+?)\s+_{5,}", output)
    i = 1
    while i + 1 < len(sections):
        test_name = sections[i].strip()
        body = sections[i + 1]
        i += 2

        file_path = None
        line_number = None
        file_match = re.search(r"^\s*([\w/\\.]+\.py):(\d+):", body, re.MULTILINE)
        if file_match:
            file_path = file_match.group(1)
            line_number = int(file_match.group(2))

        error_type = None
        error_message = ""
        error_lines = re.findall(r"^E\s+(.+)$", body, re.MULTILINE)
        if error_lines:
            first = error_lines[0].strip()
            if ":" in first:
                parts = first.split(":", 1)
                error_type = parts[0].strip()
                error_message = parts[1].strip()
            else:
                error_message = first
        else:
            lines = [l for l in body.splitlines() if l.strip()]
            if lines:
                error_message = lines[-1].strip()

        failures.append(
            TestFailure(
                test_name=test_name,
                file_path=file_path,
                line_number=line_number,
                error_type=error_type,
                error_message=error_message,
                traceback=body.strip(),
            )
        )

    if not failures:
        for m in re.finditer(
            r"FAILED\s+([\w/\\.]+\.py)::(\S+)\s*[-\u2013]\s*(.+)", output
        ):
            failures.append(
                TestFailure(
                    test_name=m.group(2),
                    file_path=m.group(1),
                    line_number=None,
                    error_type=None,
                    error_message=m.group(3),
                    traceback="",
                )
            )

    return failures


def _parse_jest(output: str) -> list:
    """Parse jest/vitest failure output."""
    failures = []
    sections = re.split(r"\u25cf\s+", output)
    for section in sections[1:]:
        lines = section.splitlines()
        if not lines:
            continue
        test_name = lines[0].strip()
        body = "\n".join(lines[1:])

        file_path = None
        line_number = None
        loc_match = re.search(r"\(([^)]+\.(?:js|ts|jsx|tsx)):(\d+):\d+\)", body)
        if loc_match:
            file_path = loc_match.group(1)
            line_number = int(loc_match.group(2))

        error_type = None
        error_message = ""
        err_match = re.search(r"^\s*(Error|TypeError|AssertionError)[:\s]+(.+)", body, re.MULTILINE)
        if err_match:
            error_type = err_match.group(1)
            error_message = err_match.group(2).strip()
        else:
            msg_lines = [l.strip() for l in lines[1:4] if l.strip()]
            error_message = msg_lines[0] if msg_lines else ""

        failures.append(
            TestFailure(
                test_name=test_name,
                file_path=file_path,
                line_number=line_number,
                error_type=error_type,
                error_message=error_message,
                traceback=body.strip(),
            )
        )
    return failures


def _parse_go(output: str) -> list:
    """Parse 'go test' failure output."""
    failures = []
    for m in re.finditer(r"--- FAIL: (\S+)", output):
        test_name = m.group(1)
        start = m.start()
        end = output.find("--- FAIL:", start + 1)
        if end == -1:
            end = len(output)
        body = output[start:end]

        file_path = None
        line_number = None
        error_message = ""
        loc_match = re.search(r"\s+(\S+\.go):(\d+):\s*(.*)", body)
        if loc_match:
            file_path = loc_match.group(1)
            line_number = int(loc_match.group(2))
            error_message = loc_match.group(3).strip()

        failures.append(
            TestFailure(
                test_name=test_name,
                file_path=file_path,
                line_number=line_number,
                error_type=None,
                error_message=error_message,
                traceback=body.strip(),
            )
        )
    return failures


def _parse_cargo(output: str) -> list:
    """Parse 'cargo test' failure output."""
    failures = []
    for m in re.finditer(r"test (\S+) \.\.\. FAILED", output):
        test_name = m.group(1)
        start = output.find(f"---- {test_name} stdout ----")
        if start == -1:
            failures.append(
                TestFailure(
                    test_name=test_name,
                    file_path=None,
                    line_number=None,
                    error_type=None,
                    error_message="Test failed",
                    traceback="",
                )
            )
            continue
        end = output.find("----", start + 10)
        if end == -1:
            end = len(output)
        body = output[start:end]
        error_message = body.strip().split("\n")[-1] if body.strip() else "Test failed"
        failures.append(
            TestFailure(
                test_name=test_name,
                file_path=None,
                line_number=None,
                error_type=None,
                error_message=error_message,
                traceback=body.strip(),
            )
        )
    return failures


def _parse_output(framework: str, output: str):
    """Parse test output and return (failures, passed_count, failed_count)."""
    failures = []

    if framework == "pytest":
        failures = _parse_pytest(output)
        m = re.search(r"(\d+) failed", output)
        failed = int(m.group(1)) if m else len(failures)
        m2 = re.search(r"(\d+) passed", output)
        passed = int(m2.group(1)) if m2 else 0
    elif framework in ("jest", "vitest"):
        failures = _parse_jest(output)
        m = re.search(r"Tests:\s+(\d+) failed", output)
        failed = int(m.group(1)) if m else len(failures)
        m2 = re.search(r"(\d+) passed", output)
        passed = int(m2.group(1)) if m2 else 0
    elif framework == "go":
        failures = _parse_go(output)
        failed = len(failures)
        passed = 0
    elif framework == "cargo":
        failures = _parse_cargo(output)
        m = re.search(r"(\d+) failed", output)
        failed = int(m.group(1)) if m else len(failures)
        m2 = re.search(r"(\d+) passed", output)
        passed = int(m2.group(1)) if m2 else 0
    else:
        failed = len(failures)
        passed = 0

    return failures, passed, failed


# ── Public interface ──────────────────────────────────────────────────────────


def run_tests(command: list, cwd=None) -> RunResult:
    """Run a test command and return structured results."""
    framework = detect_framework(command)

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            cwd=cwd,
        )
    except FileNotFoundError as exc:
        return RunResult(
            exit_code=127,
            stdout="",
            stderr=f"Command not found: {command[0]} — {exc}",
            failures=[],
            passed=0,
            failed=0,
            framework=framework,
        )

    combined_output = result.stdout + "\n" + result.stderr
    failures, passed, failed = _parse_output(framework, combined_output)

    return RunResult(
        exit_code=result.returncode,
        stdout=result.stdout,
        stderr=result.stderr,
        failures=failures,
        passed=passed,
        failed=failed,
        framework=framework,
    )
