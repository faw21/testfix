"""Tests for testfix.cli module."""
from __future__ import annotations

from unittest.mock import patch, MagicMock
from click.testing import CliRunner

from testfix.cli import main
from testfix.runner import RunResult, TestFailure
from testfix.fixer import FixResult, FilePatch


def _passing_run():
    return RunResult(exit_code=0, stdout="1 passed", stderr="", failures=[], passed=1, failed=0)


def _failing_run():
    failure = TestFailure(
        test_name="test_foo",
        file_path="tests/test_foo.py",
        line_number=10,
        error_type="AssertionError",
        error_message="Expected 1",
        traceback="",
    )
    return RunResult(exit_code=1, stdout="1 failed", stderr="", failures=[failure], passed=0, failed=1)


def test_main_all_pass():
    runner = CliRunner()
    with patch("testfix.cli.run_tests", return_value=_passing_run()):
        result = runner.invoke(main, ["pytest"])
    assert result.exit_code == 0
    assert "All tests pass" in result.output


def test_main_dry_run():
    runner = CliRunner()
    patch_obj = FilePatch(
        file_path="src/foo.py",
        original_content="x = 1\n",
        fixed_content="x = 2\n",
    )
    fix_result = FixResult(patches=[patch_obj], explanation="", files_changed=1)

    with patch("testfix.cli.run_tests", return_value=_failing_run()), \
         patch("testfix.cli.generate_fixes", return_value=fix_result):
        result = runner.invoke(main, ["--dry-run", "pytest"])

    assert "--dry-run" in result.output or "dry-run" in result.output.lower()
    assert result.exit_code == 1  # still failing


def test_main_command_not_found():
    runner = CliRunner()
    bad_run = RunResult(
        exit_code=127, stdout="", stderr="Command not found: notexist",
        failures=[], passed=0, failed=0
    )
    with patch("testfix.cli.run_tests", return_value=bad_run):
        result = runner.invoke(main, ["notexist"])
    assert result.exit_code == 2


def test_main_version():
    runner = CliRunner()
    result = runner.invoke(main, ["--version"])
    assert result.exit_code == 0
    assert "0.1.0" in result.output


def test_main_once_flag():
    runner = CliRunner()
    patch_obj = FilePatch(
        file_path="src/foo.py",
        original_content="x = 1\n",
        fixed_content="x = 2\n",
    )
    fix_result = FixResult(patches=[patch_obj], explanation="", files_changed=1)
    call_count = {"n": 0}

    def fake_run_tests(cmd, cwd=None):
        call_count["n"] += 1
        return _failing_run()

    with patch("testfix.cli.run_tests", side_effect=fake_run_tests), \
         patch("testfix.cli.generate_fixes", return_value=fix_result), \
         patch("testfix.cli.apply_patches", return_value=["src/foo.py"]):
        result = runner.invoke(main, ["--once", "pytest"])

    # --once = max_tries 2 → run test once, fix, run again
    assert call_count["n"] <= 2


def test_main_no_fixes_available():
    runner = CliRunner()
    empty_fix = FixResult(patches=[], explanation="", files_changed=0)
    with patch("testfix.cli.run_tests", return_value=_failing_run()), \
         patch("testfix.cli.generate_fixes", return_value=empty_fix):
        result = runner.invoke(main, ["pytest"])
    assert result.exit_code == 1
    assert "could not suggest" in result.output.lower() or "fix" in result.output.lower()


def test_main_fix_and_pass():
    runner = CliRunner()
    patch_obj = FilePatch(
        file_path="src/calc.py",
        original_content="return a - b\n",
        fixed_content="return a + b\n",
    )
    fix_result = FixResult(patches=[patch_obj], explanation="Fixed subtraction", files_changed=1)

    runs = [_failing_run(), _passing_run()]
    with patch("testfix.cli.run_tests", side_effect=runs), \
         patch("testfix.cli.generate_fixes", return_value=fix_result), \
         patch("testfix.cli.apply_patches", return_value=["src/calc.py"]):
        result = runner.invoke(main, ["pytest"])

    assert result.exit_code == 0
    assert "All tests pass" in result.output
