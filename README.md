# testfix

[![PyPI version](https://img.shields.io/pypi/v/testfix-ai.svg)](https://pypi.org/project/testfix-ai/)
[![Python](https://img.shields.io/pypi/pyversions/testfix-ai.svg)](https://pypi.org/project/testfix-ai/)
[![Tests](https://github.com/faw21/testfix/actions/workflows/tests.yml/badge.svg)](https://github.com/faw21/testfix/actions/workflows/tests.yml)

> AI-powered CLI that automatically fixes failing tests — non-interactive, pipeable, CI-ready.

```bash
# Tests failing? Just run testfix.
$ testfix pytest

──────────────────────── Attempt 1/5 ────────────────────────
🔴 2 failing, 8 passing (attempt 1)
   └─ test_login  tests/test_auth.py:10
   └─ test_register  tests/test_auth.py:25

🤖 Asking claude to fix 2 failure(s)…
Generated 1 file fix(es)

─── src/auth.py ──────────────────────────────────────────────
--- a/src/auth.py
+++ b/src/auth.py
@@ -3,7 +3,7 @@
 def login(user, password):
-    return db.find(user) is not None        # BUG: doesn't check password
+    return db.find(user, password) is not None

  ✔ Applied fix to auth.py (backup: .testfix.bak)

──────────────────────── Attempt 2/5 ────────────────────────
✅ All tests pass! (attempt 2)
```

## Why testfix?

Every developer faces the same loop: *run tests → fix code → run tests → ...*

Tools like aider are powerful but require an interactive session. **testfix** is different:

| Feature | testfix | aider |
|---------|---------|-------|
| Non-interactive | ✅ | ❌ (interactive REPL) |
| CI/CD ready | ✅ | ❌ |
| Pre-push hook | ✅ | ❌ |
| Pipe-friendly | ✅ | ❌ |
| Local LLM (ollama) | ✅ | ✅ |
| Auto-retry loop | ✅ | manual |

## Install

```bash
pip install testfix
```

Requires Python 3.9+ and one of: Anthropic API key, OpenAI API key, or [ollama](https://ollama.ai) running locally.

## Usage

```bash
# Basic: run pytest, fix failures, retry up to 5 times
testfix pytest

# Specific test file
testfix pytest tests/test_auth.py

# Max iterations
testfix --max-tries 3 pytest

# Fix once and re-run (equivalent to --max-tries 2)
testfix --once pytest

# Preview fixes as diffs WITHOUT applying
testfix --dry-run pytest

# Use OpenAI instead of Claude
testfix --provider openai pytest

# Use local ollama (free, no API key needed)
testfix --provider ollama pytest

# Use a stronger model for hard bugs
testfix --provider openai --model gpt-4o pytest

# Focus fixes on a specific source file
testfix --file src/auth.py pytest

# Watch mode: auto-fix whenever source files change (v0.2+)
testfix --watch pytest

# Works with any test runner
testfix npm test
testfix go test ./...
testfix cargo test
testfix vitest
```

## Supported Test Frameworks

| Framework | Failure parsing | Exit code |
|-----------|----------------|-----------|
| pytest | ✅ Full traceback | ✅ |
| jest / vitest | ✅ Test name + location | ✅ |
| go test | ✅ Test name + file:line | ✅ |
| cargo test | ✅ Test name | ✅ |
| rspec | ✅ Test name + location | ✅ |

## Pre-push hook

Automatically fix failing tests before every push:

```bash
# .git/hooks/pre-push
#!/bin/sh
testfix --once --provider ollama pytest
```

## LLM Providers

```bash
# Claude (default) — best quality
export ANTHROPIC_API_KEY=sk-ant-...
testfix pytest

# OpenAI
export OPENAI_API_KEY=sk-...
testfix --provider openai pytest

# Local ollama (free, private, no API key)
# Install: https://ollama.ai then: ollama pull qwen2.5:7b
testfix --provider ollama pytest
```

## How it works

1. **Run** your test command and capture output
2. **Parse** failures: test names, file paths, tracebacks
3. **Find** the source files that need fixing (not the test files)
4. **Ask AI** to fix the source code based on the failure context
5. **Apply** patches (with `.testfix.bak` backups)
6. **Repeat** until all tests pass or max tries reached

## Watch Mode (v0.2+)

Automatically re-run and fix tests as you edit source files:

```bash
testfix --watch pytest
```

Polls for file changes every 2 seconds, re-runs on modification, and applies AI fixes until green. Press `Ctrl+C` to stop.

## GitHub Actions

Use [testfix-action](https://github.com/faw21/testfix-action) for a zero-config CI integration:

```yaml
- uses: faw21/testfix-action@v1
  with:
    anthropic_api_key: ${{ secrets.ANTHROPIC_API_KEY }}
    test_command: pytest
```

Or use the CLI directly:

```yaml
- name: Fix and test
  run: |
    pip install testfix-ai
    testfix --provider openai --max-tries 3 pytest
  env:
    OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
```

## Full developer workflow

Combine with the rest of the ecosystem for end-to-end AI-assisted development:

```bash
# 1. Morning standup
standup-ai --yesterday

# 2. Review your code before committing
critiq --staged

# 3. Fix failing tests automatically
testfix pytest

# 4. Generate commit message
gpr --commit

# 5. Generate PR description
gpr

# 6. Pack context for AI code review
gitbrief --changed-only

# 7. Generate changelog on release
changelog-ai --since v1.0.0
```

Install the full suite:
```bash
pip install standup-ai critiq testfix gpr gitbrief changelog-ai
```

## Related tools

- [testfix-action](https://github.com/faw21/testfix-action) — this tool as a GitHub Action
- [critiq](https://github.com/faw21/critiq) — AI code reviewer (catches issues before they become failing tests)
- [difftests](https://github.com/faw21/difftests) — AI test generator (generates tests for your diffs)
- [mergefix](https://github.com/faw21/mergefix) — AI merge conflict resolver
- [gpr](https://github.com/faw21/gpr) — AI PR description generator
- [standup-ai](https://github.com/faw21/standup-ai) — AI daily standup generator
- [changelog-ai](https://github.com/faw21/changelog-ai) — AI changelog generator
- [prcat](https://github.com/faw21/prcat) — AI PR reviewer for teammate PRs

## License

Business Source License 1.1 — free for individuals and non-commercial use.
Commercial use requires a license after the Change Date (2028-01-01), at which point this project converts to Apache 2.0.
