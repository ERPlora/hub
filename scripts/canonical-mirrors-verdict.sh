#!/usr/bin/env bash
# The verdict on the toolkit's vendored copies, from the hub's side (ERPlora/hub#1296).
#
# `ERPlora/module-toolkit` vendors, byte for byte, files whose authority lives here — the manifest
# schema and the FROZEN kernel surface of `contracts/kernel/` (ADR «El Hub se CIERRA como KERNEL»)
# — and its `.github/actions/check-canonical-mirrors` compares them against the hub it is run from.
# Run from a hub pull request that ADDS contract (a route, a type, a system param) that comparison
# is red BY CONSTRUCTION: the copy lives in another repository and cannot be ahead of the change
# it copies. Five approved PRs sat blocked on it in one afternoon (hub#1296), each needing a
# resync PR in the toolkit and the pair rule of ERPlora/pm#181 to get in.
#
# THE MARKET PATTERN (Kubernetes publishing-bot, rust-lang subtrees, Envoy api): the canonical
# never blocks on the copy. The copy FOLLOWS after the merge, and fails only when it DIVERGES.
# This script is that distinction, made with git and nothing else. For every vendored path:
#
#   SYNCED     the copy is the hub's file.
#   BEHIND     the copy is an OLDER version of the hub's file and the hub only ADDED to it —
#              a warning: the copy catches up after the merge (`npm run sync-mirrors`), and until
#              then the module gate is stricter than the hub, never looser.
#   RETIRED    the hub REMOVED something the copy still carries (a line, or the whole file).
#              A failure: this is the one case where the copy must move at the same time, and
#              the pair rule (`Depends-On:` + `MERGE_PR_PAIR`, pm#181/pm#183) stays for it.
#   DIVERGENT  the copy carries content the hub NEVER had — somebody edited the copy by hand.
#              A failure no hub PR can fix: the copy is what has to go back.
#   STRICT     the schema. The module gate READS it (`validate` runs on the vendored copy), so a
#              copy behind even an addition — a new `required` entry — publishes modules the hub
#              then refuses to install. It keeps the byte-for-byte rule and the pair.
#
# "Older version" is answered by the hub's own history: the copy's blob must appear at that path
# in some commit reachable from the ref under review. That is what tells a lagging copy from a
# tampered one, and it is why the caller checks the hub out with history.
#
# THE TOOLKIT'S OWN RUN IS NOT THROWN AWAY. The caller still runs the toolkit's action and hands
# its outcome in (`--toolkit-outcome`). A failure with nothing BEHIND is a failure for ANOTHER
# reason — a hand-ported list (`BRIDGE_FUNCTIONS`, `RETIRED_FIELDS`, `CORE_QUERIES`,
# `GRANDFATHERED`), a broken reader — and stays red. So does a failure on a change that touched
# the SOURCES of those lists — this script cannot tell an addition from a retirement inside Rust,
# so it does not pretend to — or that ADDED or DROPPED a file under `contracts/kernel/`: the set
# of that directory is itself a hand-ported list in the toolkit (`KERNEL_CONTRACT_FILES`). The
# pair rule applies to both, as before.
#
# Usage:
#   canonical-mirrors-verdict.sh --hub <checkout> --toolkit <checkout>
#       [--ref <rev>]              the hub tree under review (default: HEAD)
#       [--base <rev>]             what it is compared with for "touched sources" (default: <ref>^1;
#                                  on a pull_request merge ref that is the base branch)
#       [--toolkit-outcome <s>]    the outcome of the toolkit's own step (success|failure|…)
#   canonical-mirrors-verdict.sh --print-parsed-sources
#
# Exit 0 = the canonical may merge (with warnings if the copy is behind); 1 = blocked, or the
# script could not decide (an undecidable verdict is red, never green — module-toolkit#61).

set -euo pipefail

# The hub files whose toolkit mirrors are HAND-PORTED lists, not vendored copies. The toolkit's
# test parses these to compare; this script cannot classify a change in them, so a toolkit failure
# on a change touching one of these is left standing. `apps/web/src/**/*.vue` is deliberately not
# here: the toolkit reads the views as a positive control of its own scanner, not as a copy.
PARSED_LIST_SOURCES='crates/db/src/lib.rs
crates/runtime/src/manifest.rs
crates/runtime/src/hub_users.rs
crates/runtime/src/migration_guard.rs
apps/web/src/main.ts'

# Vendored files the module gate READS at validation time. Behind is not safe for these.
GATE_INPUTS='schemas/module.schema.json'

hub=''
toolkit=''
ref='HEAD'
base=''
toolkit_outcome=''

usage() {
    printf 'usage: %s --hub <dir> --toolkit <dir> [--ref <rev>] [--base <rev>] [--toolkit-outcome <s>] | --print-parsed-sources\n' "$0" >&2
    exit 2
}

while [ $# -gt 0 ]; do
    case "$1" in
        --hub) hub="$2"; shift 2 ;;
        --toolkit) toolkit="$2"; shift 2 ;;
        --ref) ref="$2"; shift 2 ;;
        --base) base="$2"; shift 2 ;;
        --toolkit-outcome) toolkit_outcome="$2"; shift 2 ;;
        --print-parsed-sources) printf '%s\n' "$PARSED_LIST_SOURCES"; exit 0 ;;
        *) usage ;;
    esac
done

[ -n "$hub" ] && [ -n "$toolkit" ] || usage
[ -z "$base" ] && base="${ref}^1"

# GitHub Actions annotations when run there; plain lines anywhere else.
annotate() { # $1=level $2=path $3=message
    if [ -n "$2" ]; then
        printf '::%s file=%s::%s\n' "$1" "$2" "$3"
    else
        printf '::%s::%s\n' "$1" "$3"
    fi
}

die() { # a verdict this script could not reach is red, never green
    annotate error '' "$1"
    finish blocked 1
}

blocked=0
behind=0
synced=0
behind_paths=''
summary_rows=''

record() { # $1=path $2=state $3=detail
    summary_rows="${summary_rows}| \`$1\` | $2 | $3 |
"
}

finish() { # $1=verdict $2=exit code
    if [ -n "${GITHUB_OUTPUT:-}" ]; then
        {
            printf 'verdict=%s\n' "$1"
            printf 'behind=%s\n' "$(printf '%s' "$behind_paths" | tr '\n' ' ' | sed 's/ $//')"
        } >> "$GITHUB_OUTPUT"
    fi
    if [ -n "${GITHUB_STEP_SUMMARY:-}" ]; then
        {
            printf '### The toolkit'"'"'s vendored copies — verdict: **%s**\n\n' "$1"
            printf '| vendored path | state | detail |\n|---|---|---|\n%s\n' "$summary_rows"
        } >> "$GITHUB_STEP_SUMMARY"
    fi
    exit "$2"
}

[ -d "$hub/.git" ] || [ -f "$hub/.git" ] || die "--hub \`$hub\` is not a git checkout"
[ -d "$toolkit" ] || die "--toolkit \`$toolkit\` is not a directory"
git -C "$hub" rev-parse --verify --quiet "${ref}^{commit}" > /dev/null ||
    die "--ref \`$ref\` does not resolve in \`$hub\`"

# ── What the toolkit vendors: its own word, never a list kept here ──────────────────────────
#
# `scripts/sync-hub-mirrors.mjs` is the toolkit's single definition of what it copies from the
# hub (module-toolkit#115); reading it is what keeps this verdict from watching five files while
# the toolkit vendors six. The path travels in an environment variable ON PURPOSE: that script
# runs its `main()` — a real sync, which fails without a hub — whenever `process.argv[1]` is its
# own path, and `node -e <code> <path>` puts the path exactly there. With no positional argument
# the import has no side effect.
vendored=$(TOOLKIT_SYNC_SCRIPT="$toolkit/scripts/sync-hub-mirrors.mjs" node --input-type=module -e '
  import { pathToFileURL } from "node:url";
  const mod = await import(pathToFileURL(process.env.TOOLKIT_SYNC_SCRIPT).href);
  const list = mod.VENDORED_FROM_THE_HUB;
  if (!Array.isArray(list) || list.length === 0) {
    console.error("VENDORED_FROM_THE_HUB is not a non-empty array");
    process.exit(1);
  }
  console.log(list.join("\n"));
' 2> "${TMPDIR:-/tmp}/mirrors-verdict-import.$$") || {
    detail=$(tr '\n' ' ' < "${TMPDIR:-/tmp}/mirrors-verdict-import.$$" | cut -c1-300)
    rm -f "${TMPDIR:-/tmp}/mirrors-verdict-import.$$"
    die "could not read VENDORED_FROM_THE_HUB from \`$toolkit/scripts/sync-hub-mirrors.mjs\` — the toolkit no longer says what it vendors, so nothing here can be compared ($detail)"
}
rm -f "${TMPDIR:-/tmp}/mirrors-verdict-import.$$"

# Whether a blob ever sat at `path` in the history reachable from `ref`.
#
# `--full-history` is not optional. On a pull request `ref` is the merge of the base branch into
# the PR; when the PR already carried the base's hunk (a cherry-pick, the same route added twice)
# that merge is TREESAME to the PR side and the default simplification of `rev-list -- <path>`
# follows ONLY that parent — the base branch's version of the file, which is exactly what the
# toolkit copied, would come out as "never in the hub" and the canonical would go red with a lie.
in_hub_history() { # $1=blob $2=path
    local commit blob_at
    while read -r commit; do
        [ -n "$commit" ] || continue
        blob_at=$(git -C "$hub" rev-parse --verify --quiet "$commit:$2" 2> /dev/null || true)
        if [ "$blob_at" = "$1" ]; then
            return 0
        fi
    done <<EOF
$(git -C "$hub" rev-list --full-history "$ref" -- "$2")
EOF
    return 1
}

is_gate_input() { # $1=path
    printf '%s\n' "$GATE_INPUTS" | grep -qx -- "$1"
}

pair_hint='the copy must change in the same step: declare `Depends-On: ERPlora/module-toolkit#N` in the PR body and merge the pair with `MERGE_PR_PAIR` (ERPlora/pm#181, pm#183)'
resync_hint='it follows after the merge: in ERPlora/module-toolkit run `npm run sync-mirrors` and open the resync PR'

while read -r path; do
    [ -n "$path" ] || continue
    hub_blob=$(git -C "$hub" rev-parse --verify --quiet "$ref:$path" 2> /dev/null || true)
    toolkit_blob=''
    if [ -f "$toolkit/$path" ]; then
        toolkit_blob=$(git -C "$hub" hash-object --no-filters "$toolkit/$path")
    fi

    if [ -z "$hub_blob" ] && [ -z "$toolkit_blob" ]; then
        annotate error "$path" "\`$path\` is vendored by the toolkit but exists in neither repository — fix the toolkit's VENDORED_FROM_THE_HUB"
        blocked=$((blocked + 1)); record "$path" 'MISSING' 'in neither repository'
        continue
    fi

    if [ "$hub_blob" = "$toolkit_blob" ]; then
        synced=$((synced + 1)); record "$path" 'synced' ''
        continue
    fi

    if [ -z "$hub_blob" ]; then
        annotate error "$path" "a retirement: the hub drops \`$path\` and the toolkit's copy still carries it — $pair_hint"
        blocked=$((blocked + 1)); record "$path" 'RETIRED' 'file dropped in the hub; the copy still has it'
        continue
    fi

    if is_gate_input "$path"; then
        annotate error "$path" "the toolkit's copy of \`$path\` differs from the hub's, and the module gate reads this file to validate what gets published: a copy behind it lets modules through that the hub refuses — $pair_hint"
        blocked=$((blocked + 1)); record "$path" 'STRICT' 'gate input: byte for byte, with the pair'
        continue
    fi

    if [ -z "$toolkit_blob" ]; then
        annotate warning "$path" "the toolkit does not vendor \`$path\` yet (a new surface) — $resync_hint"
        behind=$((behind + 1)); behind_paths="${behind_paths}${path}
"
        record "$path" 'behind' 'not vendored yet'
        continue
    fi

    if ! in_hub_history "$toolkit_blob" "$path"; then
        annotate error "$path" "the toolkit's copy of \`$path\` carries content this hub NEVER had at any commit reachable from $ref: the copy diverged (edited by hand?) and no hub PR can fix that — restore it in ERPlora/module-toolkit with \`npm run sync-mirrors\`"
        blocked=$((blocked + 1)); record "$path" 'DIVERGENT' 'content never in the hub'
        continue
    fi

    numstat=$(git -C "$hub" diff --numstat "$toolkit_blob" "$hub_blob" | head -n 1)
    added=$(printf '%s' "$numstat" | cut -f1)
    removed=$(printf '%s' "$numstat" | cut -f2)
    case "$removed" in
        0)
            annotate warning "$path" "the toolkit's copy of \`$path\` is behind the hub by ${added} added line(s), nothing removed — $resync_hint. Until then the module gate does not see the addition, which is the safe direction"
            behind=$((behind + 1)); behind_paths="${behind_paths}${path}
"
            record "$path" 'behind' "+${added} lines, additive"
            ;;
        *)
            annotate error "$path" "a retirement: the hub removes ${removed} line(s) of \`$path\` that the toolkit's copy still promises (${added} added) — $pair_hint"
            blocked=$((blocked + 1)); record "$path" 'RETIRED' "-${removed} lines"
            ;;
    esac
done <<EOF
$vendored
EOF

if [ "$blocked" -gt 0 ]; then
    annotate error '' "$blocked vendored path(s) block this change; $behind behind, $synced in sync"
    finish blocked 1
fi

# ── The toolkit's own run, re-read ──────────────────────────────────────────────────────────
case "$toolkit_outcome" in
    '' | success)
        ;;
    failure)
        # What this change touched that the toolkit ports BY HAND — named first, whether or not a
        # copy is behind, so the red says which file and not "read the log". Two kinds:
        #   · the Rust/TS sources of the hand-ported lists (`PARSED_LIST_SOURCES`);
        #   · the SET of files under `contracts/kernel/`: the toolkit enumerates it by hand
        #     (`KERNEL_CONTRACT_FILES` + `KERNEL_CONTRACT_NOT_MIRRORED`, module-toolkit#115/#121),
        #     asserts the hub's directory against it and copies only what it names — so a sixth
        #     surface is a change of that list, not a copy that can catch up on its own.
        #     Additions and deletions only (`--no-renames` so a rename counts as both): editing
        #     the README the toolkit deliberately does not mirror is not a change of the set.
        touched=''
        if git -C "$hub" rev-parse --verify --quiet "${base}^{commit}" > /dev/null; then
            # Word-splitting is the point: one pathspec per line of the list.
            # shellcheck disable=SC2086
            touched=$(git -C "$hub" diff --name-only "$base" "$ref" -- $PARSED_LIST_SOURCES)
            kernel_set=$(git -C "$hub" diff --name-only --no-renames --diff-filter=AD "$base" "$ref" -- 'contracts/kernel/')
            if [ -n "$kernel_set" ]; then
                touched="${touched}${touched:+
}${kernel_set}"
            fi
        fi
        if [ -n "$touched" ]; then
            die "the toolkit's mirrors failed and this change also touches $(printf '%s' "$touched" | tr '\n' ' '), whose toolkit mirrors are hand-ported lists this verdict cannot classify (the set of \`contracts/kernel/\` is one of them) — $pair_hint"
        fi
        if [ "$behind" -eq 0 ]; then
            die "the toolkit's mirrors failed for another reason than a lagging copy (every vendored file is in sync): a hand-ported list or its reader — read the toolkit step's log"
        fi
        git -C "$hub" rev-parse --verify --quiet "${base}^{commit}" > /dev/null ||
            die "the toolkit's mirrors failed and \`$base\` does not resolve, so which sources this change touched is unknown — checking out with history (fetch-depth: 0) is what makes this decidable"
        annotate notice '' "the toolkit's mirrors failed only because its copies are behind an additive change: not a reason to block the canonical (hub#1296)"
        ;;
    *)
        die "the toolkit's mirrors step did not run (outcome: \`$toolkit_outcome\`), so the hand-ported lists went unchecked — no verdict without it"
        ;;
esac

if [ "$behind" -gt 0 ]; then
    printf '→ %d vendored path(s) behind, %d in sync: the copy follows after the merge\n' "$behind" "$synced"
    finish behind 0
fi
printf '→ %d vendored path(s) in sync with the hub\n' "$synced"
finish synced 0
