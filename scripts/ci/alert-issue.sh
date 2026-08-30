#!/usr/bin/env bash
# Shared "open or refresh an idempotent alert issue" step for CI workflows.
#
# Regression test for ERPlora/hub#1246: `test-hub.yml` and `image-freshness.yml` located the
# existing open alert issue with `gh issue list --search '"..." in:title'`. `--search` reads
# GitHub's search INDEX, which lags behind reality — it returned ZERO with open issues on
# 2026-08-16 and hit on 2026-08-26 (intermittent, which is worse). Two failures minutes apart
# (a push to `develop` then one to `main`, two module releases back to back) could each miss
# the other's issue and open TWO — the alert stops being idempotent exactly when there is the
# most noise. `test-hub-modules.yml` already fixed this for itself (hub#1239) by listing with
# the REST API and filtering the title LOCALLY; this script is that fix, extracted once so
# every alert step (test-hub, image-freshness, test-hub-modules, test-web, …) shares ONE
# implementation instead of three-or-more copies that can drift apart again.
#
# Usage — everything is an env var, so a `run: |` step never has to shell-escape a title or a
# multi-line body into a single command line:
#
#   REPO          "owner/repo". Defaults to $GITHUB_REPOSITORY.
#   TITLE         the literal title used when the issue is CREATED.
#   MATCH         "exact" (default) or "prefix" — how an EXISTING issue's title is matched.
#   MATCH_VALUE   the stable text matched against. Defaults to TITLE. Pass this explicitly (with
#                 MATCH=prefix) when TITLE carries a dynamic suffix — a `: <subject>`, say —
#                 that changes between runs: matching only the stable prefix is what makes the
#                 lookup idempotent across different subjects. A colon in that suffix is exactly
#                 what broke `--search` (GitHub reads `:` as search syntax); `startswith()` does
#                 not care.
#   LABEL         optional. Applied when the issue is CREATED (never re-applied on refresh, so
#                 removing it by hand is not fought every run), and used to narrow the list
#                 query server-side — `gh issue list --label` filters on the issue's own field,
#                 not the flaky search index, so it is safe to combine with the local title
#                 match instead of relying on the title alone.
#   BODY          the comment/issue body. Read from stdin instead when BODY is unset — so a
#                 caller building a multi-line body can pipe it in rather than cram it into one
#                 environment variable.
#
# `GH_TOKEN`/`GITHUB_TOKEN` auth is inherited from the environment, same as any other `gh` call
# in these workflows — this script does not touch it.
set -euo pipefail

repo="${REPO:-${GITHUB_REPOSITORY:-}}"
if [ -z "$repo" ]; then
    echo "alert-issue.sh: REPO or GITHUB_REPOSITORY is required" >&2
    exit 2
fi

title="${TITLE:-}"
if [ -z "$title" ]; then
    echo "alert-issue.sh: TITLE is required" >&2
    exit 2
fi

match="${MATCH:-exact}"
case "$match" in
    exact | prefix) ;;
    *)
        echo "alert-issue.sh: MATCH must be 'exact' or 'prefix', got '$match'" >&2
        exit 2
        ;;
esac
match_value="${MATCH_VALUE:-$title}"

label="${LABEL:-}"

if [ -n "${BODY+set}" ]; then
    body="$BODY"
elif [ ! -t 0 ]; then
    body="$(cat)"
else
    echo "alert-issue.sh: BODY env var (or piped stdin) is required" >&2
    exit 2
fi
if [ -z "$body" ]; then
    echo "alert-issue.sh: BODY is empty — refusing to open/refresh an issue with no content" >&2
    exit 2
fi

# List and match LOCALLY, never `--search` (hub#1246): that reads GitHub's search index, which
# lags behind reality. The REST list is consistent. `--label` (when given) is a normal field
# filter, not a search — safe to combine with the label narrowing the candidate set before the
# title match decides between them.
#
# The filter runs through `gh`'s OWN `--jq` (a vendored engine — `gh` does not shell out to a
# separate `jq` binary), never a standalone `jq` on PATH: `ci-runner-1` is a bare Ubuntu that
# has already cost this repo real debugging time twice by lacking tools GitHub's hosted
# runners take for granted (`gh` itself and `python`, per `scripts/kotlin-plugin-tests.sh` and
# `.github/workflows/actionlint.yml`) — this script must not add a third. `--jq` takes one flat
# expression with no way to bind a variable the way `jq --arg` would, so `match_value` is
# escaped by hand into a jq string literal (backslash and double-quote only — `startswith`/`==`
# need nothing else escaped).
escaped_value=$(printf '%s' "$match_value" | sed 's/\\/\\\\/g; s/"/\\"/g')
case "$match" in
    exact)  jq_program="[.[] | select(.title == \"$escaped_value\")][0].number // empty" ;;
    prefix) jq_program="[.[] | select(.title | startswith(\"$escaped_value\"))][0].number // empty" ;;
esac

list_args=(issue list --repo "$repo" --state open --limit 500 --json number,title --jq "$jq_program")
if [ -n "$label" ]; then
    list_args+=(--label "$label")
fi

existing=$(gh "${list_args[@]}")

if [ -n "$existing" ]; then
    echo "Refreshing open alert issue #$existing"
    gh issue comment "$existing" --repo "$repo" --body "$body"
else
    echo "Opening a new alert issue"
    create_args=(issue create --repo "$repo" --title "$title" --body "$body")
    if [ -n "$label" ]; then
        create_args+=(--label "$label")
    fi
    gh "${create_args[@]}"
fi
