#!/usr/bin/env bash
# The checks a change passes before it is pushed; .githooks/pre-push runs `fast` on every pushed commit.
#   fast [<since>]: the guardrail tests of file size, ruff, the import contracts and cognitive complexity, and then
#         ESLint, the typecheck, Vitest and pytest on what the change touches since <since> (scripts/checks.py).
# Without DEBUG the settings demand a SECRET_KEY: these checks read no secret, and a fresh worktree has no .env.
set -u
cd "$(dirname "$0")/.." || exit 1
DEBUG=True exec uv run --no-sync python scripts/checks.py "$@"
