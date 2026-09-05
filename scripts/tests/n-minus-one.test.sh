#!/usr/bin/env bash
# Contract tests for scripts/ci/n-minus-one.sh — the guard that proves the LAST released
# binary (N-1) keeps serving against the schema the CURRENT branch (N) would leave behind
# (hub#1282, second half of hub#1163).
#
# What it protects, and why each case is here:
#
#   · No lint can see this class of break: a `RENAME`/`ALTER COLUMN … TYPE` is caught by the
#     migration-verb lint from hub#1163, but a new NOT NULL constraint, a dropped default, or
#     a column that silently changed shape breaks an N-1 QUERY without ever using a watched
#     verb. The only way to know is to actually RUN N-1 against N's schema.
#   · A guard nobody can break on purpose is a guard nobody trusts. Each case below breaks the
#     thing it protects and checks the script calls it out BY NAME (which tag, which query),
#     the same bar `image-tags.test.sh` sets for `image-tags.sh`.
#
# Every external dependency (git tags, docker, curl, building+booting the branch's own binary)
# is stubbed via the seams the script exposes — hermetic and offline, same pattern as
# `image-tags.test.sh`'s `IMAGE_TAGS_PUBLISHED_CMD`.

set -uo pipefail

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
script="$script_dir/../ci/n-minus-one.sh"
tmp_dir=$(mktemp -d "${TMPDIR:-/tmp}/erplora-n-minus-one-test.XXXXXX")
trap 'rm -rf "$tmp_dir"' EXIT HUP INT TERM

passed=0

fail() {
    printf 'FAIL: %s\n' "$1" >&2
    exit 1
}

# ── A real (tiny) git repo with v* tags, to prove tag resolution is a semver sort, not a ──────
# ── lexicographic one. Lexicographic sorting would rank "v1.1.9" ABOVE "v1.1.10" — the exact
# ── shape of tag history this repo already has (17 tags today, hub#1163) — and end up
# ── comparing N against the WRONG, older N-1.
make_tagged_repo() { # $1 = list of tags to create, in the order given
    repo="$tmp_dir/repo"
    rm -rf "$repo"
    git init -q "$repo"
    git -C "$repo" config user.email "ci@erplora.test"
    git -C "$repo" config user.name "ci"
    for t in "$@"; do
        git -C "$repo" commit -q --allow-empty -m "release $t"
        git -C "$repo" tag "$t"
    done
}

# ── Fake `docker`: records what it was asked to do and answers from env-driven scenarios ─────
fake_docker="$tmp_dir/fake-docker"
cat > "$fake_docker" <<'EOF'
#!/usr/bin/env bash
set -uo pipefail
log="${FAKE_DOCKER_LOG:?}"
echo "docker $*" >> "$log"
case "$1" in
    pull)
        [ "${FAKE_DOCKER_PULL_FAILS:-0}" = "1" ] && exit 1
        exit 0
        ;;
    run)
        # -d ... IMAGE — print a fake container id, like real `docker run -d` does.
        echo "fake-container-id"
        exit 0
        ;;
    stop|rm)
        exit 0
        ;;
    *)
        echo "fake-docker: unhandled subcommand: $1" >&2
        exit 2
        ;;
esac
EOF
chmod +x "$fake_docker"

# ── Fake `curl`: answers /readyz and POST /api/query without a real hub running ───────────────
# Reads which HTTP method + URL + body it was called with from argv (the script always calls it
# the same documented way), and answers from env-driven scenarios so each test controls exactly
# what "N-1 talking to N's schema" would say.
fake_curl="$tmp_dir/fake-curl"
cat > "$fake_curl" <<'EOF'
#!/usr/bin/env bash
set -uo pipefail
log="${FAKE_CURL_LOG:?}"
echo "curl $*" >> "$log"

is_readyz=0
body=""
for a in "$@"; do
    case "$a" in
        */readyz) is_readyz=1 ;;
    esac
done
# The -d payload (the JSON body) is always the argument right after -d.
prev=""
for a in "$@"; do
    [ "$prev" = "-d" ] && body="$a"
    prev="$a"
done

if [ "$is_readyz" = "1" ]; then
    if [ "${FAKE_READYZ_DOWN:-0}" = "1" ]; then
        printf '503'
    else
        printf '200'
    fi
    exit 0
fi

# POST /api/query: decide ok:true/false from which query name is in the body.
name=$(printf '%s' "$body" | sed -n 's/.*"name":"\([^"]*\)".*/\1/p')
if [ -n "${FAKE_FAIL_QUERY:-}" ] && [ "$name" = "${FAKE_FAIL_QUERY}" ]; then
    printf '{"ok":false,"error":"boom"}'
else
    printf '{"ok":true,"data":[]}'
fi
EOF
chmod +x "$fake_curl"

# ── Fake "apply N's migrations": stands in for `cargo build` + booting the branch's own ──────
# binary, which a hermetic test cannot afford to actually run.
fake_apply_ok="$tmp_dir/fake-apply-ok"
cat > "$fake_apply_ok" <<'EOF'
#!/usr/bin/env bash
# Records the Cloud URL N would boot with (hub#1282 review): the script must hand the SAME
# explicit stub to N that it hands to N-1, so neither binary ever defaults to production.
echo "HUB_CLOUD_API_URL=${HUB_CLOUD_API_URL:-<unset>}" >> "${FAKE_APPLY_LOG:?}"
exit 0
EOF
chmod +x "$fake_apply_ok"

fake_apply_fails="$tmp_dir/fake-apply-fails"
cat > "$fake_apply_fails" <<'EOF'
#!/usr/bin/env bash
echo "cargo build failed: does not compile" >&2
exit 1
EOF
chmod +x "$fake_apply_fails"

run() { # runs the script against $repo with the fakes wired in
    docker_log="$tmp_dir/docker.log"; : > "$docker_log"
    curl_log="$tmp_dir/curl.log"; : > "$curl_log"
    apply_log="$tmp_dir/apply.log"; : > "$apply_log"
    FAKE_DOCKER_LOG="$docker_log" FAKE_CURL_LOG="$curl_log" FAKE_APPLY_LOG="$apply_log" \
    FAKE_DOCKER_PULL_FAILS="${FAKE_DOCKER_PULL_FAILS:-0}" \
    FAKE_READYZ_DOWN="${FAKE_READYZ_DOWN:-0}" \
    FAKE_FAIL_QUERY="${FAKE_FAIL_QUERY:-}" \
        "$script" \
            --repo-dir "$repo" \
            --image ghcr.io/erplora/hub \
            --database-url "postgres://postgres:test@localhost:5433/hub_test" \
            --bind "0.0.0.0:8788" \
            --ready-timeout 2 --ready-interval 1 \
            --docker-cmd "$fake_docker" \
            --curl-cmd "$fake_curl" \
            --apply-migrations-cmd "${FAKE_APPLY_CMD:-$fake_apply_ok}" \
        > "$tmp_dir/out" 2>&1
    status=$?
}

# ── Case 1: N-1 keeps serving against N's schema → GREEN ──────────────────────────────────────
make_tagged_repo v1.1.9 v1.1.10 v1.1.11
FAKE_DOCKER_PULL_FAILS=0 FAKE_READYZ_DOWN=0 FAKE_FAIL_QUERY="" run
[ "$status" -eq 0 ] || fail "N-1 serving fine must be GREEN (exit 0), got $status: $(cat "$tmp_dir/out")"
grep -qi "GREEN" "$tmp_dir/out" || fail "a passing run must say GREEN: $(cat "$tmp_dir/out")"
# The tag it picked must be the highest by SEMVER, not the lexicographically last one
# ("v1.1.9" sorts after "v1.1.10"/"v1.1.11" as plain text).
grep -qF "v1.1.11" "$tmp_dir/out" || fail "must resolve v1.1.11 as N-1 (semver sort), got: $(cat "$tmp_dir/out")"
grep -qF "v1.1.9" "$docker_log" && fail "must NOT have pulled the older v1.1.9 tag's image"
passed=$((passed + 1))

# ── Case 2: N-1 fails a core query against N's schema → RED, naming the query ─────────────────
make_tagged_repo v1.1.9 v1.1.10 v1.1.11
FAKE_DOCKER_PULL_FAILS=0 FAKE_READYZ_DOWN=0 FAKE_FAIL_QUERY="hub.roles.list" run
[ "$status" -ne 0 ] || fail "a broken core query must be RED (non-zero exit), got 0: $(cat "$tmp_dir/out")"
grep -qi "RED" "$tmp_dir/out" || fail "a failing run must say RED: $(cat "$tmp_dir/out")"
grep -qF "hub.roles.list" "$tmp_dir/out" || fail "the failure must name the broken query (hub.roles.list): $(cat "$tmp_dir/out")"
passed=$((passed + 1))

# ── Case 3: the N-1 image is missing from GHCR → RED, naming the tag ──────────────────────────
make_tagged_repo v1.1.9 v1.1.10 v1.1.11
FAKE_DOCKER_PULL_FAILS=1 FAKE_READYZ_DOWN=0 FAKE_FAIL_QUERY="" run
[ "$status" -ne 0 ] || fail "a missing N-1 image must be RED (non-zero exit), got 0: $(cat "$tmp_dir/out")"
grep -qi "RED" "$tmp_dir/out" || fail "a missing image must say RED: $(cat "$tmp_dir/out")"
grep -qF "v1.1.11" "$tmp_dir/out" || fail "the failure must name the tag it could not pull (v1.1.11): $(cat "$tmp_dir/out")"
# It must not even try to boot a container it never pulled.
grep -q "^docker run" "$docker_log" && fail "must not attempt to run a container whose image failed to pull"
passed=$((passed + 1))

# ── Case 4: N-1 never reaches /readyz=UP against N's schema → RED, naming the tag ─────────────
make_tagged_repo v1.1.9 v1.1.10 v1.1.11
FAKE_DOCKER_PULL_FAILS=0 FAKE_READYZ_DOWN=1 FAKE_FAIL_QUERY="" run
[ "$status" -ne 0 ] || fail "N-1 never becoming ready must be RED (non-zero exit), got 0: $(cat "$tmp_dir/out")"
grep -qi "RED" "$tmp_dir/out" || fail "a readyz timeout must say RED: $(cat "$tmp_dir/out")"
grep -qF "v1.1.11" "$tmp_dir/out" || fail "the failure must name the tag that never became ready (v1.1.11): $(cat "$tmp_dir/out")"
passed=$((passed + 1))

# ── Case 5: N's OWN migrations fail on a clean Postgres → RED, before ever touching N-1 ───────
make_tagged_repo v1.1.9 v1.1.10 v1.1.11
FAKE_APPLY_CMD="$fake_apply_fails" run
[ "$status" -ne 0 ] || fail "N failing to migrate a clean Postgres must be RED, got 0: $(cat "$tmp_dir/out")"
grep -qi "RED" "$tmp_dir/out" || fail "N's own migration failure must say RED: $(cat "$tmp_dir/out")"
grep -q "^docker pull" "$docker_log" && fail "must not pull N-1's image before N's own migrations even applied"
passed=$((passed + 1))

# ── Case 6: neither N nor N-1 may point at production (hub#1282 review, hub#1279) ─────────────
# `HubConfig::from_env` defaults `HUB_CLOUD_API_URL` to https://erplora.com. A CI job that boots
# two hub binaries with no explicit Cloud URL would default BOTH to production; the script must
# hand each an explicit closed-loopback stub, the same way `HUB_AUTH=dev` is set explicitly.
make_tagged_repo v1.1.9 v1.1.10 v1.1.11
FAKE_DOCKER_PULL_FAILS=0 FAKE_READYZ_DOWN=0 FAKE_FAIL_QUERY="" run
[ "$status" -eq 0 ] || fail "case 6 precondition: a healthy run must be GREEN, got $status: $(cat "$tmp_dir/out")"
n1_run=$(grep '^docker run' "$docker_log")
grep -qE -- '-e HUB_CLOUD_API_URL=http://127\.0\.0\.1:[0-9]+' <<<"$n1_run" \
    || fail "N-1 must be started with an explicit loopback HUB_CLOUD_API_URL (never the production default): $n1_run"
grep -qF 'erplora.com' "$docker_log" && fail "N-1 must never be pointed at erplora.com: $(cat "$docker_log")"
grep -qE '^HUB_CLOUD_API_URL=http://127\.0\.0\.1:[0-9]+$' "$apply_log" \
    || fail "N must be booted with the same explicit loopback HUB_CLOUD_API_URL, got: $(cat "$apply_log")"
passed=$((passed + 1))

echo "OK — n-minus-one.sh: $passed cases passed"
