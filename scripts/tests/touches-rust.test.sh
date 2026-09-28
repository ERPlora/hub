#!/usr/bin/env bash
# Contract of scripts/ci/touches-rust.sh — run with:  bash scripts/tests/touches-rust.test.sh
#
# Why (26/09, tanda 20260926-145053): `test-hub.yml` ran the whole Rust suite (clippy 3 min +
# `cargo test --workspace` 44 min) on EVERY pull request, and 43 of the 60 hub PRs opened since
# 24/09 touched no Rust at all (web, docs, scripts). Each one held a self-hosted runner for ~47
# minutes to prove nothing, and the module PRs queued behind them. The classifier answers ONE
# question for a PR: does any changed path feed something the Rust suite compiles or READS?
#
# The second half is the guard that keeps it honest: Rust tests read files OUTSIDE `crates/`
# (`apps/web/index.html`, `contracts/kernel/routes.snapshot`, `postman/…`, `schemas/…`,
# `ARQUITECTURA.md`…). A PR that only edits one of those must still run the suite, so every such
# path found in the Rust sources has to be classified as Rust — or this file goes red and names it.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CLS="${TOUCHES_RUST:-$ROOT/scripts/ci/touches-rust.sh}"
pass=0; fail=0
ok(){ printf '  \033[32m✓\033[0m %s\n' "$1"; pass=$((pass+1)); }
bad(){ printf '  \033[31m✗\033[0m %s\n     %s\n' "$1" "$2"; fail=$((fail+1)); }

echo "touches-rust.sh"
[ -f "$CLS" ] || { bad "the classifier exists" "no such file: $CLS"; echo; echo "$pass passed, $fail failed"; exit 1; }

rust(){  # $1=label, rest=paths → must say «touches Rust» (exit 0)
    local label="$1"; shift
    if printf '%s\n' "$@" | bash "$CLS" >/dev/null 2>&1; then ok "$label"; else bad "$label" "classified as NOT Rust: $*"; fi
}
norust(){  # $1=label, rest=paths → must say «no Rust» (exit 1)
    local label="$1"; shift
    local rc; printf '%s\n' "$@" | bash "$CLS" >/dev/null 2>&1; rc=$?
    if [ "$rc" -eq 1 ]; then ok "$label"; else bad "$label" "expected exit 1 (no Rust), got $rc for: $*"; fi
}

# ── 1. what is NOT Rust: the suite has nothing to prove ────────────────────────
norust "a web view"                          apps/web/src/views/SettingsPage.vue
norust "web i18n + a web test"               apps/web/src/i18n/es.json apps/web/src/views/Foo.test.ts
norust "docs and markdown outside the read set" docs/ci.md README.md
norust "a script that is not the CI scope"   scripts/tests/shell-syntax.test.sh
norust "the Android plugin (test-shell.yml runs it; the suite excludes it)" crates/tauri-plugin-erplora-android/src/lib.rs

# ── 2. what IS Rust: compiled, or read by a Rust test ──────────────────────────
rust "a crate source"                        crates/runtime/src/dispatch.rs
rust "a crate test"                          crates/server/tests/never_indexed.rs
rust "the workspace manifest"                Cargo.toml
rust "the lockfile"                          Cargo.lock
rust "the toolchain"                         rust-toolchain.toml
rust "cargo config"                          .cargo/config.toml
rust "a JSON schema (runtime tests read it)" schemas/flow.schema.json
rust "the kernel contract snapshots"         contracts/kernel/routes.snapshot
rust "the postman collection (a server test reads it)" postman/erplora-hub.postman_collection.json
rust "the module SDK sources (a test reads them)" packages/module-sdk/src/index.ts
rust "the shipped index.html (never_indexed.rs reads it)" apps/web/index.html
rust "tauri.conf.json (cloud_csp.rs reads it)" apps/tauri/src-tauri/tauri.conf.json
rust "ARQUITECTURA.md (a peripherals test reads it)" ARQUITECTURA.md
rust "the workflow that runs the suite"      .github/workflows/test-hub.yml
rust "the classifier itself"                 scripts/ci/touches-rust.sh
rust "one Rust path among web paths is enough" apps/web/src/a.vue crates/db/src/lib.rs

# ── 3. fail SAFE ───────────────────────────────────────────────────────────────
rust "an EMPTY diff runs the suite (a failed diff must never read as «no Rust»)"

# ── 4. the guard: every path outside crates/ that Rust sources read is classified as Rust ──
# Relative literals (`include_str!("../../../apps/web/index.html")`, `join("../../schemas/…")`)
# are resolved from the file's directory AND from its crate root; repo-relative literals
# (`"contracts/kernel/routes.snapshot"`) are recognised by their first segment being a top-level
# entry of the repo. Anything that lands outside `crates/` and inside the repo must be Rust.
found="$(ROOT="$ROOT" python3 - <<'PY'
import os, re, subprocess
root = os.environ["ROOT"]
tops = {e for e in os.listdir(root) if e not in (".git", "crates", "target", "node_modules")}
lit = re.compile(r'"((?:\.\./)+[A-Za-z0-9_.][^"\s]*|[A-Za-z0-9_.][A-Za-z0-9_.-]*/[^"\s]+)"')
seen = set()
for dirpath, dirs, files in os.walk(os.path.join(root, "crates")):
    dirs[:] = [d for d in dirs if d not in ("target", "node_modules")]
    for f in files:
        if not f.endswith(".rs"):
            continue
        path = os.path.join(dirpath, f)
        rel = os.path.relpath(path, root)
        parts = rel.split(os.sep)
        crate_root = os.sep.join(parts[:2]) if parts[1] != "plugins" else os.sep.join(parts[:3])
        for m in lit.finditer(open(path, encoding="utf-8", errors="ignore").read()):
            s = m.group(1)
            cands = []
            if s.startswith("../"):
                cands = [os.path.normpath(os.path.join(os.path.dirname(rel), s)),
                         os.path.normpath(os.path.join(crate_root, s))]
            elif s.split("/")[0] in tops:
                cands = [os.path.normpath(s)]
            for c in cands:
                if c.startswith("..") or c.startswith("crates" + os.sep) or c == "crates":
                    continue
                if c.split(os.sep)[0] not in tops:
                    continue
                seen.add(c)
for c in sorted(seen):
    print(c)
PY
)" || bad "the guard could scan the Rust sources" "python3 failed"
n=0
while IFS= read -r p; do
    [ -n "$p" ] || continue
    n=$((n+1))
    if printf '%s\n' "$p" | bash "$CLS" >/dev/null 2>&1; then
        ok "read by Rust and classified as Rust: $p"
    else
        bad "read by Rust and classified as Rust: $p" "a Rust source reads «${p}», but a PR touching only it would skip the suite: add it to scripts/ci/touches-rust.sh"
    fi
done <<<"$found"
# Positive control: a scan that finds nothing asserts nothing (the ARQUITECTURA.md and
# apps/web/index.html reads exist today), so zero hits is a broken scanner, not a clean repo.
if [ "$n" -ge 3 ]; then ok "the guard actually found Rust reads outside crates/ ($n)"; else bad "the guard actually found Rust reads outside crates/" "found $n: the scanner no longer matches how the sources are written"; fi

echo
echo "$pass passed, $fail failed"
[ "$fail" -eq 0 ]
