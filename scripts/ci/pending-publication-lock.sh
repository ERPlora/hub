#!/usr/bin/env bash
# A PR that DELETES a kernel e2e may not, in the same diff, ADD a `# pending-publication:` marker.
#
#   usage: pending-publication-lock.sh --base <ref> [--head <ref>]
#
# Compares the two reviewed lists between <base> and <head> (default HEAD) of the repo in the
# current directory:
#   · entries of `scripts/ci/kernel-e2e-targets.txt` present in <base> and gone in <head>;
#   · `# pending-publication:` markers of `scripts/ci/module-hub-batteries.txt` present in <head>
#     and absent in <base>.
# Both non-empty → exit 1 with both sides named on STDERR. Exit 0 otherwise; exit 2 on an
# environment error (a ref that does not resolve), never read as a verdict.
#
# Sets, not a line diff: reordering a list or moving an existing marker is not a deletion nor an
# addition. Lines are trimmed the way `kernel-e2e-targets.sh` and `module-hub-batteries.sh` trim
# them, so an indented entry or marker still counts.
#
# ── WHY THIS EXISTS (hub#1995, from hub#1994) ──────────────────────────────────────────────
# hub#1264 moves module-owned e2e out of the hub into the modules' batteries, and the move is only
# safe if the heir battery is ALREADY published and running. kitchen#84's marker lets a NEW
# battery be declared before its module publishes it — and excuses it from the catalogue check
# meanwhile. Used on the heir of a deleted e2e, it leaves that coverage run by nobody until the
# marker expires (up to 30 days, hub#1994): the hub#1381 hole with a deadline. So the marker is
# for new batteries only. If a PR genuinely needs both — retire an e2e and land an unrelated new
# battery — split it: publish the battery first, then delete the e2e against a published heir.
#
# Runs in `actionlint.yml` on every pull request (`--base HEAD^1`: the checkout is the PR merge
# commit, whose first parent is the base branch). Cases: `scripts/tests/pending-publication-lock.test.sh`.
set -uo pipefail

KERNEL='scripts/ci/kernel-e2e-targets.txt'
BATTERIES='scripts/ci/module-hub-batteries.txt'
MARKER='# pending-publication:'

base=''
head='HEAD'

usage() {
    printf 'usage: %s --base <ref> [--head <ref>]\n' "$0"
}

while [ $# -gt 0 ]; do
    case "$1" in
        --base) base="${2:-}"; shift 2 ;;
        --head) head="${2:-}"; shift 2 ;;
        -h | --help) usage; exit 0 ;;
        *) usage >&2; exit 2 ;;
    esac
done

if [ -z "$base" ]; then
    usage >&2
    exit 2
fi

resolve() { # $1=ref → commit sha, or exit 2
    local sha
    if ! sha=$(git rev-parse --verify --quiet "$1^{commit}"); then
        printf 'pending-publication-lock: cannot resolve %s to a commit in %s\n' "$1" "$PWD" >&2
        exit 2
    fi
    printf '%s\n' "$sha"
}

base_sha=$(resolve "$base") || exit 2
head_sha=$(resolve "$head") || exit 2

# The trimmed lines of <file> at <commit>; empty when the file does not exist there.
lines_at() { # $1=commit, $2=path
    if git cat-file -e "$1:$2" 2>/dev/null; then
        git show "$1:$2" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//'
    fi
}

kernel_entries() { # $1=commit → sorted distinct entries (no comments, no blank lines)
    lines_at "$1" "$KERNEL" | awk 'NF && substr($0, 1, 1) != "#"' | sort -u
}

markers() { # $1=commit → sorted distinct pending-publication markers
    lines_at "$1" "$BATTERIES" | awk -v m="$MARKER" 'index($0, m) == 1' | sort -u
}

removed=$(comm -23 <(kernel_entries "$base_sha") <(kernel_entries "$head_sha"))
added=$(comm -13 <(markers "$base_sha") <(markers "$head_sha"))

if [ -z "$removed" ] || [ -z "$added" ]; then
    exit 0
fi

{
    printf 'pending-publication-lock: this diff deletes a kernel e2e AND adds a pending-publication marker.\n'
    printf 'The heir of a deleted e2e must be a battery ALREADY published and running; the marker is\n'
    printf 'for NEW batteries only (hub#1995). Publish the battery first, then delete the e2e.\n'
    printf '%s\n' "$removed" | sed 's/^/pending-publication-lock: removed-kernel-e2e: /'
    printf '%s\n' "$added" | sed 's/^/pending-publication-lock: added-marker: /'
} >&2
exit 1
