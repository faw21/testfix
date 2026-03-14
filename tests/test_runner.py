"""Tests for testfix.runner module."""
from __future__ import annotations

import subprocess
from unittest.mock import patch, MagicMock

import pytest

from testfix.runner import (
    RunResult,
    TestFailure,
    detect_framework,
    run_tests,
    _parse_pytest,
    _parse_jest,
    _parse_go,
    _parse_cargo,
)


# ── detect_framework ──────────────────────────────────────────────────────────


def test_detect_framework_pytest():
    assert detect_framework(["pytest"]) == "pytest"
    assert detect_framework(["python", "-m", "pytest"]) == "pytest"
    assert detect_framework(["py.test", "tests/"]) == "pytest"


def test_detect_framework_jest():
    assert detect_framework(["jest"]) == "jest"
    assert detect_framework(["npx", "jest"]) == "jest"
    assert detect_framework(["npm", "test"]) == "jest"


def test_detect_framework_go():
    assert detect_framework(["go", "test", "./..."]) == "go"


def test_detect_framework_cargo():
    assert detect_framework(["cargo", "test"]) == "cargo"


def test_detect_framework_vitest():
    assert detect_framework(["vitest"]) == "vitest"


def test_detect_framework_fallback():
    assert detect_framework(["python", "run_tests.py"]) == "pytest"


# ── _parse_pytest ─────────────────────────────────────────────────────────────


PYTEST_OUTPUT = """
=========================== short test summary info ============================
FAILED tests/test_auth.py::test_login_wrong_password - AssertionError: expected 401
FAILED tests/test_user.py::test_create_user - TypeError: missing argument
============================== 2 failed, 3 passed in 0.12s ==============================
"""

PYTEST_OUTPUT_DETAILED = """\
_____________________________ test_login_wrong_password _____________________________

    def test_login_wrong_password():
        result = auth.login("user", "wrong")
E   AssertionError: expected 401
E   assert 200 == 401

tests/test_auth.py:25: AssertionError
"""


def test_parse_pytest_summary_fallback():
    failures = _parse_pytest(PYTEST_OUTPUT)
    assert len(failures) == 2
    names = [f.test_name for f in failures]
    assert "test_login_wrong_password" in names
    assert "test_create_user" in names


def test_parse_pytest_detailed():
    failures = _parse_pytest(PYTEST_OUTPUT_DETAILED)
    assert len(failures) == 1
    f = failures[0]
    assert f.test_name == "test_login_wrong_password"
    assert "AssertionError" in f.error_message or "expected 401" in f.error_message
    assert f.file_path == "tests/test_auth.py"
    assert f.line_number == 25


def test_parse_pytest_empty():
    assert _parse_pytest("") == []
    assert _parse_pytest("all tests passed") == []


# ── _parse_jest ───────────────────────────────────────────────────────────────


JEST_OUTPUT = """\
● should add two numbers

  expect(received).toBe(expected)

  Expected: 4
  Received: 3

    at Object.<anonymous> (src/math.test.js:5:20)

● should return user by id

  TypeError: Cannot read property 'id' of undefined

    at Object.<anonymous> (src/user.test.ts:12:15)
"""


def test_parse_jest_basic():
    failures = _parse_jest(JEST_OUTPUT)
    assert len(failures) >= 1
    names = [f.test_name for f in failures]
    assert any("add two numbers" in n for n in names)


def test_parse_jest_empty():
    assert _parse_jest("Tests: 0 passed") == []


# ── _parse_go ─────────────────────────────────────────────────────────────────


GO_OUTPUT = """\
--- FAIL: TestAdd (0.00s)
    math_test.go:15: expected 4 but got 3
--- FAIL: TestSubtract (0.00s)
    math_test.go:22: expected 2 but got 1
FAIL
"""


def test_parse_go_basic():
    failures = _parse_go(GO_OUTPUT)
    assert len(failures) == 2
    assert failures[0].test_name == "TestAdd"
    assert failures[1].test_name == "TestSubtract"


def test_parse_go_empty():
    assert _parse_go("ok  mypackage  0.012s") == []


# ── _parse_cargo ──────────────────────────────────────────────────────────────


CARGO_OUTPUT = """\
test tests::test_add ... FAILED
test tests::test_subtract ... FAILED

failures:

---- tests::test_add stdout ----
thread 'tests::test_add' panicked at 'assertion failed: add(2, 2) == 4', src/lib.rs:10:5
"""


def test_parse_cargo_basic():
    failures = _parse_cargo(CARGO_OUTPUT)
    assert len(failures) >= 1
    names = [f.test_name for f in failures]
    assert "tests::test_add" in names


# ── run_tests ─────────────────────────────────────────────────────────────────


def test_run_tests_command_not_found():
    result = run_tests(["nonexistent_command_xyz_123"])
    assert result.exit_code == 127
    assert "not found" in result.stderr.lower() or "Command" in result.stderr


def test_run_tests_passing():
    """Run a real command that succeeds."""
    result = run_tests(["python", "-c", "print('ok')"])
    assert result.exit_code == 0
    assert result.all_passed


def test_run_tests_failing():
    """Run a real command that fails."""
    result = run_tests(["python", "-c", "import sys; sys.exit(1)"])
    assert result.exit_code != 0
    assert not result.all_passed


def test_run_result_all_passed_true():
    r = RunResult(exit_code=0, stdout="", stderr="", failures=[], passed=5, failed=0)
    assert r.all_passed is True


def test_run_result_all_passed_false():
    r = RunResult(exit_code=1, stdout="", stderr="", failures=[], passed=3, failed=2)
    assert r.all_passed is False
