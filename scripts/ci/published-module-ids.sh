#!/usr/bin/env bash
# Print the ids of the PUBLISHED modules, one per line, sorted — the list
# `test-hub-modules.yml` hands to `scripts/materialize-published-modules.sh --modules`.
#
#   scripts/ci/published-module-ids.sh [--org ERPlora] [--branch main]
#
# A published module is a PUBLIC, non-archived repo of the org with a `module.json` on its
# publishing branch. One GraphQL call answers that for the whole org (`object(expression:)` is
# null when the file is not there), so there is no per-repo 404 to tell apart from a real error.
#
# Exit codes: 0 = the ids are on stdout · 2 = environment (no `gh`, `gh` failed, an answer that is
# not the expected JSON, or an org with no published module at all). Never an empty list with 0:
# downstream that would materialise nothing and blame the clone for it.
#
# Why this replaced the deploy-key bundle as the id source (pm#655): the bundle had to be kept in
# step with the org by hand, and it was not — `attendance` was born without a key and every run of
# the workflow died on «the catalogue is INCOMPLETE» for a day and a half, while the retired and
# archived `invoice_series` was still being cloned. With the module repos public since 2026-10-08,
# the org is the list. Cases in `scripts/tests/published-module-ids.test.sh`.

set -uo pipefail

org=ERPlora
branch=main

env_error() { printf 'published-module-ids: %s\n' "$1" >&2; exit 2; }

while [ $# -gt 0 ]; do
    case "$1" in
        --org) org="${2:-}"; shift 2 ;;
        --branch) branch="${2:-}"; shift 2 ;;
        -h | --help) sed -n '2,20p' "$0"; exit 0 ;;
        *) env_error "unknown argument: $1" ;;
    esac
done
[ -n "$org" ] || env_error '--org must not be empty'
[ -n "$branch" ] || env_error '--branch must not be empty'

command -v gh > /dev/null 2>&1 || env_error "no \`gh\` on PATH: it is how the org is asked for its modules"
command -v python3 > /dev/null 2>&1 || env_error 'no python3 on PATH: it parses the answer'

query='query($endCursor: String) {
  organization(login: "'"$org"'") {
    repositories(first: 100, after: $endCursor, privacy: PUBLIC) {
      pageInfo { hasNextPage endCursor }
      nodes { name isArchived object(expression: "'"$branch"':module.json") { __typename } }
    }
  }
}'

answer=$(gh api graphql --paginate --slurp -f query="$query") \
    || env_error "\`gh api graphql\` failed listing the repos of $org (its error is above)"

printf '%s' "$answer" | python3 -c '
import json
import re
import sys

ID = re.compile(r"^[a-z][a-z0-9_]*$")

def die(msg):
    print(f"published-module-ids: {msg}", file=sys.stderr)
    sys.exit(2)

try:
    pages = json.load(sys.stdin)
except ValueError as err:
    die(f"the answer from GitHub is not JSON ({err})")
if not isinstance(pages, list):
    pages = [pages]

ids = []
for page in pages:
    if not isinstance(page, dict):
        die(f"unexpected page in the answer: {page!r:.200}")
    if page.get("errors"):
        die("GitHub answered with errors: " + "; ".join(e.get("message", str(e)) for e in page["errors"]))
    try:
        nodes = page["data"]["organization"]["repositories"]["nodes"]
    except (KeyError, TypeError):
        die(f"the answer does not carry organization.repositories.nodes: {page!r:.200}")
    for repo in nodes:
        if repo.get("isArchived") or not repo.get("object"):
            continue
        name = repo.get("name", "")
        if not ID.match(name):
            print(f"published-module-ids: ignoring {name!r}: it has a module.json but is not a module id", file=sys.stderr)
            continue
        ids.append(name)

if not ids:
    die(f"no published module found (public, not archived, with module.json on {sys.argv[1]!r})")
print("\n".join(sorted(set(ids))))
' "$branch"
