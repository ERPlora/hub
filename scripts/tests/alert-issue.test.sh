#!/usr/bin/env bash
# Tests for scripts/ci/alert-issue.sh — the shared "open or refresh an idempotent alert
# issue" lookup used by every CI alert step (test-hub.yml, image-freshness.yml,
# test-hub-modules.yml, and test-web.yml).
#
# Regression test for ERPlora/hub#1246: `test-hub.yml` and `image-freshness.yml` matched the
# existing open issue with `gh issue list --search '"..." in:title'`. `--search` reads GitHub's
# search INDEX, which lags behind reality — it returned ZERO with open issues on 2026-08-16, and
# hit on 2026-08-26 (intermittent, which is worse). Two failures minutes apart (a push to
# `develop` then one to `main`, two releases back to back) could each miss the other's issue and
# open TWO — the alert stops being idempotent exactly when there is the most noise.
# `test-hub-modules.yml` already fixed this for itself (hub#1239) by listing with the REST API
# and filtering the title LOCALLY; this script is that fix, extracted once so every alert step
# shares ONE implementation instead of three/four copies that can drift apart again.
#
# Every case here stubs `gh` (a fake binary put first on PATH) so the suite never touches the
# network: the stub answers `gh issue list` from a fixture and RECORDS every `gh issue comment`/
# `gh issue create` call so the assertions can tell which one happened, and to WHICH issue.
set -uo pipefail

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
SCRIPT="$script_dir/../ci/alert-issue.sh"

pass=0
fail=0
ok()  { printf '  \033[32m✓\033[0m %s\n' "$1"; pass=$((pass + 1)); }
bad() { printf '  \033[31m✗\033[0m %s\n     %s\n' "$1" "$2"; fail=$((fail + 1)); }

if [ ! -f "$SCRIPT" ]; then
    printf 'FAIL: no such script: %s\n' "$SCRIPT" >&2
    exit 1
fi

if ! command -v jq >/dev/null 2>&1; then
    printf 'FAIL: jq is required (both by the script and by this test)\n' >&2
    exit 1
fi

# ── Fake `gh`, put first on PATH ──────────────────────────────────────────────
# `gh issue list ... --json number,title --jq <program>` answers from $STUB_DIR/issues.json —
# a fixture the test controls per case — filtered through the SAME `<program>` the real
# `alert-issue.sh` built, using the real `jq` binary to emulate gh's own (vendored, jq-
# compatible) `--jq` engine. `jq` here is a TEST-ONLY tool, never a production dependency —
# `alert-issue.sh` itself only ever shells out to `gh` (see its own comment on why: a bare
# `ci-runner-1` has no standalone `jq`). `gh issue comment` and `gh issue create` append one
# line per call to $STUB_DIR/calls.log instead of doing anything: the assertions read that
# log. Any OTHER `gh` invocation (in particular `gh issue list --search ...`) is a hard
# failure, so a regression that brings `--search` back inside the script itself is caught
# here too, not only by the grep-based contract check below.
make_stub_dir() {
    local dir
    dir=$(mktemp -d)
    printf '[]\n' > "$dir/issues.json"
    : > "$dir/calls.log"
    cat > "$dir/gh" <<'STUB'
#!/usr/bin/env bash
set -uo pipefail
log="$STUB_DIR/calls.log"
case "$1 $2" in
    "issue list")
        jq_program=""
        prev=""
        for a in "$@"; do
            if [ "$a" = "--search" ]; then
                echo "STUB: gh issue list must never be called with --search (hub#1246)" >&2
                exit 9
            fi
            if [ "$prev" = "--jq" ]; then
                jq_program="$a"
            fi
            prev="$a"
        done
        if [ -n "$jq_program" ]; then
            jq -r "$jq_program" "$STUB_DIR/issues.json"
        else
            cat "$STUB_DIR/issues.json"
        fi
        ;;
    "issue comment" | "issue create" | "issue close")
        printf '%s\n' "$*" >> "$log"
        if [ "$1 $2" = "issue create" ]; then
            # The new issue now EXISTS: a later `gh issue list` sees it as #9999. With
            # $STUB_DIR/race present, a twin job opened the same alert a moment before (#9000).
            title=""
            prev=""
            for a in "$@"; do
                [ "$prev" = "--title" ] && title="$a"
                prev="$a"
            done
            if [ -e "$STUB_DIR/race" ]; then
                jq --arg t "$title" '. + [{"number": 9000, "title": $t}]' "$STUB_DIR/issues.json" \
                    > "$STUB_DIR/issues.tmp" && mv "$STUB_DIR/issues.tmp" "$STUB_DIR/issues.json"
            fi
            jq --arg t "$title" '. + [{"number": 9999, "title": $t}]' "$STUB_DIR/issues.json" \
                > "$STUB_DIR/issues.tmp" && mv "$STUB_DIR/issues.tmp" "$STUB_DIR/issues.json"
            echo "https://github.com/ERPlora/hub/issues/9999"
        fi
        ;;
    *)
        echo "STUB: unexpected gh invocation: $*" >&2
        exit 9
        ;;
esac
STUB
    chmod +x "$dir/gh"
    echo "$dir"
}

run_script() {   # STUB_DIR is set (and exported, see below) by the caller before this runs
    PATH="$STUB_DIR:$PATH" "$SCRIPT" >"$OUT" 2>&1
    echo $?
}

echo "scripts/ci/alert-issue.sh"

# ── 1 · An open issue with a matching title → comment, never a new issue ─────────────────────
STUB_DIR=$(make_stub_dir); export STUB_DIR
OUT="$STUB_DIR/out"
cat > "$STUB_DIR/issues.json" <<'JSON'
[{"number": 42, "title": "main HEAD has no image in GHCR"}]
JSON
code=$(REPO=ERPlora/hub TITLE="main HEAD has no image in GHCR" MATCH=exact BODY="stale" run_script)
errs=""
[ "$code" = 0 ] || errs="$errs exit=$code"
grep -q '^issue comment 42 ' "$STUB_DIR/calls.log" || errs="$errs no-comment-on-42"
grep -q '^issue create' "$STUB_DIR/calls.log" && errs="$errs unexpectedly-created-a-new-issue"
[ -z "$errs" ] \
    && ok "an open issue with the exact title gets a comment, not a new issue" \
    || bad "an open issue with the exact title gets a comment, not a new issue" "$errs out=$(cat "$OUT")"

# ── 2 · No matching open issue → create one, with the label ─────────────────────────────────
STUB_DIR=$(make_stub_dir); export STUB_DIR
OUT="$STUB_DIR/out"
printf '[]\n' > "$STUB_DIR/issues.json"
code=$(REPO=ERPlora/hub TITLE="main HEAD has no image in GHCR" MATCH=exact BODY="stale" LABEL="area:ci-cd" run_script)
errs=""
[ "$code" = 0 ] || errs="$errs exit=$code"
grep -q '^issue create' "$STUB_DIR/calls.log" || errs="$errs did-not-create"
grep -q '\-\-label area:ci-cd' "$STUB_DIR/calls.log" || errs="$errs create-call-is-missing---label-area:ci-cd"
grep -q '^issue comment' "$STUB_DIR/calls.log" && errs="$errs unexpectedly-commented"
[ -z "$errs" ] \
    && ok "no open match creates a new issue carrying the label" \
    || bad "no open match creates a new issue carrying the label" "$errs out=$(cat "$OUT")"

# ── 3 · A CLOSED issue with the same title never matches → a new one is opened ──────────────
#    `gh issue list --state open` already excludes it server-side; the fixture models that: the
#    matching issue simply is not among the ones `--state open` would ever hand back. This is
#    what proves the script does not go hunting through closed issues on its own.
STUB_DIR=$(make_stub_dir); export STUB_DIR
OUT="$STUB_DIR/out"
printf '[]\n' > "$STUB_DIR/issues.json"   # the closed twin is, by definition, not in this list
code=$(REPO=ERPlora/hub TITLE="main HEAD has no image in GHCR" MATCH=exact BODY="stale" LABEL="area:ci-cd" run_script)
errs=""
[ "$code" = 0 ] || errs="$errs exit=$code"
grep -q '^issue create' "$STUB_DIR/calls.log" || errs="$errs did-not-reopen-as-a-new-issue"
[ -z "$errs" ] \
    && ok "a closed same-title issue does not satisfy the match — a new one opens" \
    || bad "a closed same-title issue does not satisfy the match — a new one opens" "$errs out=$(cat "$OUT")"

# ── 4 · Prefix match — test-hub.yml's title carries a dynamic `: <subject>` suffix ──────────
#    A colon reaching `--search` would be read as GitHub search syntax (part of the original
#    bug); here it only has to survive a `startswith` in jq, which does not care about colons.
STUB_DIR=$(make_stub_dir); export STUB_DIR
OUT="$STUB_DIR/out"
cat > "$STUB_DIR/issues.json" <<'JSON'
[{"number": 7, "title": "develop is broken after a merge: fix(billing): retry webhook"}]
JSON
code=$(REPO=ERPlora/hub TITLE="develop is broken after a merge: feat(auth): rotate tokens" \
       MATCH=prefix MATCH_VALUE="develop is broken after a merge" BODY="stale" run_script)
errs=""
[ "$code" = 0 ] || errs="$errs exit=$code"
grep -q '^issue comment 7 ' "$STUB_DIR/calls.log" || errs="$errs no-comment-on-7"
[ -z "$errs" ] \
    && ok "prefix match finds the open issue despite a different dynamic suffix" \
    || bad "prefix match finds the open issue despite a different dynamic suffix" "$errs out=$(cat "$OUT")"

# ── 5 · REPO reaches the comment call as `--repo` ────────────────────────────────────────────
#    A script that hardcoded a repo (or dropped the flag) would still pass every other case
#    here, since the stub always answers regardless of which --repo it was given. This is the
#    one case that actually reads the recorded call args instead of only their first token.
STUB_DIR=$(make_stub_dir); export STUB_DIR
OUT="$STUB_DIR/out"
cat > "$STUB_DIR/issues.json" <<'JSON'
[{"number": 1, "title": "main HEAD has no image in GHCR"}]
JSON
code=$(REPO=ERPlora/hub TITLE="main HEAD has no image in GHCR" MATCH=exact BODY="stale" run_script)
errs=""
[ "$code" = 0 ] || errs="$errs exit=$code"
grep -q '^issue comment 1 .*--repo ERPlora/hub' "$STUB_DIR/calls.log" || errs="$errs comment-call-is-missing---repo-ERPlora/hub"
[ -z "$errs" ] \
    && ok "the --repo flag reaches the comment call" \
    || bad "the --repo flag reaches the comment call" "$errs calls=$(cat "$STUB_DIR/calls.log") out=$(cat "$OUT")"

# ── 6 · No BODY (env nor stdin) is a loud, early error — never a silent empty issue ─────────
STUB_DIR=$(make_stub_dir); export STUB_DIR
OUT="$STUB_DIR/out"
printf '[]\n' > "$STUB_DIR/issues.json"
code=$(REPO=ERPlora/hub TITLE="x" MATCH=exact run_script </dev/null)
errs=""
[ "$code" != 0 ] || errs="$errs exit=0-should-have-failed"
grep -qi 'BODY' "$OUT" || errs="$errs error-does-not-mention-BODY: $(cat "$OUT")"
grep -q '^issue create' "$STUB_DIR/calls.log" && errs="$errs created-an-issue-anyway"
[ -z "$errs" ] \
    && ok "a missing BODY fails loudly instead of opening an empty issue" \
    || bad "a missing BODY fails loudly instead of opening an empty issue" "$errs"

# ── 7 · A title with a quote/backslash does not break the hand-built jq program ─────────────
#    `gh --jq` takes one flat expression with no `--arg`, so MATCH_VALUE is escaped by hand
#    into a jq string literal. An unescaped `"` would end the string early and turn the rest
#    into a syntax error (gh would exit non-zero, never a silent no-match); an unescaped `\`
#    would combine with the next character. Both must still find the open issue.
STUB_DIR=$(make_stub_dir); export STUB_DIR
OUT="$STUB_DIR/out"
cat > "$STUB_DIR/issues.json" <<'JSON'
[{"number": 55, "title": "build \"release\\prod\" is not publishing"}]
JSON
code=$(REPO=ERPlora/hub TITLE='build "release\prod" is not publishing' MATCH=exact BODY="stale" run_script)
errs=""
[ "$code" = 0 ] || errs="$errs exit=$code out=$(cat "$OUT")"
grep -q '^issue comment 55 ' "$STUB_DIR/calls.log" || errs="$errs no-comment-on-55"
[ -z "$errs" ] \
    && ok "a title with a quote and a backslash still matches (jq-escaped correctly)" \
    || bad "a title with a quote and a backslash still matches (jq-escaped correctly)" "$errs"

# ── 8 · Two jobs that raced to open the SAME alert leave ONE open (pm#655) ─────────────────
#    `test-hub-modules.yml` runs the battery alert in two matrix parts at once (`batteries 1/2`
#    and `batteries 2/2`): when both fail with no alert open, both list (nothing), both create.
#    After creating, the script lists again; if an older twin is open, the alert goes there as a
#    comment and its own issue is closed as a duplicate — whichever job loses the race.
STUB_DIR=$(make_stub_dir); export STUB_DIR
OUT="$STUB_DIR/out"
printf '[]\n' > "$STUB_DIR/issues.json"
touch "$STUB_DIR/race"
code=$(REPO=ERPlora/hub TITLE="Module batteries fail" MATCH=exact BODY="shard 2/2 red" run_script)
errs=""
[ "$code" = 0 ] || errs="$errs exit=$code"
grep -q '^issue close 9999 ' "$STUB_DIR/calls.log" || errs="$errs did-not-close-its-own-duplicate-9999"
grep -q '^issue comment 9000 ' "$STUB_DIR/calls.log" || errs="$errs alert-did-not-reach-the-older-twin-9000"
grep -q '^issue close 9000' "$STUB_DIR/calls.log" && errs="$errs closed-the-SURVIVOR"
[ -z "$errs" ] \
    && ok "a job that lost the race closes its own duplicate and comments on the older twin" \
    || bad "a job that lost the race closes its own duplicate and comments on the older twin" "$errs out=$(cat "$OUT") calls=$(cat "$STUB_DIR/calls.log")"

# … and the job that WON (its issue is the oldest) keeps it: no close, no extra comment.
STUB_DIR=$(make_stub_dir); export STUB_DIR
OUT="$STUB_DIR/out"
printf '[]\n' > "$STUB_DIR/issues.json"
code=$(REPO=ERPlora/hub TITLE="Module batteries fail" MATCH=exact BODY="shard 1/2 red" run_script)
errs=""
[ "$code" = 0 ] || errs="$errs exit=$code"
grep -q '^issue close' "$STUB_DIR/calls.log" && errs="$errs closed-its-own-surviving-issue"
grep -q '^issue comment' "$STUB_DIR/calls.log" && errs="$errs commented-on-its-own-new-issue"
[ -z "$errs" ] \
    && ok "the job whose issue is the oldest keeps it open" \
    || bad "the job whose issue is the oldest keeps it open" "$errs calls=$(cat "$STUB_DIR/calls.log")"

echo
if [ "$fail" -eq 0 ]; then
    echo "PASS: $pass alert-issue.sh case(s)"
    exit 0
else
    echo "FAIL: $fail of $((pass + fail)) alert-issue.sh case(s)"
    exit 1
fi
