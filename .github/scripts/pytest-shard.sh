#!/usr/bin/env bash
# Runs one shard of the Hub's pytest suite, the share of one job of test.yml's python matrix (hub#1185):
#   bash .github/scripts/pytest-shard.sh <index> <total> <warn-minutes> [pytest arguments...]
# <index> and <total> are the ones GitHub gives the job (strategy.job-index, from 0, and strategy.job-total),
# so the jobs of the matrix, whatever its size, run the groups 1 to <total> of pytest-split and cover the
# whole suite, each test in exactly one. The split is least_duration: with no stored durations it deals the
# tests out one by one, in name order, so the slow kinds (transaction=True, the sweeps over every app) are
# spread over every shard instead of landing in the same contiguous chunk, which is what the default does.
# It ends with pytest's own exit code, and when pytest took longer than <warn-minutes> it writes a warning
# annotation: the job's timeout is getting near and the matrix needs another shard before a slow runner of
# GitHub cuts the job, as it cut the single job of before at 30 minutes without a failing test.
set -euo pipefail

fail() {
  echo "::error::$*" >&2
  exit 2
}

if [ "$#" -lt 3 ]; then
  fail "usage: pytest-shard.sh <index> <total> <warn-minutes> [pytest arguments...]"
fi
index="$1" total="$2" warn_minutes="$3"
shift 3
for value in "$index" "$total" "$warn_minutes"; do
  case "$value" in
    '' | *[!0-9]*) fail "index, total and warn-minutes must be whole numbers, got: $index $total $warn_minutes" ;;
  esac
done
if [ "$total" -lt 1 ] || [ "$index" -ge "$total" ]; then
  fail "the index must be from 0 to total - 1, got index $index of total $total"
fi
if [ "$warn_minutes" -lt 1 ]; then
  fail "warn-minutes must be at least 1, got $warn_minutes"
fi

group=$((index + 1))
started="$(date +%s)"
status=0
uv run --locked pytest --splits "$total" --group "$group" --splitting-algorithm least_duration "$@" || status=$?
took=$(($(date +%s) - started))

echo "shard $group of $total: pytest took $((took / 60)) min $((took % 60)) s"
if [ "$took" -gt $((warn_minutes * 60)) ]; then
  echo "::warning title=pytest near the job's timeout::shard $group of $total took longer than $warn_minutes min:" \
    "add a shard to the python job's matrix (.github/workflows/test.yml) before a slow runner cuts the job"
fi
exit "$status"
