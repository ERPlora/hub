#!/usr/bin/env bash
# Tests that the Dockerfile fetches nothing by URL. BuildKit requests every `ADD <url>` again on each build to
# compute its cache key, even when no layer changed, so a slow website fails a build of unchanged code: the files
# the image needs live in the repo and are copied.
#   bash .github/scripts/dockerfile.test.sh [Dockerfile]
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
dockerfile="${1:-$here/../../Dockerfile}"
failures=0

check() {
  local name="$1"
  shift
  if "$@"; then
    echo "ok   - $name"
  else
    echo "FAIL - $name"
    failures=$((failures + 1))
  fi
}

# remote_adds <file>: each ADD instruction whose source is a URL or a git remote, continuation lines joined.
remote_adds() {
  awk '
    { line = line $0 }
    /\\$/ { sub(/\\$/, "", line); next }
    { split(line, word, " "); if (toupper(word[1]) == "ADD" && line ~ /:\/\/|git@/) print line; line = "" }
  ' "$1"
}

no_remote_add() { [[ -z $(remote_adds "$1") ]]; }
has_remote_add() { ! no_remote_add "$1"; }

fixtures="$(mktemp -d)"
trap 'rm -rf "$fixtures"' EXIT
fixture() { printf '%s\n' "$2" > "$fixtures/$1"; echo "$fixtures/$1"; }

[[ -f $dockerfile ]] || { echo "FAIL - $dockerfile not found"; exit 1; }
check "the Dockerfile adds nothing from a URL" no_remote_add "$dockerfile"
remote_adds "$dockerfile" | sed 's/^/       found: /'

check "an ADD of an https URL is caught" \
  has_remote_add "$(fixture https 'ADD --chmod=644 https://example.org/key.asc /usr/share/keyrings/key.asc')"
check "an ADD of an http URL in lower case is caught" has_remote_add "$(fixture lower 'add http://example.org/a /a')"
check "an ADD whose URL is on a continuation line is caught" \
  has_remote_add "$(fixture continued $'ADD --chmod=644 \\\n    https://example.org/a /a')"
check "an ADD in JSON form is caught" has_remote_add "$(fixture json 'ADD ["https://example.org/a", "/a"]')"
check "an ADD of a git remote is caught" has_remote_add "$(fixture git 'ADD git@github.com:example/repo.git /src')"
check "a COPY of a file of the repo passes" no_remote_add "$(fixture copy 'COPY --chmod=644 docker/key.asc /k.asc')"
check "an ADD of a local archive passes" no_remote_add "$(fixture local 'ADD vendor.tar.gz /opt/')"
check "a comment that names an ADD of a URL passes" no_remote_add "$(fixture comment '# ADD https://example.org/a /a')"
check "a RUN that mentions a URL passes" \
  no_remote_add "$(fixture run 'RUN echo "deb https://apt.postgresql.org/pub/repos/apt main" > /x')"

if [[ $failures -gt 0 ]]; then
  echo "$failures failure(s)"
  exit 1
fi
echo "all passed"
