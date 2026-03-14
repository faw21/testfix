"""AI-powered fixer — reads failing tests and source files, generates fixes."""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .runner import RunResult, TestFailure
from .providers import call_llm


# ── Data models ──────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class FilePatch:
    """A proposed fix for a single file."""

    file_path: str
    original_content: str
    fixed_content: str

    @property
    def diff_lines(self) -> list[str]:
        return list(
            difflib.unified_diff(
                self.original_content.splitlines(keepends=True),
                self.fixed_content.splitlines(keepends=True),
                fromfile=f"a/{self.file_path}",
                tofile=f"b/{self.file_path}",
            )
        )

    @property
    def has_changes(self) -> bool:
        return self.original_content != self.fixed_content


@dataclass(frozen=True)
class FixResult:
    """Result from one AI fix iteration."""

    patches: list[FilePatch] = field(default_factory=list)
    explanation: str = ""
    files_changed: int = 0


# ── Helpers ───────────────────────────────────────────────────────────────────


def _extract_source_files_from_failures(
    failures: list[TestFailure], cwd: str
) -> set[str]:
    """
    Given test failures, guess which *source* (non-test) files need fixing.
    We look at the traceback for .py / .js / .ts / .go / .rs files that are
    NOT in a test directory / not test files.
    """
    source_files: set[str] = set()
    test_patterns = re.compile(
        r"(test_|_test\.|tests/|spec/|__tests__/|\.spec\.|\.test\.)",
        re.IGNORECASE,
    )

    for failure in failures:
        # From the explicit file_path field
        if failure.file_path:
            p = failure.file_path
            if not test_patterns.search(p):
                source_files.add(p)

        # From the traceback — find all file references
        for m in re.finditer(
            r"([\w./\\-]+\.(?:py|js|ts|jsx|tsx|go|rs|rb))", failure.traceback
        ):
            candidate = m.group(1)
            # Skip stdlib / site-packages
            if "site-packages" in candidate or "/lib/" in candidate:
                continue
            if not test_patterns.search(candidate):
                source_files.add(candidate)

    # Filter to files that actually exist
    existing = set()
    for f in source_files:
        p = Path(cwd) / f if not Path(f).is_absolute() else Path(f)
        if p.exists():
            existing.add(str(p.relative_to(cwd)) if p.is_relative_to(cwd) else f)

    return existing


def _read_file(path: str, cwd: str, max_chars: int = 6000) -> str:
    """Read a file relative to cwd, truncating if too large."""
    p = Path(cwd) / path if not Path(path).is_absolute() else Path(path)
    try:
        content = p.read_text(errors="replace")
    except (OSError, UnicodeDecodeError):
        return ""
    if len(content) > max_chars:
        content = content[:max_chars] + f"\n... [truncated at {max_chars} chars]"
    return content


def _build_system_prompt() -> str:
    return (
        "You are an expert software engineer fixing failing tests. "
        "You will be given:\n"
        "1. Failing test output\n"
        "2. The test files\n"
        "3. The source files that the tests exercise\n\n"
        "Your task: FIX THE SOURCE CODE so the tests pass. "
        "Do NOT modify test files. "
        "Only fix the minimal amount of code necessary. "
        "Output ONLY valid code files in this EXACT format (no extra text):\n\n"
        "FILE: <relative/path/to/file.py>\n"
        "```\n"
        "<complete fixed file content>\n"
        "```\n\n"
        "Repeat for each file that needs changes. "
        "If multiple files need changes, output each one. "
        "Do not output files that don't need changes."
    )


def _build_user_prompt(
    run_result: RunResult,
    test_files: dict[str, str],
    source_files: dict[str, str],
    max_failures: int = 5,
) -> str:
    parts = ["## Test Failures\n"]

    failures_to_show = run_result.failures[:max_failures]
    for i, failure in enumerate(failures_to_show, 1):
        parts.append(f"### Failure {i}: {failure.test_name}")
        if failure.file_path:
            loc = failure.file_path
            if failure.line_number:
                loc += f":{failure.line_number}"
            parts.append(f"Location: {loc}")
        if failure.error_type:
            parts.append(f"Error type: {failure.error_type}")
        parts.append(f"Error: {failure.error_message}")
        if failure.traceback:
            tb = failure.traceback[:2000]
            parts.append(f"Traceback:\n```\n{tb}\n```")
        parts.append("")

    if len(run_result.failures) > max_failures:
        parts.append(f"... and {len(run_result.failures) - max_failures} more failures\n")

    if source_files:
        parts.append("## Source Files (fix these)\n")
        for path, content in source_files.items():
            parts.append(f"### FILE: {path}\n```\n{content}\n```\n")

    if test_files:
        parts.append("## Test Files (DO NOT modify)\n")
        for path, content in test_files.items():
            parts.append(f"### FILE: {path}\n```\n{content}\n```\n")

    parts.append(
        "\nNow output the fixed source files in the required format. "
        "Remember: only fix source files, not test files."
    )

    return "\n".join(parts)


def _parse_llm_response(response: str) -> dict[str, str]:
    """
    Parse LLM response into {file_path: content} dict.
    Expected format:
      FILE: path/to/file.py
      ```
      <content>
      ```
    """
    result: dict[str, str] = {}

    # Match blocks: FILE: <path>\n```[lang]\n<content>\n```
    pattern = re.compile(
        r"FILE:\s*([^\n]+)\n```(?:\w+)?\n(.*?)```",
        re.DOTALL,
    )
    for m in pattern.finditer(response):
        file_path = m.group(1).strip()
        content = m.group(2)
        result[file_path] = content

    # Fallback: if no FILE: blocks found, try ```python ... ``` with surrounding context
    if not result:
        # Try to find single code block
        code_match = re.search(r"```(?:\w+)?\n(.*?)```", response, re.DOTALL)
        if code_match:
            result["__unknown__"] = code_match.group(1)

    return result


# ── Public interface ──────────────────────────────────────────────────────────


def generate_fixes(
    run_result: RunResult,
    cwd: str,
    provider: str = "claude",
    model: Optional[str] = None,
    focus_file: Optional[str] = None,
) -> FixResult:
    """
    Given a failed RunResult, generate AI-powered fixes.

    Returns a FixResult with patches for each file that needs changing.
    """
    if run_result.all_passed:
        return FixResult()

    # Find test files from failures
    test_file_paths: set[str] = set()
    test_patterns = re.compile(
        r"(test_|_test\.|tests/|spec/|__tests__/|\.spec\.|\.test\.)",
        re.IGNORECASE,
    )
    for failure in run_result.failures:
        if failure.file_path and test_patterns.search(failure.file_path):
            test_file_paths.add(failure.file_path)

    # Find source files
    if focus_file:
        p = Path(cwd) / focus_file
        source_file_paths = {str(p.relative_to(cwd))} if p.exists() else set()
    else:
        source_file_paths = _extract_source_files_from_failures(
            run_result.failures, cwd
        )

    # Read file contents
    test_files = {p: _read_file(p, cwd) for p in test_file_paths if _read_file(p, cwd)}
    source_files = {p: _read_file(p, cwd) for p in source_file_paths if _read_file(p, cwd)}

    # Build prompt
    system = _build_system_prompt()
    user = _build_user_prompt(run_result, test_files, source_files)

    # Call LLM
    response = call_llm(system=system, user=user, provider=provider, model=model)

    # Parse response
    proposed_changes = _parse_llm_response(response)

    # Create patches
    patches: list[FilePatch] = []
    for file_path, new_content in proposed_changes.items():
        original = _read_file(file_path, cwd)
        patch = FilePatch(
            file_path=file_path,
            original_content=original,
            fixed_content=new_content,
        )
        if patch.has_changes:
            patches.append(patch)

    return FixResult(
        patches=patches,
        explanation=response[:500],  # First 500 chars for display
        files_changed=len(patches),
    )


def apply_patches(patches: list[FilePatch], cwd: str) -> list[str]:
    """
    Apply patches to disk. Creates .testfix.bak backups.
    Returns list of applied file paths.
    """
    applied: list[str] = []
    for patch in patches:
        p = Path(cwd) / patch.file_path if not Path(patch.file_path).is_absolute() else Path(patch.file_path)
        if not p.parent.exists():
            continue
        # Backup
        backup = p.with_suffix(p.suffix + ".testfix.bak")
        if p.exists():
            backup.write_text(p.read_text(errors="replace"))
        # Apply
        p.write_text(patch.fixed_content)
        applied.append(str(p))
    return applied
