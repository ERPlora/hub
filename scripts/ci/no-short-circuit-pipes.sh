#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# No shell script of this repo may pipe into a reader that SHORT-CIRCUITS
# (hub#1534).
#
# `producer | grep -q PATTERN` under `set -o pipefail` is a check that lies in
# the WORST direction. `grep -q` exits at the FIRST match and closes the pipe;
# the producer takes `EPIPE` and dies with 141, and `pipefail` hands the pipeline
# the PRODUCER's status — so a MATCH is reported as a failure and `if ! … ; then`
# takes the error branch precisely when the pattern WAS there.
#
# It is a race (whoever finishes first wins), so it goes green on macOS and on an
# idle runner and red on a loaded Linux one. On 2026-09-04 it failed the PR of
# hub#1530 claiming the Playwright bench did not pin `HUB_CLOUD_API_URL` — a line
# that had been there since July. The cost is not the lost PR: it is a watchman
# that shouts when everything is fine, and the answer it trains everyone to give.
#
# The fix is a here-string, which opens no pipe at all:
#
#     grep -q PATTERN <<<"$block"          instead of   printf '%s' "$block" | grep -q PATTERN
#     grep -qx "$x" <<<"$(some_command)"   instead of   some_command | grep -qx "$x"
#
# What counts as short-circuiting here: `grep` with `-q` (exits at the first
# match) or with `-m N` (exits at the Nth). `| head -N` is the same mechanism and
# is NOT scanned yet — hub#1552 has the sixteen live occurrences; adding it here
# before they are swept would be a guard born red.
#
# Not flagged, on purpose:
#   · comment lines — the trap has to be explainable in writing;
#   · a match inside a backtick span (odd number of backticks before it), which
#     is how this repo quotes the pattern in prose and in `bad`/`ok` messages;
#   · a line tagged `sigpipe-demo`, for the two places that use the defect on
#     purpose to PROVE it is real before forbidding it.
#
# Usage:
#   scripts/ci/no-short-circuit-pipes.sh [--root DIR] [--list]
#
#   --root DIR   tree to scan (default: this repo)
#   --list       print the discovered scripts and exit
#
# Exit: 0 clean · 1 at least one offending line · 2 usage or environment problem.
#
# Discovery is delegated to `scripts/ci/shell-syntax.sh --list` — the repo's one
# answer to "which files are shell scripts" (`*.sh` anywhere plus anything with a
# sh/bash shebang, so `.githooks/pre-push` is in). One discoverer, one place to
# fix when it drifts; `scripts/tests/shell-syntax.test.sh` pins its size and
# `scripts/tests/no-short-circuit-pipes.test.sh` pins this file's use of it.
#
# Contract: scripts/tests/no-short-circuit-pipes.test.sh
# ─────────────────────────────────────────────────────────────────────────────
set -uo pipefail

self_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
root=$(CDPATH= cd -- "$self_dir/../.." && pwd)
list_only=0

die() { printf 'no-short-circuit-pipes: %s\n' "$1" >&2; exit 2; }

while [ $# -gt 0 ]; do
    case "$1" in
        (--root)
            [ $# -ge 2 ] || die "--root needs a directory"
            root=$2; shift 2 ;;
        (--list) list_only=1; shift ;;
        (-h | --help)
            sed -n '2,45p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        (*) die "unknown argument: $1" ;;
    esac
done

[ -d "$root" ] || die "no such directory: $root"
root=$(CDPATH= cd -- "$root" && pwd)

discoverer="$self_dir/shell-syntax.sh"
[ -x "$discoverer" ] || die "no such discoverer: $discoverer"

listing=$("$discoverer" --root "$root" --list 2>/dev/null)
[ -n "$listing" ] || die "the discoverer returned nothing for $root — discovery is broken, not the tree"

scripts=""
while IFS= read -r rel; do
    [ -n "$rel" ] || continue
    case "$rel" in (shell-syntax:*) continue ;; esac
    scripts="$scripts$rel
"
done <<EOF
$listing
EOF

count=$(grep -c . <<<"$scripts" || true)

if [ "$list_only" -eq 1 ]; then
    printf '%s' "$scripts"
    exit 0
fi

[ "$count" -gt 0 ] || die "no shell script found under $root — discovery is broken, not the tree"

# ── The scan ────────────────────────────────────────────────────────────────
# ONE awk per file: no pipe and no short-circuiting reader, because a scanner
# written with the very defect it hunts is the joke that writes itself.
#
# The pipe is written `[|]`, and that is not a style choice. `-v` runs its own
# escape pass over the value, so a single-backslash `\|` arrives at the regex
# engine already eaten and the `|` becomes an alternation: `illegal primary in
# regular expression`, awk dies on every file, and — with the previous version of
# the line below, which sent awk's stderr to /dev/null — the scanner reported the
# whole tree CLEAN, exit 0. Doubling it (`\\|`) also works, which is worse: two
# spellings that look the same and only one of them scans anything. The character
# class has no escape to get wrong. Measured while writing this file, and the
# per-flag positive controls in the contract test are what caught it.
#
# Assembled from fragments so that these lines do not match themselves — a guard
# that has to exempt its own source has a hole the size of that exemption.
pipe_then_grep='[|][[:space:]]*grep([[:space:]]+-[A-Za-z-]+)*[[:space:]]+-[A-Za-z]*'
quiet_flag="${pipe_then_grep}q"
max_count_flag="${pipe_then_grep}m[[:space:]]*[0-9]"

failed=0
offenders=0
while IFS= read -r rel; do
    [ -n "$rel" ] || continue
    hits=$(awk -v q="$quiet_flag" -v m="$max_count_flag" '
        /^[[:space:]]*#/  { next }
        /sigpipe-demo/    { next }
        {
            if (!match($0, q) && !match($0, m)) next
            # A match inside a backtick span is prose ABOUT the pattern, not code:
            # an odd number of backticks before it means the span is still open.
            before = substr($0, 1, RSTART - 1)
            ticks = gsub(/`/, "`", before)
            if (ticks % 2 == 1) next
            printf "%d: %s\n", FNR, $0
        }
    ' "$root/$rel") || die "awk failed while scanning $rel — the scan is UNPROVEN, not clean"
    [ -n "$hits" ] || continue
    failed=$((failed + 1))
    while IFS= read -r hit; do
        [ -n "$hit" ] || continue
        offenders=$((offenders + 1))
        printf '  \033[31m✗\033[0m %s:%s\n' "$rel" "$hit" >&2
    done <<EOF
$hits
EOF
done <<EOF
$scripts
EOF

if [ "$failed" -gt 0 ]; then
    printf '\033[31mFAIL\033[0m: %d líneas en %d de %d scripts canalizan hacia un lector que corta\n' \
        "$offenders" "$failed" "$count" >&2
    printf '       bajo `pipefail` un MATCH se reporta como FALLO. Usa `grep -q PATRÓN <<<"$bloque"` (hub#1534).\n' >&2
    exit 1
fi
printf '\033[32mOK\033[0m: %d scripts, ninguno canaliza hacia un lector que corta (hub#1534)\n' "$count"
