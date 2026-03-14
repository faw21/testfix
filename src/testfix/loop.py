"""Retry loop — run tests → fix failures → repeat until green or max tries."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional

from .runner import RunResult, run_tests
from .fixer import FilePatch, FixResult, apply_patches, generate_fixes


# ── Data types ────────────────────────────────────────────────────────────────

@dataclass
class IterationRecord:
    """Record of a single run-fix iteration."""

    iteration: int
    run_result: RunResult
    fix_result: Optional[FixResult] = None
    applied_files: list[str] = field(default_factory=list)


@dataclass
class LoopResult:
    """Final result of the fix loop."""

    success: bool               # True if tests pass at end
    iterations: list[IterationRecord]
    total_files_fixed: int = 0

    @property
    def attempts(self) -> int:
        return len(self.iterations)

    @property
    def final_run(self) -> Optional[RunResult]:
        if self.iterations:
            return self.iterations[-1].run_result
        return None


# ── Loop ──────────────────────────────────────────────────────────────────────

def run_fix_loop(
    command: list[str],
    cwd: str,
    provider: str = "claude",
    model: Optional[str] = None,
    max_tries: int = 3,
    dry_run: bool = False,
    focus_file: Optional[str] = None,
    on_run_start: Optional[Callable[[int], None]] = None,
    on_run_done: Optional[Callable[[RunResult], None]] = None,
    on_fix_start: Optional[Callable[[int], None]] = None,
    on_fix_done: Optional[Callable[[FixResult, list[str]], None]] = None,
) -> LoopResult:
    """
    Run tests → fix failures → repeat up to max_tries times.

    Args:
        command: Test command to run (e.g. ["pytest", "tests/"]).
        cwd: Working directory.
        provider: LLM provider ("claude", "openai", "ollama").
        model: Model override.
        max_tries: Maximum fix iterations.
        dry_run: Show diffs but don't write files.
        focus_file: Only fix this source file (optional).
        on_run_start: Callback(iteration) before each test run.
        on_run_done: Callback(RunResult) after each test run.
        on_fix_start: Callback(iteration) before each fix attempt.
        on_fix_done: Callback(FixResult, applied_files) after each fix.

    Returns:
        LoopResult summarising all iterations.
    """
    iterations: list[IterationRecord] = []
    total_files_fixed = 0

    for attempt in range(1, max_tries + 1):
        # ── Run tests ─────────────────────────────────────────────────────────
        if on_run_start:
            on_run_start(attempt)

        run_result = run_tests(command, cwd=cwd)

        if on_run_done:
            on_run_done(run_result)

        record = IterationRecord(iteration=attempt, run_result=run_result)
        iterations.append(record)

        if run_result.all_passed:
            return LoopResult(
                success=True,
                iterations=iterations,
                total_files_fixed=total_files_fixed,
            )

        # Last iteration: no point generating more fixes
        if attempt == max_tries:
            break

        # ── Generate fixes ────────────────────────────────────────────────────
        if on_fix_start:
            on_fix_start(attempt)

        fix_result = generate_fixes(
            run_result=run_result,
            cwd=cwd,
            provider=provider,
            model=model,
            focus_file=focus_file,
        )
        record.fix_result = fix_result

        if not fix_result.patches:
            # AI couldn't find files to fix — give up
            break

        # ── Apply patches ─────────────────────────────────────────────────────
        if not dry_run:
            applied = apply_patches(fix_result.patches, cwd=cwd)
            record.applied_files = applied
            total_files_fixed += len(applied)
        else:
            record.applied_files = [p.file_path for p in fix_result.patches if p.has_changes]

        if on_fix_done:
            on_fix_done(fix_result, record.applied_files)

        if not record.applied_files:
            # No actual changes — no point retrying
            break

    # Final run to check if last fix worked (if not dry_run and we applied something)
    if not dry_run and iterations and iterations[-1].applied_files:
        if on_run_start:
            on_run_start(len(iterations) + 1)
        final_run = run_tests(command, cwd=cwd)
        if on_run_done:
            on_run_done(final_run)
        iterations.append(IterationRecord(iteration=len(iterations) + 1, run_result=final_run))
        if final_run.all_passed:
            return LoopResult(
                success=True,
                iterations=iterations,
                total_files_fixed=total_files_fixed,
            )

    return LoopResult(
        success=False,
        iterations=iterations,
        total_files_fixed=total_files_fixed,
    )
