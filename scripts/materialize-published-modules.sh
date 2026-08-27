#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# materialize-published-modules.sh — put the PUBLISHED module catalogue on disk.
#
# ERPlora/hub#1153. The module e2e need the 27 modules, and there are exactly
# two states a module can be in: what is PUBLISHED (`origin/main` of its repo,
# `dist/` committed, which is what every hub installs) and whatever branch an
# agent happens to have left in the shared `modules-workspace` checkout. Only
# the first one is a fact. On 2026-08-28, 9 of 27 checkouts were parked off
# `main`, so measuring against them is a raffle — and it goes BOTH ways:
#
#   · a module BEHIND reds a push that did not cause it (`sales_e2e` 4 vs 5
#     operations, which cost the fleet several half-hour diagnoses);
#   · a module AHEAD greens a contract that already moved in production
#     (hub#540) — the expensive one, because nothing looks wrong.
#
# This script is the ONE place that materialises that catalogue. It is shared:
# `.githooks/pre-push` calls it for `HUB_GATE_WITH_MODULES=1` and
# `.github/workflows/test-hub-modules.yml` calls it too, so the local gate and
# the "crater/runbot" job cannot drift apart — the failure mode that already
# cost `main` once with the Postgres config living in three copies (hub#647).
#
# It is deliberately boring: `git clone --depth 1 --branch main`, a directory
# per module, `git fetch` to refresh. No archive format, no lockfile, no
# manifest of its own.
#
# The contract it implements: `architecture/hub/kernel-contract.md`
# (ADR «El Hub se CIERRA como KERNEL», 2026-08-27), §6 hole #2.
#
# ── USAGE ────────────────────────────────────────────────────────────────────
#   scripts/materialize-published-modules.sh --dest DIR [options]
#
#     --dest DIR             where the catalogue is materialised (required).
#                            One directory per module id; reused across runs.
#     --floor N              minimum number of manifests that must end up in
#                            DIR (default 25). Below it, the run FAILS.
#     --keys DIR             the deploy-key bundle (one private key per module,
#                            named after the module). When present it is the id
#                            source AND each clone uses its module's own key.
#     --ids-from DIR         a directory of module checkouts, used ONLY for the
#                            module IDS and their remote URLs — never for their
#                            content. This is how the local gate reuses the
#                            sibling `modules-workspace/modules` without ever
#                            measuring against it.
#     --modules "a b c"      an explicit id list; wins over every other source.
#     --remote-template TPL  where a module lives, `%s` = the id
#                            (default: git@github.com:ERPlora/%s.git).
#     --branch NAME          the published branch (default: main).
#
#   stdout: the resolved catalogue directory, and nothing else — callers
#           consume it (`ERPLORA_MODULES_DIR=$(… )`). Progress goes to stderr.
#
# Tests: scripts/materialize-published-modules.test.sh (local bare repos over
# `file://` — no network, no GitHub, no deploy keys).
# ─────────────────────────────────────────────────────────────────────────────
set -uo pipefail

DEST=""
FLOOR=25
KEYS_DIR="${HUB_MODULE_KEYS_DIR:-${HOME:-}/.erplora/module-keys}"
KEYS_EXPLICIT=0
IDS_FROM=""
MODULES=""
REMOTE_TEMPLATE="git@github.com:ERPlora/%s.git"
BRANCH=main

die() { printf '❌ materialize-published-modules: %s\n' "$1" >&2; exit 1; }
say() { printf '%s\n' "$1" >&2; }

while [ $# -gt 0 ]; do
    case "$1" in
        --dest)            DEST="${2:-}"; shift 2 ;;
        --floor)           FLOOR="${2:-}"; shift 2 ;;
        --keys)            KEYS_DIR="${2:-}"; KEYS_EXPLICIT=1; shift 2 ;;
        --ids-from)        IDS_FROM="${2:-}"; shift 2 ;;
        --modules)         MODULES="${2:-}"; shift 2 ;;
        --remote-template) REMOTE_TEMPLATE="${2:-}"; shift 2 ;;
        --branch)          BRANCH="${2:-}"; shift 2 ;;
        -h|--help)         sed -n '2,55p' "$0"; exit 0 ;;
        *)                 die "unknown argument: $1" ;;
    esac
done

[ -n "$DEST" ] || die "--dest is required."
case "$FLOOR" in ''|*[!0-9]*) die "--floor must be a number, got '$FLOOR'." ;; esac
command -v git >/dev/null 2>&1 || die "'git' is not on PATH."

# ── 1 · Which modules? ───────────────────────────────────────────────────────
# In order of authority. The keys bundle comes first because it is the source
# that cannot quietly fall short: in CI a module without its deploy key cannot
# be cloned at all, so the bundle IS the catalogue. `--ids-from` is the local
# fallback, and it contributes ids and remotes only.
ids=""
id_source=""
if [ -n "$MODULES" ]; then
    ids="$MODULES"
    id_source="--modules"
elif [ -d "$KEYS_DIR" ] && [ -n "$(ls -A "$KEYS_DIR" 2>/dev/null)" ]; then
    ids="$(cd "$KEYS_DIR" && ls -A)"
    id_source="deploy-key bundle $KEYS_DIR"
elif [ -n "$IDS_FROM" ] && [ -d "$IDS_FROM" ]; then
    ids="$(cd "$IDS_FROM" && for d in */; do [ -f "${d}module.json" ] && printf '%s\n' "${d%/}"; done)"
    id_source="checkout ids in $IDS_FROM"
fi
# shellcheck disable=SC2086  # word splitting is how the id list is normalised
ids="$(printf '%s\n' $ids | sed '/^$/d' | sort -u)"

if [ -z "$ids" ]; then
    say "❌ materialize-published-modules: no module ids to materialise."
    say "   Tried, in order: --modules, the deploy-key bundle ($KEYS_DIR),"
    say "   and the checkouts under '${IDS_FROM:-<--ids-from not given>}'."
    say "   Pass --modules \"<ids>\" or point --ids-from at a modules-workspace checkout."
    exit 1
fi
say "📦 materialize-published-modules: $(printf '%s\n' "$ids" | wc -l | tr -d ' ') module(s) from ${id_source}; publishing branch '${BRANCH}'."

# The bundle is only usable as a KEY source when it really holds keys; an
# explicit --keys that turns out to be empty is a caller error, not a fallback.
use_keys=0
if [ -d "$KEYS_DIR" ] && [ -n "$(ls -A "$KEYS_DIR" 2>/dev/null)" ]; then
    use_keys=1
elif [ "$KEYS_EXPLICIT" = 1 ]; then
    die "--keys '$KEYS_DIR' is not a directory with keys in it."
fi

mkdir -p "$DEST" || die "cannot create --dest '$DEST'."
DEST="$(cd "$DEST" && pwd -P)"

# ── 2 · Where does a module live, and with which credential? ─────────────────
# When a local checkout of the module exists, its own `origin` URL is preferred:
# it is a URL that already works with THIS developer's credentials (ssh, https
# + gh helper, whatever they set up), which is exactly what the fallback path
# needs. With the deploy-key bundle we go through the template instead, because
# each key is scoped to one repo and has to be paired with it.
remote_for() {              # $1 = id
    local id=$1 url=""
    if [ "$use_keys" = 0 ] && [ -n "$IDS_FROM" ] && [ -d "$IDS_FROM/$id/.git" ]; then
        url="$(git -C "$IDS_FROM/$id" remote get-url origin 2>/dev/null || true)"
    fi
    if [ -z "$url" ]; then
        # shellcheck disable=SC2059  # the template is a format string on purpose
        url="$(printf "$REMOTE_TEMPLATE" "$id")"
    fi
    printf '%s' "$url"
}

ssh_for() {                 # $1 = id — the module's own deploy key, or nothing
    local id=$1
    if [ "$use_keys" = 1 ] && [ -f "$KEYS_DIR/$id" ]; then
        printf 'ssh -i %s -o IdentitiesOnly=yes -o BatchMode=yes' "$KEYS_DIR/$id"
    fi
}

# The version is DISPLAY only — it makes a red readable ("sales 2.16.29") — so a
# machine without python3 loses the column, never the guard.
module_version() {          # $1 = tree
    python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["version"])' \
        "$1/module.json" 2>/dev/null || printf '?'
}

# ── 3 · Materialise, cached ──────────────────────────────────────────────────
# A re-clone of 27 repos on every push would make the opt-in unusable, and a
# cache that never refreshes would recreate the very staleness this exists to
# kill. So: clone once, then `fetch --depth 1` + a hard reset onto FETCH_HEAD on
# every run. The fetch IS how we learn that `origin/main` moved.
#
# The reset is safe here in a way it never is in a worktree: `$DEST` is a
# DERIVED cache this script owns end to end, it is never a place anybody edits,
# and that is exactly why the catalogue is materialised apart instead of
# `pull`ing `modules-workspace` — those checkouts hold other agents' unpushed
# commits.
#
# Failures are COLLECTED, not fail-fast: one run should name every broken
# module instead of sending the reader back for a second round per module.
failed=""
for id in $ids; do
    url="$(remote_for "$id")"
    ssh_cmd="$(ssh_for "$id")"
    tree="$DEST/$id"
    log="$DEST/.$id.log"
    if [ -d "$tree/.git" ]; then
        if GIT_SSH_COMMAND="$ssh_cmd" git -C "$tree" fetch -q --depth 1 "$url" "$BRANCH" >"$log" 2>&1 \
            && git -C "$tree" checkout -q --detach FETCH_HEAD >>"$log" 2>&1 \
            && git -C "$tree" clean -qfdx >>"$log" 2>&1; then
            rm -f "$log"
        else
            failed="$failed $id"
            continue
        fi
    else
        rm -rf "$tree"
        if GIT_SSH_COMMAND="$ssh_cmd" git clone -q --depth 1 --branch "$BRANCH" "$url" "$tree" >"$log" 2>&1; then
            rm -f "$log"
        else
            failed="$failed $id"
            continue
        fi
    fi
    if [ ! -f "$tree/module.json" ]; then
        say "   ⚠️  $id: '${BRANCH}' carries no module.json"
        failed="$failed $id"
        continue
    fi
    printf '   %-18s %s\n' "$id" "$(module_version "$tree")" >&2
done

if [ -n "$failed" ]; then
    say ""
    say "❌ materialize-published-modules: could NOT materialise:${failed}"
    for id in $failed; do
        [ -f "$DEST/.$id.log" ] || continue
        say "   ── $id ──"
        tail -5 "$DEST/.$id.log" | sed 's/^/     /' >&2
    done
    say "   Nothing is measured against a partial catalogue: fix the access (deploy key,"
    say "   ssh agent, network) and run again."
    exit 1
fi

# ── 4 · The floor ────────────────────────────────────────────────────────────
# Without it a partial catalogue silently shrinks coverage instead of failing:
# the first version of the CI job cloned 13 of 27 and would have passed at 21
# (hub#1216). A number that only ever goes UP.
n=$(find "$DEST" -mindepth 2 -maxdepth 2 -name module.json | wc -l | tr -d ' ')
if [ "$n" -lt "$FLOOR" ]; then
    say "❌ materialize-published-modules: only $n module(s) with module.json in $DEST — the floor is $FLOOR."
    say "   A short catalogue means the e2e cover LESS than they claim, which is worse than a red."
    say "   If a new module was published, add its deploy key to the bundle (hub#1216)."
    exit 1
fi

say "✅ materialize-published-modules: $n published module(s) in $DEST."
printf '%s\n' "$DEST"
