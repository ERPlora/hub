#!/usr/bin/env bash
# Resolve the module `*.hub.test.py|sh` batteries in the PUBLISHED catalogue and check them
# against the reviewed list in `scripts/ci/module-hub-batteries.txt`.
#
# Prints the module ids that carry a battery to STDOUT, one per line, sorted and DISTINCT — that
# is the worklist a runner hands to `erplora test <dir> --against-hub`. Every diagnostic goes to
# STDERR so it can never be consumed as a module id.
#
# Exit codes: 0 = catalogue and list agree · 1 = they disagree (the verdict) · 2 = environment
# error (no catalogue, no manifest, a declared module that never materialised). The separation is
# the same one `kernel-e2e-targets.sh` draws and it matters for the same reason: a clone that
# failed must never read as "the battery is missing". hub#1294 spent a red job and nine blocked
# PRs on one SSH flake precisely because the wrong layer got blamed.
#
# Regression test for ERPlora/hub#1381; cases in `scripts/tests/module-hub-batteries.test.sh`.
#
# ── WHY THIS EXISTS ─────────────────────────────────────────────────────────────────────────
# hub#1264 moves the e2e that assert MODULE behaviour out of the hub and into each module's own
# `erplora test` battery. The premise is that coverage CHANGES PLACE. On 2026-08-30 it did not:
# hub#1372 deleted `services_package_redeem_e2e.rs` — 391 lines the pre-push gate and this very
# workflow both ran — and its replacement, `services/tests/package_redeem.hub.test.py`, was run by
# NOBODY. Both CIs stayed green, which is what made it expensive: nothing anywhere went red to say
# the coverage had stopped being exercised.
#
# This guard is the other half of `scripts/ci/kernel-e2e-targets.txt`. A slice deletes a line
# THERE and adds the battery that inherited it HERE, in the same PR. That pair of edits is the
# reviewable act — a reviewer reads both sides of the move instead of a deletion that points at
# nothing checkable.
#
# It is BIDIRECTIONAL, like its sibling. A DECLARED battery absent from the published module is
# hub#1381 itself: the e2e is gone and its replacement never landed, so the behaviour is asserted
# nowhere at all. A battery IN THE CATALOGUE that nobody declared is the quieter direction: it
# exists, but no reviewer ever tied it to the coverage it was meant to inherit, so the hub e2e it
# should have retired either lingers or — worse — gets deleted later by someone assuming the
# pairing was checked.
#
# 🔴 WHAT THIS GUARD DOES NOT DO. It proves a battery EXISTS in the published module; it does not
# prove it passes. What RUNS it is `scripts/ci/run-module-hub-batteries.sh`, in the same job
# (`test-hub-modules.yml`, step `run-batteries`), which takes its worklist from here — call this
# script with `--batteries` for the files rather than the module ids. Do not read a green here as
# "the battery passes": read it as "the battery is where the PR that deleted the e2e said it
# would be".
set -uo pipefail

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

catalogue="${ERPLORA_MODULES_DIR:-}"
manifest="$script_dir/module-hub-batteries.txt"

# `--batteries` swaps WHAT the agreeing path prints — one line per BATTERY instead of one per
# module — and nothing else. The runner (`run-module-hub-batteries.sh`) needs the files: it runs
# the `*.hub.test.py|sh` family and nothing else, and it takes them from here so that "what is a
# hub battery" (the name rule AND the `_HUB_BASE_URL` content rule) is written once. The verdict
# is untouched: a disagreement is still exit 1 with an empty stdout, never a worklist.
emit=modules

while [ $# -gt 0 ]; do
    case "$1" in
        --catalogue) catalogue="$2"; shift 2 ;;
        --manifest) manifest="$2"; shift 2 ;;
        --batteries) emit=batteries; shift ;;
        -h | --help)
            printf 'usage: %s [--catalogue <dir>] [--manifest <file>] [--batteries]\n' "$0"
            exit 0
            ;;
        *)
            printf 'usage: %s [--catalogue <dir>] [--manifest <file>] [--batteries]\n' "$0" >&2
            exit 2
            ;;
    esac
done

if [ -z "$catalogue" ]; then
    printf 'module-hub-batteries: no catalogue. Pass --catalogue <dir> or set ERPLORA_MODULES_DIR\n' >&2
    printf '  (the directory `scripts/materialize-published-modules.sh --dest` leaves behind).\n' >&2
    exit 2
fi
if [ ! -d "$catalogue" ]; then
    printf 'module-hub-batteries: no such catalogue directory: %s\n' "$catalogue" >&2
    exit 2
fi
if [ ! -f "$manifest" ]; then
    printf 'module-hub-batteries: no such manifest: %s\n' "$manifest" >&2
    exit 2
fi

# ── What the CATALOGUE says ─────────────────────────────────────────────────────────────────
# The toolkit decides a battery belongs to family `hub` by NAME (`*.hub.test.py|sh`) or by
# CONTENT (it reads `ERPLORA_HUB_BASE_URL` / `<ID>_HUB_BASE_URL`) — `run-batteries.mjs`,
# `HUB_NAME_RE` / `HUB_CONTENT_RE`. Both halves are honoured here: knowing only the naming rule
# would let a hub battery hide behind an ordinary name and go undeclared, which is the silence
# this guard exists to break.
#
# Discovery is deliberately WIDER than the toolkit's, which only looks under `tests/`. A battery
# parked anywhere else can never be run by `erplora test`, so surfacing it as undeclared is the
# point: a discoverer that quietly stops discovering is the same class of lie one level up
# (hub#1327, hub#1359). What is excluded is what the module did not write — vendored
# dependencies, build output, virtualenvs and caches.
discovered=$(
    find "$catalogue" -mindepth 1 -maxdepth 1 -type d -print |
        LC_ALL=C sort |
        while IFS= read -r mod_dir; do
            module=${mod_dir##*/}
            find "$mod_dir" \
                \( -type d \( -name node_modules -o -name dist -o -name venv \
                              -o -name __pycache__ -o -name '.*' \) \) -prune -o \
                -type f \( -name '*.test.py' -o -name '*.test.sh' \) -print 2>/dev/null |
                while IFS= read -r file; do
                    rel=${file#"$mod_dir"/}
                    # The arms are parenthesised — `(pattern)`, not `pattern)` — because this
                    # `case` lives inside a command substitution and bash 3.2, the one macOS
                    # ships, would otherwise read the first `)` as the end of the `$( … )`
                    # (hub#1468). Guard: `scripts/ci/shell-syntax.sh`.
                    case "$rel" in
                        (*.hub.test.py | *.hub.test.sh) ;;
                        (*)
                            # Not named as a hub battery: it only counts if it reaches for the
                            # hub's base URL, the way the toolkit classifies by content.
                            grep -q '_HUB_BASE_URL' "$file" 2>/dev/null || continue
                            ;;
                    esac
                    printf '%s/%s\n' "$module" "$rel"
                done
        done | LC_ALL=C sort
)

# ── What the LIST says ──────────────────────────────────────────────────────────────────────
# `#` comments and blank lines are ignored; surrounding whitespace is trimmed so a stray space
# never turns into a phantom entry.
declared_raw=$(sed -e 's/[[:space:]]*#.*$//' -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//' \
    "$manifest" | grep -v '^$' | LC_ALL=C sort)

failures=""
env_failures=""

# ── Shape first: an entry that is not `<module>/<path>` cannot be checked against anything ──
# Without this it would silently become a module id with no battery, and the verdict would blame
# a missing file instead of the malformed line that caused it.
malformed=$(printf '%s\n' "$declared_raw" | grep -v '^$' | grep -v '/' || true)
if [ -n "$malformed" ]; then
    failures="$failures
  - manifest entries that are not \`<module-id>/<path to the battery>\`:
$(printf '%s\n' "$malformed" | sed 's/^/      /')"
fi

duplicates=$(printf '%s\n' "$declared_raw" | grep -v '^$' | uniq -d)
if [ -n "$duplicates" ]; then
    failures="$failures
  - duplicated entries in the manifest (they would run the module twice, and would let a later
    deletion pass with the other copy still standing):
$(printf '%s\n' "$duplicates" | sed 's/^/      /')"
fi

declared=$(printf '%s\n' "$declared_raw" | grep -v '^$' | uniq)

# ── `# pending-publication: <repo>#<n>` — a NEW battery whose module has not published it yet ──
# Without it a battery that retires no hub e2e could never land: the module's gate
# (module-toolkit#163) refuses it until this list on `develop` declares it, and the "declared but
# not published" direction below refuses the declaration until the module's `main` publishes it
# (kitchen#84). The marker lives on its OWN comment line, right above the entry, because the
# module's gate compares whole lines and a trailing `# …` would hide the declaration from it.
#
# It excuses exactly ONE thing — that entry missing from the catalogue — and names the issue that
# publishes it. A marker without `<repo>#<n>`, or with no entry right below it, is refused: a
# pending line nobody owns, or one that slid onto the wrong entry after an edit, is how the
# hub#1381 direction would go quiet.
pending=""
pending_notes=""
marker_issue=""
while IFS= read -r line || [ -n "$line" ]; do
    trimmed=$(printf '%s' "$line" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')
    if [ -n "$marker_issue" ]; then
        case "$trimmed" in
            ('' | '#'*)
                failures="$failures
  - a \`# pending-publication: $marker_issue\` marker with no entry right below it:
      the marker excuses the line directly under it and nothing else"
                ;;
            (*)
                entry=$(printf '%s' "$trimmed" | sed 's/[[:space:]]*#.*$//')
                pending="$pending$entry
"
                pending_notes="$pending_notes$entry ($marker_issue)
"
                ;;
        esac
        marker_issue=""
    fi
    case "$trimmed" in
        ('# pending-publication:'*)
            marker_issue=$(printf '%s' "${trimmed#\# pending-publication:}" | sed 's/^[[:space:]]*//')
            if ! grep -Eq '^[A-Za-z0-9_./-]+#[0-9]+$' <<<"$marker_issue"; then
                failures="$failures
  - a \`# pending-publication:\` marker must name the issue that publishes the battery as
    \`<repo>#<n>\`, got: '$marker_issue'"
                marker_issue=""
            fi
            ;;
    esac
done <"$manifest"
if [ -n "$marker_issue" ]; then
    failures="$failures
  - a \`# pending-publication: $marker_issue\` marker at the end of the list, with no entry below it"
fi
pending=$(printf '%s' "$pending" | grep -v '^$' | LC_ALL=C sort -u || true)

# ── A declared module that never materialised is the ENVIRONMENT, not the verdict ───────────
# `materialize-published-modules.sh --floor 25` already fails on a catalogue that came up short,
# but a single module missing from an otherwise full catalogue would land here as "its battery is
# gone" — blaming the module for a clone that failed.
missing_modules=""
while IFS= read -r entry; do
    [ -n "$entry" ] || continue
    case "$entry" in */*) ;; *) continue ;; esac
    module=${entry%%/*}
    if [ ! -d "$catalogue/$module" ]; then
        missing_modules="$missing_modules$module
"
    fi
done <<EOF_DECLARED
$declared
EOF_DECLARED
missing_modules=$(printf '%s' "$missing_modules" | grep -v '^$' | LC_ALL=C sort -u || true)

if [ -n "$missing_modules" ]; then
    env_failures="$env_failures
  - DECLARED modules that are not in the catalogue at all — the catalogue is incomplete, so
    nothing can be concluded about their batteries:
$(printf '%s\n' "$missing_modules" | sed 's/^/      /')"
fi

# The entries whose module IS on disk: only those can produce a content verdict.
checkable=$(
    printf '%s\n' "$declared" | grep -v '^$' |
        while IFS= read -r entry; do
            case "$entry" in (*/*) ;; (*) continue ;; esac
            module=${entry%%/*}
            [ -d "$catalogue/$module" ] && printf '%s\n' "$entry"
        done | LC_ALL=C sort
)

missing_all=$(LC_ALL=C comm -23 <(printf '%s\n' "$checkable" | grep -v '^$') \
    <(printf '%s\n' "$discovered" | grep -v '^$'))
missing=$(LC_ALL=C comm -23 <(printf '%s\n' "$missing_all" | grep -v '^$') \
    <(printf '%s\n' "$pending" | grep -v '^$'))
# Pending AND already published: the marker is stale. A notice, never a red — a red here would
# land in the push of whoever comes after the module's merge, the inventory#77 crater.
published_pending=$(LC_ALL=C comm -12 <(printf '%s\n' "$pending" | grep -v '^$') \
    <(printf '%s\n' "$discovered" | grep -v '^$'))
undeclared=$(LC_ALL=C comm -13 <(printf '%s\n' "$declared" | grep -v '^$') \
    <(printf '%s\n' "$discovered" | grep -v '^$'))

if [ -n "$missing" ]; then
    failures="$failures
  - DECLARED but NOT in the published module — the battery that a hub e2e was retired against is
    not there, so that behaviour is now asserted nowhere:
$(printf '%s\n' "$missing" | sed 's/^/      /')"
fi

if [ -n "$undeclared" ]; then
    failures="$failures
  - IN THE PUBLISHED MODULE but not declared — a battery nobody tied to the coverage it inherits:
$(printf '%s\n' "$undeclared" | sed 's/^/      /')"
fi

# The environment verdict wins: with an incomplete catalogue the content comparison is measuring
# a catalogue that is not the one under test.
if [ -n "$env_failures" ]; then
    {
        printf 'module-hub-batteries: the catalogue in %s is INCOMPLETE.\n' "$catalogue"
        printf '%s\n\n' "$env_failures"
        printf 'This is an environment failure, not a verdict on the batteries: re-run the\n'
        printf 'materialisation (`scripts/materialize-published-modules.sh`). If a module was\n'
        printf 'renamed or retired, its deploy key and its lines in the manifest go together.\n'
    } >&2
    exit 2
fi

if [ -n "$failures" ]; then
    {
        printf 'module-hub-batteries: the reviewed list and %s disagree.\n' "$catalogue"
        printf '%s\n\n' "$failures"
        printf 'The list is %s.\n\n' "$manifest"
        printf 'If a hub#1264 slice moved a kernel e2e into a module battery, the SAME PR drops its\n'
        printf 'line from `scripts/ci/kernel-e2e-targets.txt` and adds the battery here. Those two\n'
        printf 'edits together are what makes the move reviewable: a deletion that points at nothing\n'
        printf 'checkable is how 391 lines of `services` coverage ended up running nowhere (hub#1381).\n'
    } >&2
    exit 1
fi

# One line per pending entry, with a stable prefix a reader (or a test) can match: still waiting
# for its module, or already published and carrying a marker that should go.
if [ -n "$pending_notes" ]; then
    printf '%s' "$pending_notes" | grep -v '^$' | while IFS= read -r note; do
        if grep -Fxq "${note%% (*}" <<<"$published_pending"; then
            printf 'module-hub-batteries: stale-pending-publication: %s — published, drop the marker\n' "$note"
        else
            printf 'module-hub-batteries: pending-publication: %s — declared, not run until published\n' "$note"
        fi
    done >&2
fi

# The worklist. By default one line per MODULE, not per battery: a module is ONE unit of work —
# the runner boots a hub for it and runs every battery it carries against that hub, so emitting
# the id twice would boot a kernel twice for nothing. With `--batteries`, one line per battery,
# which is what the runner needs to know WHICH files to execute inside that hub.
#
# Guarded on emptiness, and the exit is EXPLICIT: a bare `grep -v` over no batteries matches
# nothing and returns 1, which would hand the caller a "they disagree" verdict with an empty
# stderr — a red with nothing to read, from a catalogue that agreed perfectly.
if [ -n "$discovered" ]; then
    if [ "$emit" = batteries ]; then
        printf '%s\n' "$discovered"
    else
        printf '%s\n' "$discovered" | sed 's|/.*||' | LC_ALL=C sort -u
    fi
fi
exit 0
