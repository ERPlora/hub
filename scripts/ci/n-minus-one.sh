#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# n-minus-one.sh — does the LAST released binary (N-1) keep serving against the
# schema the CURRENT branch (N) would leave behind? (hub#1282, second half of hub#1163)
#
# hub#1163's lint reads the TEXT of a migration (`RENAME`, `ALTER COLUMN … TYPE`) and blocks
# what it can see there. What no lint can see: a new NOT NULL constraint, a default that quietly
# disappeared, or a table that changed shape without using any watched verb. The only way to
# know N-1 still works is to actually RUN it against N's schema — this script is that run.
#
# What it does, in order (and why the order matters — each step is a distinct way to be RED):
#
#   1. Resolve the last `v*` tag (semver sort — NOT lexicographic: this repo already has
#      "v1.1.9" sorting AFTER "v1.1.10"/"v1.1.11" as plain text) and its commit sha.
#   2. Pull `ghcr.io/erplora/hub:<sha>` — the SAME immutable-by-commit tag `build-hub.yml`
#      already publishes on every push to `main` and every `v*` release (scripts/image-tags.sh),
#      reused here instead of rebuilding N-1 from source. Missing ⇒ RED, naming the tag.
#   3. Build N (this branch) from source and boot it briefly against a CLEAN Postgres, letting
#      its own startup apply the system migrations (`erplora_runtime::system_migrations`) —
#      that clean Postgres, after N stops, IS "N's schema". N failing here is RED before N-1
#      is ever touched: it means N itself does not boot, which is a different bug than this
#      script exists to catch, but must not be hidden behind a false N-1 verdict.
#   4. Start the N-1 image against that SAME database and wait for `/readyz`=UP. N-1 never
#      becoming ready ⇒ RED, naming the tag.
#   5. Smoke a minimal set of CORE queries (the `hub.*` reserved namespace, ADR-0192 —
#      `crates/runtime/src/hub_users.rs::CORE_QUERIES`; the one surface reachable without a
#      module installed, since modules come from the marketplace at runtime and this job has no
#      network path to it) through N-1. The first one that fails ⇒ RED, naming that query.
#
# Every external dependency is a seam (git tags are real — a tiny repo is cheap to make in a
# test; docker/curl/the "apply N's migrations" step are swappable) so
# `scripts/tests/n-minus-one.test.sh` can prove each RED path fires, hermetically, offline —
# same shape as `scripts/image-tags.sh` / `image-tags.test.sh`.
#
# Usage:
#   scripts/ci/n-minus-one.sh --repo-dir . --image ghcr.io/erplora/hub \
#       --database-url postgres://postgres:test@localhost:5432/hub_test \
#       --bind 0.0.0.0:8788
#
# Seams (all optional, default to the real thing):
#   --docker-cmd <cmd>             default: docker
#   --curl-cmd <cmd>                default: curl
#   --git-cmd <cmd>                 default: git
#   --apply-migrations-cmd <cmd>   default: build+boot N from source (see apply_branch_migrations)
#   --ready-timeout <seconds>      default: 90
#   --ready-interval <seconds>     default: 2
# ─────────────────────────────────────────────────────────────────────────────
set -uo pipefail

# Queries del namespace reservado `hub.` (ADR-0192) que cualquier hub recién nacido puede
# responder sin un solo módulo instalado — es la única superficie de negocio alcanzable en este
# job, que no tiene red hacia el marketplace para instalar nada real.
CORE_QUERIES="hub.users.list hub.roles.list hub.setup.status hub.fiscal.limits hub.approvals.list"

# Neither binary may ever point at production (hub#1279): `HubConfig::from_env` defaults
# `HUB_CLOUD_API_URL` to https://erplora.com when the variable is absent. Nothing in this job
# needs the Cloud (no machine token ⇒ no marketplace, no heartbeat, no error sink), so both N and
# N-1 get the same explicit closed-loopback stub — port 9 is `discard`, nothing listens there.
CLOUD_API_URL_STUB="http://127.0.0.1:9"

repo_dir="."
image="ghcr.io/erplora/hub"
database_url=""
bind="0.0.0.0:8788"
ready_timeout=90
ready_interval=2
docker_cmd="docker"
curl_cmd="curl"
git_cmd="git"
apply_migrations_cmd=""

usage() {
    cat >&2 <<'EOF'
Usage: n-minus-one.sh --database-url <postgres DSN> [options]

Required:
  --database-url <dsn>          Postgres DSN of a CLEAN scratch database (service container).

Options:
  --repo-dir <path>              Checkout of the branch under test (default: .)
  --image <ref>                  GHCR image base (default: ghcr.io/erplora/hub)
  --bind <host:port>              Where N and (later) N-1 listen (default: 0.0.0.0:8788)
  --ready-timeout <seconds>      /readyz poll timeout (default: 90)
  --ready-interval <seconds>     /readyz poll interval (default: 2)
  --docker-cmd <cmd>              Seam for tests (default: docker)
  --curl-cmd <cmd>                 Seam for tests (default: curl)
  --git-cmd <cmd>                  Seam for tests (default: git)
  --apply-migrations-cmd <cmd>   Seam for tests; real default builds+boots N from source.
EOF
}

while [ $# -gt 0 ]; do
    case "$1" in
        --repo-dir) repo_dir="$2"; shift 2 ;;
        --image) image="$2"; shift 2 ;;
        --database-url) database_url="$2"; shift 2 ;;
        --bind) bind="$2"; shift 2 ;;
        --ready-timeout) ready_timeout="$2"; shift 2 ;;
        --ready-interval) ready_interval="$2"; shift 2 ;;
        --docker-cmd) docker_cmd="$2"; shift 2 ;;
        --curl-cmd) curl_cmd="$2"; shift 2 ;;
        --git-cmd) git_cmd="$2"; shift 2 ;;
        --apply-migrations-cmd) apply_migrations_cmd="$2"; shift 2 ;;
        -h|--help) usage; exit 0 ;;
        *) echo "n-minus-one: unknown argument: $1" >&2; usage; exit 2 ;;
    esac
done

if [ -z "$database_url" ]; then
    echo "n-minus-one: --database-url is required" >&2
    usage
    exit 2
fi

# GHCR lowercases package names; github.repository_owner keeps its case (same normalization as
# scripts/image-tags.sh, so the two never disagree on what the image is called).
image=$(printf '%s' "$image" | tr '[:upper:]' '[:lower:]')

port="${bind##*:}"
base_url="http://127.0.0.1:${port}"

log() { printf '%s\n' "$*"; }

# ── 1. Resolve N-1: the last `v*` tag, by SEMVER — not by plain-text sort ──────────────────────
# `git tag -l | sort`/`tail -1` ranks "v1.1.9" above "v1.1.10" as TEXT. `--sort=-v:refname` is
# git's own version-aware sort (the same field `git tag` uses for `--sort=v:refname` elsewhere in
# the codebase) and gets X.Y.Z right without hand-rolled numeric parsing.
resolve_last_tag() {
    "$git_cmd" -C "$repo_dir" tag -l 'v*' --sort=-v:refname | head -1
}

resolve_tag_sha() { # $1 = tag
    "$git_cmd" -C "$repo_dir" rev-list -n1 "$1"
}

# ── 2. Pull N-1's immutable image ──────────────────────────────────────────────────────────────
pull_n1_image() { # $1 = image ref
    "$docker_cmd" pull "$1" >&2
}

# ── /readyz poll, shared by "N applies its migrations" and "N-1 boots against them" ───────────
wait_ready() {
    local deadline=$(( $(date +%s) + ready_timeout ))
    while [ "$(date +%s)" -lt "$deadline" ]; do
        local code
        code=$("$curl_cmd" -sS -o /dev/null -w '%{http_code}' "${base_url}/readyz" 2>/dev/null || echo 000)
        [ "$code" = "200" ] && return 0
        sleep "$ready_interval"
    done
    return 1
}

# ── 3. Apply N's (this branch's) migrations to a clean Postgres ───────────────────────────────
# The real implementation: build the branch's own server binary and boot it briefly. Its normal
# startup (`erplora_server::serve`) runs `erplora_runtime::system_migrations::apply` before it
# ever answers `/readyz`, so a clean Postgres that N reaches UP against — RIGHT AFTER — has
# exactly N's system schema. No module migrations run because a fresh hub has zero installed
# modules (`hub_module` is empty) — same starting point `newborn_hub_is_empty.rs` boots from.
apply_branch_migrations_default() {
    local dsn="$1"
    log "n-minus-one: building N (this branch) — cargo build -p erplora-server"
    if ! (cd "$repo_dir" && cargo build -p erplora-server) >&2; then
        echo "n-minus-one: N (this branch) failed to compile — cannot produce the schema to test against." >&2
        return 1
    fi
    local bin="$repo_dir/target/debug/erplora-server"
    if [ ! -x "$bin" ]; then
        echo "n-minus-one: build reported success but $bin is not there." >&2
        return 1
    fi
    log "n-minus-one: booting N briefly to apply its migrations against a clean Postgres"
    HUB_DATABASE_URL="$dsn" HUB_AUTH=dev HUB_BIND="$bind" HUB_CLOUD_API_URL="$CLOUD_API_URL_STUB" "$bin" >&2 &
    local pid=$!
    if ! wait_ready; then
        echo "n-minus-one: N (this branch) never reached /readyz=UP against a clean Postgres — its migrations did not finish applying." >&2
        kill "$pid" 2>/dev/null || true
        wait "$pid" 2>/dev/null || true
        return 1
    fi
    kill "$pid" 2>/dev/null || true
    wait "$pid" 2>/dev/null || true
    log "n-minus-one: N's migrations are applied — this Postgres now has N's schema"
    return 0
}

apply_branch_migrations() { # $1 = dsn
    if [ -n "$apply_migrations_cmd" ]; then
        HUB_CLOUD_API_URL="$CLOUD_API_URL_STUB" "$apply_migrations_cmd" "$1"
        return $?
    fi
    apply_branch_migrations_default "$1"
}

# ── 4. Start N-1 against N's schema ────────────────────────────────────────────────────────────
start_n1_container() { # $1 = image ref, $2 = dsn
    "$docker_cmd" run -d --rm --network host \
        -e HUB_DATABASE_URL="$2" -e HUB_AUTH=dev -e HUB_BIND="$bind" \
        -e HUB_CLOUD_API_URL="$CLOUD_API_URL_STUB" \
        "$1"
}

stop_n1_container() { # $1 = container id
    [ -n "${1:-}" ] || return 0
    "$docker_cmd" stop "$1" >/dev/null 2>&1 || true
}

# ── 5. Smoke the core queries through N-1 ──────────────────────────────────────────────────────
run_core_query() { # $1 = query name → 0 if {"ok":true}, 1 otherwise
    local body
    body=$("$curl_cmd" -sS -X POST "${base_url}/api/query" \
        -H 'content-type: application/json' \
        -d "{\"name\":\"$1\",\"params\":{}}" 2>/dev/null)
    grep -q '"ok":true' <<<"$body"
}

main() {
    local tag sha image_ref container

    tag=$(resolve_last_tag)
    if [ -z "$tag" ]; then
        log "n-minus-one: no v* tag found yet — nothing published to compare N-1 against. Nothing to do."
        exit 0
    fi
    sha=$(resolve_tag_sha "$tag")
    if [ -z "$sha" ]; then
        echo "::error::n-minus-one: RED — could not resolve a commit for tag '$tag'." >&2
        exit 1
    fi
    image_ref="${image}:${sha}"
    log "n-minus-one: N-1 = ${tag} (${sha}) → ${image_ref}"

    # ── Step 3 first, on purpose: N's own migrations must apply before N-1 is even fetched. ──
    # A red here is a DIFFERENT bug (N does not boot) and must not be reported as an N-1 finding.
    if ! apply_branch_migrations "$database_url"; then
        echo "::error::n-minus-one: RED — the branch's own migrations did not apply cleanly; N-1 was never touched." >&2
        exit 1
    fi

    if ! pull_n1_image "$image_ref"; then
        echo "::error::n-minus-one: RED — could not pull N-1's image (${tag}, ${image_ref}). The check could not run." >&2
        exit 1
    fi

    container=$(start_n1_container "$image_ref" "$database_url")
    if [ -z "$container" ]; then
        echo "::error::n-minus-one: RED — N-1 (${tag}) did not start against N's schema." >&2
        exit 1
    fi
    # shellcheck disable=SC2064 # container id is fixed at trap-set time, on purpose
    trap "stop_n1_container '$container'" EXIT

    if ! wait_ready; then
        echo "::error::n-minus-one: RED — N-1 (${tag}) never reached /readyz=UP against N's schema." >&2
        exit 1
    fi

    for q in $CORE_QUERIES; do
        if ! run_core_query "$q"; then
            echo "::error::n-minus-one: RED — N-1 (${tag}) cannot serve '${q}' against N's schema." >&2
            exit 1
        fi
    done

    log "n-minus-one: GREEN — N-1 (${tag}) still serves /readyz + ${CORE_QUERIES// /, } against N's schema."
}

main
