#!/usr/bin/env bash
# touches-rust.sh — does a change set feed anything the Rust suite compiles or READS?
#
#   git diff --name-only HEAD^1 HEAD | scripts/ci/touches-rust.sh
#   exit 0 → yes, run clippy + cargo test · exit 1 → no Rust: the suite has nothing to prove
#
# Used by `test-hub.yml` on pull requests (26/09): 43 of 60 hub PRs since 24/09 touched no Rust
# and each held a self-hosted runner ~47 min for nothing. A push to develop/main never asks: it
# always runs everything (hub#572).
#
# The list is the Rust sources PLUS every file outside `crates/` that a Rust test reads — kept in
# sync by scripts/tests/touches-rust.test.sh, which scans the sources and goes red on any read
# path this script would wave through. When in doubt it says YES: an empty diff (a failed `git
# diff`) runs the suite, because a missed Rust change is a red develop and a wasted run is minutes.
# The Android plugin is left out on purpose: the suite excludes it and test-shell.yml runs it.
set -uo pipefail

seen=0
while IFS= read -r path; do
    [ -n "$path" ] || continue
    seen=1
    case "$path" in
        crates/tauri-plugin-erplora-android/*) ;;
        crates/*|Cargo.toml|Cargo.lock|rust-toolchain.toml|.cargo/*) exit 0 ;;
        schemas/*|contracts/*|postman/*|packages/module-sdk/*) exit 0 ;;
        apps/web/index.html|apps/tauri/src-tauri/tauri.conf.json|ARQUITECTURA.md) exit 0 ;;
        .github/workflows/test-hub.yml|scripts/ci/touches-rust.sh) exit 0 ;;
    esac
done
[ "$seen" -eq 1 ] || exit 0
exit 1
