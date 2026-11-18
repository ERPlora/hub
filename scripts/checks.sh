#!/usr/bin/env bash
# The checks a change passes before it is pushed; .githooks/pre-push runs `fast` on every pushed commit.
#   fast: the guardrail tests of file size, ruff, the import contracts and cognitive complexity, the lists that only
#         shrink included. Seconds, without the network or a database.
# Without DEBUG the settings demand a SECRET_KEY: these checks read no secret, and a fresh worktree has no .env.
set -u
cd "$(dirname "$0")/.." || exit 1
case "${1:-}" in
  fast) ;;
  *)
    echo "usage: scripts/checks.sh fast" >&2
    exit 2
    ;;
esac
DEBUG=True exec uv run --no-sync pytest -q --tb=short \
  tests/test_guardrails_size.py \
  tests/test_guardrails_lint.py \
  tests/test_guardrails_ruff.py \
  tests/test_guardrails_complexity.py \
  tests/test_guardrails_imports.py
