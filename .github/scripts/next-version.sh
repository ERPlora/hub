#!/usr/bin/env bash
# Prints the next release tag of a project (PLAN-AWS §6): CalVer per project,
#   <project>-vYYYY.MM.DD.N, with N = 1, 2, 3… within that day for that project.
# Pure: the existing tags come on stdin (one per line, any project, any order);
# it reads no git state and creates nothing.
#   git tag --list 'hub-v*' | bash .github/scripts/next-version.sh hub "$(date -u +%Y.%m.%d)"
set -euo pipefail

project="${1:-}" day="${2:-}"

case "$project" in
  hub | saas) ;;
  *)
    echo "unknown project '$project' (hub | saas)" >&2
    exit 1
    ;;
esac
if ! [[ "$day" =~ ^[0-9]{4}\.[0-9]{2}\.[0-9]{2}$ ]]; then
  echo "invalid day '$day', expected YYYY.MM.DD" >&2
  exit 1
fi

# Highest N among this project's tags of that day; anything else is ignored.
prefix="$project-v$day."
last=0
while IFS= read -r tag || [ -n "$tag" ]; do
  n="${tag#"$prefix"}"
  if [ "$n" != "$tag" ] && [[ "$n" =~ ^[0-9]+$ ]] && [ "$((10#$n))" -gt "$last" ]; then
    last="$((10#$n))"
  fi
done

echo "$prefix$((last + 1))"
