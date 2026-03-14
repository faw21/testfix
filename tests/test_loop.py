"""Tests for testfix.loop module."""
from __future__ import annotations

from unittest.mock import MagicMock, call, patch

import pytest

from testfix.fixer import FilePatch, FixResult
from testfix.loop import IterationRecord, LoopResult, run_fix_loop
from testfix.runner import RunResult, TestFailure


# ── Helpers ───────────────────────────────────────────────────────────────────

def _passing():
    return RunResult(exit_code=0, stdout="1 passed", stderr="", failures=[], passed=1, failed=0)


def _failing(n=1):
    failures = [
        TestFailure(
            test_name=f"test_fail_{i}",
            file_path="tests/test_foo.py",
            line_number=i * 5,
            error_type="AssertionError",
            error_message="assert False",
            traceback="",
        )
        for i in range(1, n + 1)
    ]
    return RunResult(exit_code=1, stdout="", stderr="", failures=failures, passed=0, failed=n)


def _fix_result_with_patch():
    return FixResult(
        patches=[FilePatch("src/foo.py", "old\n", "new\n")],
        explanation="fixed",
        files_changed=1,
    )


def _fix_result_empty():
    return FixResult(patches=[], explanation="nothing found", files_changed=0)


# ── LoopResult ────────────────────────────────────────────────────────────────

def test_loop_result_attempts():
    result = LoopResult(
        success=True,
        iterations=[
            IterationRecord(1, _passing()),
        ],
    )
    assert result.attempts == 1


def test_loop_result_final_run():
    run = _passing()
    result = LoopResult(success=True, iterations=[IterationRecord(1, run)])
    assert result.final_run is result.iterations[-1].run_result


def test_loop_result_final_run_empty():
    result = LoopResult(success=False, iterations=[])
    assert result.final_run is None


# ── run_fix_loop ──────────────────────────────────────────────────────────────

def test_loop_passes_on_first_run():
    """Tests already pass — no fixing needed."""
    with (
        patch("testfix.loop.run_tests", return_value=_passing()) as mock_run,
        patch("testfix.loop.generate_fixes") as mock_fix,
    ):
        result = run_fix_loop(["pytest"], cwd="/tmp")

    assert result.success is True
    assert result.attempts == 1
    mock_fix.assert_not_called()


def test_loop_fixes_on_second_attempt():
    """First run fails, fix is applied, second run passes."""
    run_sequence = [_failing(), _passing()]
    fix = _fix_result_with_patch()

    with (
        patch("testfix.loop.run_tests", side_effect=run_sequence),
        patch("testfix.loop.generate_fixes", return_value=fix),
        patch("testfix.loop.apply_patches", return_value=["src/foo.py"]),
    ):
        result = run_fix_loop(["pytest"], cwd="/tmp", max_tries=3)

    assert result.success is True
    assert result.total_files_fixed == 1


def test_loop_exhausts_max_tries():
    """Tests keep failing even after max_tries."""
    fix = _fix_result_with_patch()

    with (
        patch("testfix.loop.run_tests", return_value=_failing()),
        patch("testfix.loop.generate_fixes", return_value=fix),
        patch("testfix.loop.apply_patches", return_value=["src/foo.py"]),
    ):
        result = run_fix_loop(["pytest"], cwd="/tmp", max_tries=2)

    assert result.success is False


def test_loop_stops_when_no_files_to_fix():
    """AI returns no patches — loop stops early."""
    with (
        patch("testfix.loop.run_tests", return_value=_failing()),
        patch("testfix.loop.generate_fixes", return_value=_fix_result_empty()),
    ):
        result = run_fix_loop(["pytest"], cwd="/tmp", max_tries=5)

    assert result.success is False


def test_loop_dry_run_does_not_apply():
    """In dry-run mode, patches are shown but not applied."""
    fix = _fix_result_with_patch()

    with (
        patch("testfix.loop.run_tests", side_effect=[_failing(), _passing()]),
        patch("testfix.loop.generate_fixes", return_value=fix),
        patch("testfix.loop.apply_patches") as mock_apply,
    ):
        result = run_fix_loop(["pytest"], cwd="/tmp", dry_run=True, max_tries=3)

    mock_apply.assert_not_called()


def test_loop_callbacks_are_called():
    """Verify all progress callbacks fire at the right times."""
    on_run_start = MagicMock()
    on_run_done = MagicMock()
    on_fix_start = MagicMock()
    on_fix_done = MagicMock()
    fix = _fix_result_with_patch()

    with (
        patch("testfix.loop.run_tests", side_effect=[_failing(), _passing()]),
        patch("testfix.loop.generate_fixes", return_value=fix),
        patch("testfix.loop.apply_patches", return_value=["src/foo.py"]),
    ):
        run_fix_loop(
            ["pytest"],
            cwd="/tmp",
            max_tries=3,
            on_run_start=on_run_start,
            on_run_done=on_run_done,
            on_fix_start=on_fix_start,
            on_fix_done=on_fix_done,
        )

    assert on_run_start.called
    assert on_run_done.called
    assert on_fix_start.called
    assert on_fix_done.called


def test_loop_focus_file_passed_to_generate_fixes():
    """focus_file option is forwarded to generate_fixes."""
    fix = _fix_result_with_patch()

    with (
        patch("testfix.loop.run_tests", side_effect=[_failing(), _passing()]),
        patch("testfix.loop.generate_fixes", return_value=fix) as mock_gen,
        patch("testfix.loop.apply_patches", return_value=["src/auth.py"]),
    ):
        run_fix_loop(["pytest"], cwd="/tmp", focus_file="src/auth.py", max_tries=3)

    mock_gen.assert_called_once()
    _, kwargs = mock_gen.call_args
    assert kwargs.get("focus_file") == "src/auth.py" or mock_gen.call_args[0][3] == "src/auth.py" or "src/auth.py" in str(mock_gen.call_args)
