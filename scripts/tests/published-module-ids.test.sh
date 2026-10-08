#!/usr/bin/env bash
# Contract tests for scripts/ci/published-module-ids.sh — where `test-hub-modules.yml` gets the
# list of PUBLISHED modules it materialises (pm#655).
#
# Why the source moved. Until pm#655 the ids came out of the `MODULES_DEPLOY_KEYS` bundle (one
# read-only deploy key per module repo, hub#1216): the keys were needed to clone private repos,
# and the bundle was "the one source that cannot fall short". It fell short. `attendance` was born
# on 2026-10-06 without a key in the bundle, its battery was declared in
# `scripts/ci/module-hub-batteries.txt`, and from 2026-10-07 08:19Z every run of the workflow died
# in ~1 minute on «the catalogue is INCOMPLETE» — 40 runs in a row, the module e2e verifying
# nothing. The bundle also still carried `invoice_series`, a module retired and archived weeks ago.
# Rebuilding it takes the private half of every key, which lives nowhere but inside the secret.
#
# Since 2026-10-08 the module repos are PUBLIC, so no key is needed to clone them, and the org
# itself is the list: a public, non-archived repo with a `module.json` on its publishing branch IS
# a published module. A new module enters on its first push; a retired one leaves when archived.
#
# Hermetic: `gh` is a stub that replays a canned GraphQL answer and records how it was called.

set -uo pipefail

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
script="$script_dir/../ci/published-module-ids.sh"
tmp_dir=$(mktemp -d "${TMPDIR:-/tmp}/erplora-published-module-ids-test.XXXXXX")
trap 'rm -rf "$tmp_dir"' EXIT HUP INT TERM

passed=0
out=""
err=""
rc=0

fail() {
    printf 'FAIL: %s\n' "$1" >&2
    printf '  exit was: %s\n' "$rc" >&2
    [ -n "$out" ] && printf '  stdout was:\n%s\n' "$(printf '%s\n' "$out" | sed 's/^/    /')" >&2
    [ -n "$err" ] && printf '  stderr was:\n%s\n' "$(printf '%s\n' "$err" | sed 's/^/    /')" >&2
    exit 1
}

ok() { passed=$((passed + 1)); }

[ -f "$script" ] || fail "no such script: $script"

fake_bin="$tmp_dir/bin"
mkdir -p "$fake_bin"
cat > "$fake_bin/gh" <<'GH'
#!/usr/bin/env bash
# Stub `gh`: records its argv (one per line) and replays $GH_STUB_OUT with exit $GH_STUB_RC.
printf '%s\n' "$@" > "$GH_ARGS_LOG"
[ -n "${GH_STUB_ERR:-}" ] && printf '%s\n' "$GH_STUB_ERR" >&2
[ -n "${GH_STUB_OUT:-}" ] && cat "$GH_STUB_OUT"
exit "${GH_STUB_RC:-0}"
GH
chmod +x "$fake_bin/gh"

run_ids() { # rest=extra args; env: GH_STUB_OUT, GH_STUB_RC, GH_STUB_ERR
    : > "$tmp_dir/gh-args.log"
    PATH="$fake_bin:$PATH" GH_ARGS_LOG="$tmp_dir/gh-args.log" \
        bash "$script" "$@" > "$tmp_dir/stdout" 2> "$tmp_dir/stderr"
    rc=$?
    out=$(cat "$tmp_dir/stdout")
    err=$(cat "$tmp_dir/stderr")
}

node() { # $1=name $2=archived(true|false) $3=has module.json(1|0)
    local obj=null
    [ "$3" = 1 ] && obj='{"__typename": "Blob"}'
    printf '{"name": "%s", "isArchived": %s, "object": %s}' "$1" "$2" "$obj"
}

page() { # $1=hasNextPage, rest = nodes
    local next=$1 joined=""
    shift
    for n in "$@"; do joined="${joined:+$joined, }$n"; done
    printf '{"data": {"organization": {"repositories": {"pageInfo": {"hasNextPage": %s, "endCursor": "c"}, "nodes": [%s]}}}}' \
        "$next" "$joined"
}

# Two pages, as `gh api graphql --paginate --slurp` hands them: a JSON ARRAY of whole responses.
two_pages="$tmp_dir/two-pages.json"
{
    printf '['
    page true \
        "$(node sales false 1)" \
        "$(node hub false 0)" \
        "$(node invoice_series true 1)" \
        "$(node attendance false 1)"
    printf ', '
    page false \
        "$(node module-toolkit false 1)" \
        "$(node blueprints false 0)" \
        "$(node appointments false 1)"
    printf ']\n'
} > "$two_pages"

# ── 1 · The published modules, and only them, sorted, one per line ───────────────────────
GH_STUB_OUT="$two_pages" run_ids
[ "$rc" -eq 0 ] || fail "1: a well-formed answer must exit 0"
ok
expected=$(printf 'appointments\nattendance\nsales')
[ "$out" = "$expected" ] || fail "1: expected exactly the published modules, sorted"
ok
# Each exclusion, named, so a failure says which rule broke.
case "$out" in *invoice_series*) fail "1: an ARCHIVED repo (a retired module) is not published" ;; esac
case "$out" in *hub*|*blueprints*) fail "1: a repo without module.json on the branch is not a module" ;; esac
case "$out" in *module-toolkit*) fail "1: a repo name that is not a module id must be dropped" ;; esac
ok
# Regression test for ERPlora/hub#2035: a module born AFTER the hand-kept list (`attendance`,
# 2026-10-06, no deploy key in the bundle) is published the moment its repo is, with nobody
# editing anything — the org IS the list. The alert of hub#2035 fired 40 runs in a row on it.
case "$out" in *attendance*) ;; *) fail "1: hub#2035 — a module born after the key bundle (attendance) must be published without anyone editing a list" ;; esac
ok
grep -q 'module-toolkit' <<<"$err" \
    || fail "1: a dropped non-id repo carrying module.json must be NAMED on stderr, not vanish"
ok

# ── 2 · It asks GitHub the right question ────────────────────────────────────────────────
args=$(cat "$tmp_dir/gh-args.log")
grep -qx 'graphql' <<<"$args" || fail "2: expected \`gh api graphql\`, argv was: $args"
grep -qx -- '--paginate' <<<"$args" || fail "2: without --paginate the org is cut at 100 repos"
grep -qx -- '--slurp' <<<"$args" || fail "2: --slurp is what makes the pages one JSON array"
grep -q 'privacy: PUBLIC' <<<"$args" || fail "2: only PUBLIC repos are cloned without a key"
grep -q '"main:module.json"' <<<"$args" || fail "2: the module.json must be read on main by default"
grep -q 'login: "ERPlora"' <<<"$args" || fail "2: the org must default to ERPlora"
ok

GH_STUB_OUT="$two_pages" run_ids --org Acme --branch stable
args=$(cat "$tmp_dir/gh-args.log")
grep -q 'login: "Acme"' <<<"$args" || fail "2: --org is not honoured"
grep -q '"stable:module.json"' <<<"$args" || fail "2: --branch is not honoured"
ok

# ── 3 · Anything that is not a clean answer is an ENVIRONMENT error, never an empty list ──
# An empty stdout with exit 0 would materialise nothing, and the `--floor 25` downstream would
# then blame the clone. The failure has to say where it really happened.
GH_STUB_RC=1 GH_STUB_ERR='HTTP 502: Bad Gateway' run_ids
[ "$rc" -eq 2 ] || fail "3: a failing \`gh\` must exit 2, got $rc"
[ -z "$out" ] || fail "3: a failing \`gh\` must print no ids"
grep -q 'HTTP 502' <<<"$err" || fail "3: gh's own error must be passed through"
ok

printf 'not json\n' > "$tmp_dir/garbage.json"
GH_STUB_OUT="$tmp_dir/garbage.json" run_ids
[ "$rc" -eq 2 ] || fail "3: a malformed answer must exit 2, got $rc"
[ -z "$out" ] || fail "3: a malformed answer must print no ids"
ok

printf '[{"errors": [{"message": "Could not resolve to an Organization"}], "data": {"organization": null}}]\n' \
    > "$tmp_dir/errors.json"
GH_STUB_OUT="$tmp_dir/errors.json" run_ids
[ "$rc" -eq 2 ] || fail "3: a GraphQL error answer must exit 2, got $rc"
grep -q 'Could not resolve' <<<"$err" || fail "3: the GraphQL error must be named on stderr"
ok

{ printf '['; page false "$(node hub false 0)" "$(node old true 1)"; printf ']\n'; } > "$tmp_dir/none.json"
GH_STUB_OUT="$tmp_dir/none.json" run_ids
[ "$rc" -eq 2 ] || fail "3: an org with NO published module is not a pass, must exit 2, got $rc"
ok

# ── 4 · No `gh` at all is an environment error too ───────────────────────────────────────
no_gh="$tmp_dir/no-gh"
mkdir -p "$no_gh"
for tool in bash python3 dirname cat sort sed; do
    ln -sf "$(command -v "$tool")" "$no_gh/$tool"
done
PATH="$no_gh" bash "$script" > "$tmp_dir/stdout" 2> "$tmp_dir/stderr"
rc=$?
out=$(cat "$tmp_dir/stdout")
err=$(cat "$tmp_dir/stderr")
[ "$rc" -eq 2 ] || fail "4: without gh on PATH it must exit 2, got $rc"
ok

printf 'published-module-ids.test.sh: %s checks passed\n' "$passed"
