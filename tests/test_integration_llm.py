"""Integration tests — real LLM calls for testfix.

These tests make actual API calls and are marked with @pytest.mark.integration.
Run with: pytest -m integration
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from dotenv import load_dotenv

load_dotenv("/Users/aaronwu/Local/my-projects/give-it-all/.env", override=True)

import os

HAS_ANTHROPIC = bool(os.environ.get("ANTHROPIC_API_KEY"))
HAS_OPENAI = bool(os.environ.get("OPENAI_API_KEY"))


@pytest.mark.integration
@pytest.mark.skipif(not HAS_ANTHROPIC, reason="ANTHROPIC_API_KEY not set")
def test_generate_fixes_real_claude(tmp_path):
    """Full integration: buggy Python file + failing test → Claude fixes it."""
    from testfix.fixer import generate_fixes
    from testfix.runner import RunResult, TestFailure

    # Write buggy source
    src = tmp_path / "calc.py"
    src.write_text(
        "def multiply(a, b):\n"
        "    return a + b  # BUG: should be a * b\n"
    )

    failure = TestFailure(
        test_name="test_multiply",
        file_path="tests/test_calc.py",
        line_number=3,
        error_type="AssertionError",
        error_message="assert 5 == 6  (multiply(2, 3) should return 6)",
        traceback=(
            f'  File "{src}", line 2, in multiply\n'
            "    return a + b\n"
            "AssertionError: assert 5 == 6"
        ),
    )
    run_result = RunResult(
        exit_code=1, stdout="", stderr="",
        failures=[failure], passed=0, failed=1,
    )

    result = generate_fixes(run_result, cwd=str(tmp_path), provider="claude", model="claude-haiku-4-5")

    assert result.files_changed >= 1 or result.patches, (
        "Expected at least one file patch but got none. "
        "The LLM may not have understood the format."
    )
    for patch in result.patches:
        if "calc.py" in patch.file_path:
            assert "* b" in patch.fixed_content or "a * b" in patch.fixed_content


@pytest.mark.integration
@pytest.mark.skipif(not HAS_OPENAI, reason="OPENAI_API_KEY not set")
def test_generate_fixes_real_openai(tmp_path):
    """Full integration: buggy Python file + failing test → OpenAI fixes it."""
    from testfix.fixer import generate_fixes
    from testfix.runner import RunResult, TestFailure

    src = tmp_path / "greeter.py"
    src.write_text(
        "def greet(name):\n"
        "    return 'Goodbye, ' + name  # BUG: should be Hello\n"
    )

    failure = TestFailure(
        test_name="test_greet",
        file_path="tests/test_greeter.py",
        line_number=3,
        error_type="AssertionError",
        error_message="assert 'Goodbye, Alice' == 'Hello, Alice'",
        traceback=(
            f'  File "{src}", line 2, in greet\n'
            "AssertionError: assert 'Goodbye, Alice' == 'Hello, Alice'"
        ),
    )
    run_result = RunResult(
        exit_code=1, stdout="", stderr="",
        failures=[failure], passed=0, failed=1,
    )

    result = generate_fixes(run_result, cwd=str(tmp_path), provider="openai", model="gpt-4o-mini")

    assert result.files_changed >= 1 or result.patches, "Expected at least one file patch"
