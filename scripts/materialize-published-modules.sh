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
# ERPlora/hub#1294. A clone/fetch that fails with a TRANSIENT transport or
# auth error (a dropped SSH handshake, a reset connection) is retried with
# backoff before the module is given up on. On 2026-08-28 at 11:55-11:56Z one
# such flake — `Permission denied (publickey)` on `invoice_series`, with the
# very same deploy key that had cloned it fine three hours before — turned the
# whole "e2e con módulos reales" job red with zero retries and blocked nine
# approved PRs behind it. A PERMANENT failure (e.g. "repository not found",
# meaning the key or the repo name is wrong) is never retried: retrying it
# only delays the same answer.
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
#   env HUB_MATERIALIZE_RETRY_DELAYS  space-separated backoff (seconds) between
#                            retries of a transient clone/fetch failure
#                            (default "2 8 30" — 3 retries, 4 attempts total).
#                            Only ever overridden by the test suite, to run
#                            the retry cases without sitting through real time.
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

# Only real module ids survive. The pattern is the manifest's own
# (`schemas/module.schema.json` → `id`), not one invented here.
#
# Why this exists: `MODULES_DEPLOY_KEYS` is a tar built on a Mac, so next to every key it
# carries an AppleDouble sidecar `._<module>` (and the odd `.DS_Store`). The inline loop this
# script replaced listed the bundle with plain `ls`, which HIDES dotfiles, so it never saw
# them; listing with `ls -A` does — and a 27-module catalogue became 54, with the 27 sidecars
# each handed to ssh AS A PRIVATE KEY and dying on `Permission denied (publickey)`
# (hub#1153, run 33128409723). The real modules had cloned fine; the junk failed the job.
#
# Ignoring is LOUD. A silent filter would turn a mistyped id into missing coverage, which is
# exactly the failure the floor below exists to catch — so the names are printed.
MODULE_ID_RE='^[a-z][a-z0-9_]*$'
ignored="$(printf '%s\n' "$ids" | grep -Ev "$MODULE_ID_RE" || true)"
ids="$(printf '%s\n' "$ids" | grep -E "$MODULE_ID_RE" || true)"
if [ -n "$ignored" ]; then
    say "   ⚠️  ignoring $(printf '%s\n' "$ignored" | wc -l | tr -d ' ') entry(ies) that are not a module id (${MODULE_ID_RE}): $(printf '%s ' $ignored)"
fi

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

# Only set GIT_SSH_COMMAND when there IS a key. An empty value is not "unset" to
# git: it tries to run an empty program ("fatal: unable to fork") and every ssh
# remote fails — the whole fallback path for a developer with `git@github.com:`
# remotes. Without a key the developer's own ssh (agent, config) does the work.
git_with_key() {            # $1 = ssh command or empty; the rest = git arguments
    local ssh_cmd=$1
    shift
    if [ -n "$ssh_cmd" ]; then
        GIT_SSH_COMMAND="$ssh_cmd" git "$@"
    else
        git "$@"
    fi
}

# The version is DISPLAY only — it makes a red readable ("sales 2.16.29") — so a
# machine without python3 loses the column, never the guard.
module_version() {          # $1 = tree
    python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["version"])' \
        "$1/module.json" 2>/dev/null || printf '?'
}

# ── 2b · Retry on transient clone/fetch failures (hub#1294) ──────────────────
# Only a transport/auth failure is worth a retry — one bad SSH handshake does
# not mean the repo or the key is wrong. "repository not found" and similar
# are config errors: retrying them wastes the whole backoff window only to
# report the same failure, so they are NOT in this list on purpose.
RETRY_DELAYS="${HUB_MATERIALIZE_RETRY_DELAYS:-2 8 30}"

# Which SIDE the failure is on, so the summary sends the reader to the right place
# (hub#1380). Anything that smells of the remote — auth, the network, a repo that
# is not there — is access; everything else is local, and the cache is the first
# suspect.
looks_like_access_failure() {  # $1 = path to the failed attempt's log
    grep -qiE 'permission denied|could not read from remote|repository not found|does not appear to be a git repository|connection|timed out|host key|name or service not known|access denied' \
        "$1" 2>/dev/null
}

is_transient_git_failure() {   # $1 = path to the failed attempt's log
    grep -qiE 'permission denied \(publickey\)|connection reset|early eof|could not read from remote|timed out' \
        "$1" 2>/dev/null
}

# Runs a git network step (clone, or fetch+checkout+clean) with retries on
# transient failures, backing off per $RETRY_DELAYS between attempts. A
# permanent failure (message does not match is_transient_git_failure) returns
# immediately on the FIRST attempt — no retry, no wasted backoff.
#   $1 = id (for the retry log line)   $2 = log file the step writes to
#   $3.. = the command to run (its own function, so `&&` chains stay intact)
run_with_retry() {
    local id="$1" log="$2" attempt=1 delays="$RETRY_DELAYS" delay
    shift 2
    while true; do
        if "$@" >"$log" 2>&1; then
            return 0
        fi
        is_transient_git_failure "$log" || return 1   # permanent: give up now
        delay="${delays%% *}"
        [ -n "$delay" ] || return 1                    # retry budget exhausted
        attempt=$((attempt + 1))
        say "   ⏳ $id: transient git failure — retrying (attempt ${attempt}) in ${delay}s…"
        sleep "$delay"
        case "$delays" in
            *' '*) delays="${delays#* }" ;;
            *)     delays="" ;;
        esac
    done
}

# The two network steps a module can need, each wrapped by run_with_retry so
# a flaky attempt starts from a clean slate rather than a half-written tree.
# `-f` on the checkout below is the hard reset the header already promises, and
# hub#1380 is what its absence cost: the cache is SHARED by every worktree of the
# hub, so ONE touched file inside it aborted the checkout — and the sanitising
# step that would have removed it runs AFTER, so it never got to run at all. The
# gate then stayed dead for the whole fleet, pointing at the deploy keys.
# Forcing is safe HERE for the reason the header gives: $DEST is a DERIVED cache
# this script owns end to end, and nobody edits inside it.
fetch_existing_tree() {     # $1 = ssh_cmd  $2 = tree  $3 = url  $4 = branch
    git_with_key "$1" -C "$2" fetch -q --depth 1 "$3" "$4" \
        && git -C "$2" checkout -qf --detach FETCH_HEAD \
        && git -C "$2" clean -qfdx
}

# A cached directory is only reusable when it IS the module's own repo. On
# 2026-08-30 all 27 held a clone of the HUB instead (639 MB, `origin` pointing at
# ERPlora/hub), and the module checkout aborted against the hub's own files.
# Fetching on top of the wrong repo never heals; re-cloning always does, and at
# `--depth 1` it costs little. An unreadable or remote-less `.git` answers empty
# here, which is also "not the module" — and also wants a re-clone.
tree_is_the_module() {      # $1 = tree  $2 = expected url
    [ "$(git -C "$1" remote get-url origin 2>/dev/null || true)" = "$2" ]
}

clone_new_tree() {          # $1 = ssh_cmd  $2 = url  $3 = tree  $4 = branch
    rm -rf "$3"
    git_with_key "$1" clone -q --depth 1 --branch "$4" "$2" "$3"
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
    if [ -d "$tree/.git" ] && tree_is_the_module "$tree" "$url"; then
        if run_with_retry "$id" "$log" fetch_existing_tree "$ssh_cmd" "$tree" "$url" "$BRANCH"; then
            rm -f "$log"
        else
            failed="$failed $id"
            continue
        fi
    else
        if run_with_retry "$id" "$log" clone_new_tree "$ssh_cmd" "$url" "$tree" "$BRANCH"; then
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
    # Until hub#1380 EVERY failure read «fix the access», and half the time that is the
    # wrong place to look: a dirty or foreign cache is LOCAL, and the hours went into
    # deploy keys that were never broken. Say which side this was.
    access=0
    local_fail=0
    for id in $failed; do
        [ -f "$DEST/.$id.log" ] || continue
        if looks_like_access_failure "$DEST/.$id.log"; then
            access=1
        else
            local_fail=1
        fi
    done
    say ""
    say "   Nothing is measured against a partial catalogue."
    [ "$access" = 1 ] && \
        say "   → ACCESS: fix the deploy key / ssh agent / network, then run again."
    [ "$local_fail" = 1 ] && {
        say "   → LOCAL: this is not the access. The cache is DERIVED — nobody edits it and"
        say "     nothing else reads it — so remove it and run again:  rm -rf $DEST"
    }
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
