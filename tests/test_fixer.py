"""Tests for testfix.fixer module."""
from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from testfix.fixer import (
    FilePatch,
    FixResult,
    _extract_source_files_from_failures,
    _parse_llm_response,
    _build_system_prompt,
    apply_patches,
    generate_fixes,
)
from testfix.runner import RunResult, TestFailure


# ── FilePatch ─────────────────────────────────────────────────────────────────


def test_filepatch_has_changes_true():
    p = FilePatch(file_path="a.py", original_content="x = 1", fixed_content="x = 2")
    assert p.has_changes is True


def test_filepatch_has_changes_false():
    p = FilePatch(file_path="a.py", original_content="x = 1", fixed_content="x = 1")
    assert p.has_changes is False


def test_filepatch_diff_lines():
    p = FilePatch(file_path="a.py", original_content="x = 1\n", fixed_content="x = 2\n")
    diff = p.diff_lines
    assert any("-x = 1" in line for line in diff)
    assert any("+x = 2" in line for line in diff)


# ── _extract_source_files_from_failures ──────────────────────────────────────


def test_extract_source_files_from_traceback(tmp_path):
    src = tmp_path / "auth.py"
    src.write_text("def login(): pass\n")
    # Use relative path in traceback so regex + file resolution is deterministic
    rel_path = "auth.py"

    failure = TestFailure(
        test_name="test_login",
        file_path="tests/test_auth.py",
        line_number=10,
        error_type="AssertionError",
        error_message="Expected 401",
        traceback=f"  File \"{rel_path}\", line 5, in login\n    raise ValueError",
    )

    result = _extract_source_files_from_failures([failure], str(tmp_path))
    # auth.py should be found (not a test file)
    assert any("auth.py" in f for f in result)


def test_extract_skips_test_files(tmp_path):
    test_file = tmp_path / "tests" / "test_auth.py"
    test_file.parent.mkdir()
    test_file.write_text("def test_x(): pass\n")

    failure = TestFailure(
        test_name="test_x",
        file_path="tests/test_auth.py",
        line_number=1,
        error_type=None,
        error_message="fail",
        traceback="",
    )

    result = _extract_source_files_from_failures([failure], str(tmp_path))
    # test files should be excluded from source candidates
    assert not any("test_auth.py" in f for f in result)


# ── _parse_llm_response ───────────────────────────────────────────────────────


def test_parse_llm_response_basic():
    response = """\
FILE: src/auth.py
```python
def login(user, password):
    return 401
```
"""
    result = _parse_llm_response(response)
    assert "src/auth.py" in result
    assert "def login" in result["src/auth.py"]


def test_parse_llm_response_multiple_files():
    response = """\
FILE: src/a.py
```python
a = 1
```

FILE: src/b.py
```python
b = 2
```
"""
    result = _parse_llm_response(response)
    assert len(result) == 2
    assert "src/a.py" in result
    assert "src/b.py" in result


def test_parse_llm_response_empty():
    assert _parse_llm_response("") == {}
    assert _parse_llm_response("No changes needed.") == {}


def test_parse_llm_response_fallback_code_block():
    response = """\
Here is the fix:
```python
def fixed(): pass
```
"""
    result = _parse_llm_response(response)
    assert len(result) == 1
    assert "def fixed" in list(result.values())[0]


# ── _build_system_prompt ──────────────────────────────────────────────────────


def test_build_system_prompt_contains_key_instructions():
    prompt = _build_system_prompt()
    assert "FIX THE SOURCE CODE" in prompt
    assert "Do NOT modify test files" in prompt
    assert "FILE:" in prompt


# ── apply_patches ─────────────────────────────────────────────────────────────


def test_apply_patches_creates_backup(tmp_path):
    src = tmp_path / "calc.py"
    src.write_text("def add(a, b): return a - b\n")

    patch_obj = FilePatch(
        file_path="calc.py",
        original_content="def add(a, b): return a - b\n",
        fixed_content="def add(a, b): return a + b\n",
    )
    applied = apply_patches([patch_obj], cwd=str(tmp_path))

    assert len(applied) == 1
    assert src.read_text() == "def add(a, b): return a + b\n"
    backup = src.with_suffix(".py.testfix.bak")
    assert backup.exists()
    assert backup.read_text() == "def add(a, b): return a - b\n"


def test_apply_patches_no_change(tmp_path):
    src = tmp_path / "calc.py"
    src.write_text("def add(a, b): return a + b\n")

    patch_obj = FilePatch(
        file_path="calc.py",
        original_content="def add(a, b): return a + b\n",
        fixed_content="def add(a, b): return a + b\n",
    )
    applied = apply_patches([patch_obj], cwd=str(tmp_path))
    assert len(applied) == 1  # still applied, just no content change


# ── generate_fixes (mocked) ───────────────────────────────────────────────────


def test_generate_fixes_no_failures():
    run_result = RunResult(
        exit_code=0, stdout="", stderr="", failures=[], passed=5, failed=0
    )
    result = generate_fixes(run_result, cwd="/tmp")
    assert result.files_changed == 0
    assert result.patches == []


def test_generate_fixes_with_llm_mock(tmp_path):
    src = tmp_path / "math.py"
    src.write_text("def add(a, b):\n    return a - b\n")

    failure = TestFailure(
        test_name="test_add",
        file_path=str(tmp_path / "tests/test_math.py"),
        line_number=5,
        error_type="AssertionError",
        error_message="assert 3 == 4",
        traceback=f"  File \"{src}\", line 2",
    )
    run_result = RunResult(
        exit_code=1, stdout="", stderr="", failures=[failure], passed=0, failed=1
    )

    llm_response = f"""\
FILE: math.py
```python
def add(a, b):
    return a + b
```
"""

    with patch("testfix.fixer.call_llm", return_value=llm_response):
        result = generate_fixes(run_result, cwd=str(tmp_path))

    assert result.files_changed >= 1
    assert any("math.py" in p.file_path for p in result.patches)
