# testfix

**AI-powered failing test auto-fixer.** Run your tests, let the AI fix the failures, repeat until green — all from one command.

```bash
pip install testfix
testfix pytest          # run, fix, retry up to 5× until tests pass
```

> Supports pytest · jest · vitest · go test · cargo test

---

## Why testfix?

You've been there: you write a feature, run tests, and see 5 failures. Fixing each one manually means reading tracebacks, understanding what broke, writing a fix, re-running — and repeating. testfix automates that loop.

Unlike GitHub Copilot (needs IDE) or aider (interactive session), testfix is a **pure CLI tool**: non-interactive, pipeable, pre-push hook-ready.

---

## Installation

```bash
pip install testfix
```

Requires Python 3.9+. No configuration needed — just install and run.

### API Keys

Set one of these (or use Ollama for free local inference):

```bash
export ANTHROPIC_API_KEY=sk-ant-...   # Claude (default)
export OPENAI_API_KEY=sk-...          # OpenAI
# or use --provider ollama (no key needed, runs locally)
```

---

## Quick Start

```bash
# Run pytest and fix failures (up to 5 tries)
testfix pytest

# Fix a specific test file
testfix pytest tests/test_auth.py

# Run once: test → fix → test again
testfix --once pytest

# Preview fixes without applying them
testfix --dry-run pytest

# Use OpenAI instead of Claude
testfix --provider openai pytest

# Use local Ollama (free, no API key)
testfix --provider ollama pytest

# Use Jest
testfix npm test

# Use Go test
testfix go test ./...

# Focus on a specific source file
testfix --file src/auth.py pytest
```

---

## How it works

```
testfix pytest
│
├─ Attempt 1/5
│   ├─ Run: pytest
│   ├─ 3 failing tests found
│   ├─ 🤖 Asking Claude to fix 3 failure(s)…
│   ├─ Generated 1 file fix(es)
│   │   └─ src/auth.py  (diff shown)
│   └─ ✔ Applied fix (backup: .testfix.bak)
│
├─ Attempt 2/5
│   ├─ Run: pytest
│   └─ ✅ All tests pass!
│
└─ Exit 0
```

1. **Run** your tests with the command you provide
2. **Parse** failures: extracts test name, location, error, traceback
3. **Collect** relevant source files (from tracebacks + heuristics)
4. **Ask** the AI to fix the source code — never modifies test files
5. **Apply** the fix (with `.testfix.bak` backup)
6. **Repeat** until tests pass or `--max-tries` is reached

---

## Options

```
testfix [OPTIONS] TEST_COMMAND...

Options:
  --max-tries N      Max fix-and-retry iterations (default: 5)
  --once             Run once: test → fix → test again (--max-tries 2)
  --dry-run          Show diffs but don't apply fixes
  --provider NAME    LLM provider: claude, openai, ollama (default: claude)
  --model NAME       Model override (e.g. claude-sonnet-4-5, gpt-4o)
  --file PATH        Focus fixes on this source file
  -v, --verbose      Show full test runner stderr
  --version          Show version and exit
```

---

## Pre-push hook

Add to `.git/hooks/pre-push`:

```bash
#!/bin/bash
testfix --once --provider ollama pytest
```

This runs tests, lets AI fix any failures, and blocks the push if tests are still failing.

---

## CI / GitHub Actions

```yaml
- name: Run and auto-fix tests
  run: testfix pytest
  env:
    ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
```

Or use `--dry-run` in CI to just report what would be fixed without changing files:

```yaml
- name: Check if AI can fix test failures
  run: testfix --dry-run pytest || echo "Tests failing (see diff above)"
```

---

## Supported test frameworks

| Framework | Command example |
|-----------|----------------|
| **pytest** | `testfix pytest` |
| **jest** | `testfix npx jest` |
| **vitest** | `testfix npx vitest` |
| **go test** | `testfix go test ./...` |
| **cargo test** | `testfix cargo test` |
| **rspec** | `testfix bundle exec rspec` |
| **any** | `testfix <your test command>` |

---

## Ecosystem

testfix is part of a suite of AI-powered developer CLI tools:

| Tool | Purpose |
|------|---------|
| **[critiq](https://github.com/faw21/critiq)** | AI code reviewer — catch issues before you push |
| **[testfix](https://github.com/faw21/testfix)** | AI test fixer — automatically fix failing tests |
| **[difftests](https://github.com/faw21/difftests)** | AI test generator — write tests for your diffs |
| **[gpr](https://github.com/faw21/gpr)** | AI PR description + commit message generator |
| **[gitbrief](https://github.com/faw21/gitbrief)** | Pack your codebase into LLM context |
| **[standup-ai](https://github.com/faw21/standup-ai)** | AI daily standup generator |
| **[changelog-ai](https://github.com/faw21/changelog-ai)** | AI CHANGELOG generator |
| **[prcat](https://github.com/faw21/prcat)** | AI PR reviewer for incoming PRs |
| **[chronicle](https://github.com/faw21/chronicle)** | Turn git history into stories |

---

## License

Business Source License 1.1 — free for non-commercial use. See [LICENSE](LICENSE).
