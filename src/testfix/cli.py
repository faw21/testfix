"""testfix CLI — run tests, fix failures, repeat."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.text import Text

from . import __version__
from .fixer import apply_patches, generate_fixes
from .runner import RunResult, run_tests

console = Console()


# ── Helpers ───────────────────────────────────────────────────────────────────


def _print_run_summary(result: RunResult, attempt: int) -> None:
    """Print a summary of the test run."""
    if result.all_passed:
        console.print(f"[bold green]✅ All tests pass![/] (attempt {attempt})")
    else:
        icon = "🔴"
        console.print(
            f"{icon} [bold red]{result.failed} failing[/], "
            f"[green]{result.passed} passing[/]  "
            f"(attempt {attempt})"
        )
        for failure in result.failures[:5]:
            loc = f"  [dim]{failure.file_path}:{failure.line_number}[/]" if failure.file_path else ""
            console.print(f"   └─ {failure.test_name}{loc}")
        if len(result.failures) > 5:
            console.print(f"   └─ [dim]… and {len(result.failures) - 5} more[/]")


def _print_diff(diff_lines: list[str], file_path: str) -> None:
    """Print a colorised unified diff."""
    diff_text = "".join(diff_lines)
    if diff_text:
        syntax = Syntax(diff_text, "diff", theme="monokai", line_numbers=False)
        console.print(Panel(syntax, title=f"[bold]{file_path}[/]", border_style="dim"))


def _do_fix_cycle(
    command: list[str],
    *,
    cwd: str,
    max_tries: int,
    provider: str,
    model: Optional[str],
    dry_run: bool,
    focus_file: Optional[str],
    verbose: bool,
) -> int:
    """
    Core retry loop.

    Returns:
        0 — all tests pass
        1 — still failing after max_tries
        2 — error (command not found etc.)
    """
    attempt = 0

    while attempt < max_tries:
        attempt += 1
        console.rule(f"[dim]Attempt {attempt}/{max_tries}[/]")

        # Run tests
        result = run_tests(command, cwd=cwd)

        if verbose and result.stderr:
            console.print(f"[dim]{result.stderr[:500]}[/]")

        _print_run_summary(result, attempt)

        if result.exit_code == 127:
            console.print(f"[bold red]Error:[/] {result.stderr}")
            return 2

        if result.all_passed:
            return 0

        if attempt >= max_tries:
            console.print(
                f"\n[yellow]⚠️  Still failing after {max_tries} attempt(s).[/] "
                "Try increasing [bold]--max-tries[/] or switch to a stronger model."
            )
            return 1

        # Generate fixes
        console.print(f"\n[bold cyan]🤖 Asking {provider} to fix {result.failed} failure(s)…[/]")

        try:
            fix_result = generate_fixes(
                result,
                cwd=cwd,
                provider=provider,
                model=model,
                focus_file=focus_file,
            )
        except Exception as exc:
            console.print(f"[bold red]LLM error:[/] {exc}")
            return 2

        if not fix_result.patches:
            console.print("[yellow]⚠️  AI could not suggest fixes.[/] Check the failures manually.")
            return 1

        console.print(f"[green]Generated {fix_result.files_changed} file fix(es)[/]")

        for patch in fix_result.patches:
            _print_diff(patch.diff_lines, patch.file_path)

        if dry_run:
            console.print("\n[bold yellow]--dry-run:[/] Not applying fixes. Exiting.")
            return 1

        # Apply
        applied = apply_patches(fix_result.patches, cwd=cwd)
        for f in applied:
            console.print(f"  [green]✔[/] Applied fix to [bold]{Path(f).name}[/] (backup: .testfix.bak)")

    # Should not reach here
    return 1


# ── CLI ───────────────────────────────────────────────────────────────────────


@click.command(
    name="testfix",
    context_settings={"ignore_unknown_options": True},
)
@click.argument("test_command", nargs=-1, required=True, type=click.UNPROCESSED)
@click.option(
    "--max-tries",
    default=5,
    show_default=True,
    help="Maximum fix-and-retry iterations.",
)
@click.option(
    "--once",
    is_flag=True,
    help="Run tests once, fix once, run again — equivalent to --max-tries 2.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show proposed fixes as diffs but do not apply them.",
)
@click.option(
    "--provider",
    default="claude",
    type=click.Choice(["claude", "openai", "ollama"], case_sensitive=False),
    show_default=True,
    help="LLM provider.",
)
@click.option(
    "--model",
    default=None,
    help="Model name override (e.g. claude-sonnet-4-5, gpt-4o, qwen2.5:7b).",
)
@click.option(
    "--file",
    "focus_file",
    default=None,
    help="Focus fixes on this source file (relative to cwd).",
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    help="Show full stderr output from test runner.",
)
@click.version_option(__version__, "--version")
def main(
    test_command: tuple,
    max_tries: int,
    once: bool,
    dry_run: bool,
    provider: str,
    model: Optional[str],
    focus_file: Optional[str],
    verbose: bool,
) -> None:
    """
    Run tests. If they fail, ask AI to fix them. Repeat until they pass.

    \b
    Examples:
        testfix pytest
        testfix pytest tests/test_auth.py
        testfix --max-tries 3 pytest
        testfix --dry-run pytest
        testfix --provider ollama pytest
        testfix --once npm test
    """
    from dotenv import load_dotenv
    load_dotenv(override=True)

    cwd = str(Path.cwd())
    effective_max = 2 if once else max_tries
    command = list(test_command)

    console.print(
        Panel(
            f"[bold]testfix[/] v{__version__}  "
            f"[dim]command:[/] {' '.join(command)}  "
            f"[dim]provider:[/] {provider}  "
            f"[dim]max-tries:[/] {effective_max}",
            border_style="blue",
        )
    )

    exit_code = _do_fix_cycle(
        command,
        cwd=cwd,
        max_tries=effective_max,
        provider=provider,
        model=model,
        dry_run=dry_run,
        focus_file=focus_file,
        verbose=verbose,
    )

    sys.exit(exit_code)
