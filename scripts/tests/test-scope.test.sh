#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Contract test for `scripts/ci/test-scope.py` — the resolver that decides which
# Rust packages a PR's `cargo test` must cover, so that `test-hub.yml` runs the
# packages a diff can reach instead of the whole workspace on every push.
#
# Why: measured on 2026-08-29, `cargo test --workspace` takes 25 min of a runner
# slot and a PR is re-pushed 2-3 times during review, so HALF of the runner
# minutes of the day were burnt on runs cancelled by the next push. The local
# pre-push gate has run scoped since hub#1207; this brings the same rule to CI.
#
# The contract (same as the gate's, on purpose):
#   · a file owned by a package selects that package AND every package that
#     depends on it, through every kind of edge (dev-dependencies break tests);
#   · anything transversal (Cargo.lock, the workspace manifest, the toolchain,
#     `.cargo/`, `schemas/`) → the whole workspace;
#   · a file under a Rust dir that no package claims → the whole workspace
#     (a crate not yet in `members` is a reason to widen, never to ignore);
#   · no Rust file touched → `none` (nothing to compile);
#   · excluded packages never appear in the selection; if the selection reaches
#     every testable package the answer is `workspace`, not a long `-p` list;
#   · output is three lines: mode, human reason, then one package per line.
#
# Run:  bash scripts/tests/test-scope.test.sh
# ─────────────────────────────────────────────────────────────────────────────
set -uo pipefail

repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
resolver="$repo_root/scripts/ci/test-scope.py"
tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT

pass=0; fail=0
ok()   { pass=$((pass + 1)); echo "  ✓ $1"; }
bad()  { fail=$((fail + 1)); echo "  ✗ $1"; [ -n "${2:-}" ] && echo "      $2"; }

# A tiny workspace: db ← runtime ← server; tauri is excluded like in CI; `tools` is standalone.
cat > "$tmp/meta.json" <<'EOF'
{
  "workspace_root": "/ws",
  "workspace_members": ["db 0.1.0", "runtime 0.1.0", "server 0.1.0", "tauri 0.1.0", "tools 0.1.0"],
  "packages": [
    {"id": "db 0.1.0",      "name": "db",      "manifest_path": "/ws/crates/db/Cargo.toml",      "dependencies": []},
    {"id": "runtime 0.1.0", "name": "runtime", "manifest_path": "/ws/crates/runtime/Cargo.toml", "dependencies": [{"name": "db", "kind": null}]},
    {"id": "server 0.1.0",  "name": "server",  "manifest_path": "/ws/crates/server/Cargo.toml",  "dependencies": [{"name": "runtime", "kind": "dev"}]},
    {"id": "tauri 0.1.0",   "name": "tauri",   "manifest_path": "/ws/apps/tauri/Cargo.toml",     "dependencies": [{"name": "runtime", "kind": null}]},
    {"id": "tools 0.1.0",   "name": "tools",   "manifest_path": "/ws/crates/tools/Cargo.toml",   "dependencies": []}
  ]
}
EOF

resolve() { # <changed files…> → stdout of the resolver (excludes: tauri)
    printf '%s\n' "$@" | HUB_GATE_RUST_DIRS=crates python3 "$resolver" "$tmp/meta.json" tauri
}
mode()     { resolve "$@" | sed -n 1p; }
packages() { resolve "$@" | sed -n '3,$p' | tr '\n' ' ' | sed 's/ $//'; }

echo "resolver exists and is executable python"
[ -f "$resolver" ] && ok "scripts/ci/test-scope.py exists" || bad "scripts/ci/test-scope.py is missing"
PYTHONDONTWRITEBYTECODE=1 python3 -m py_compile "$resolver" 2>/dev/null && ok "compiles" || bad "does not compile"

echo "no Rust touched → none"
[ "$(mode .github/workflows/test-hub.yml docs/x.md)" = none ] && ok "workflow + docs → none" || bad "expected none" "$(resolve .github/workflows/test-hub.yml)"

echo "a leaf package selects itself and its dependents (dev edges included)"
[ "$(mode crates/db/src/lib.rs)" = packages ] && ok "mode packages" || bad "expected packages"
[ "$(packages crates/db/src/lib.rs)" = "db runtime server" ] && ok "db → db runtime server (server via dev-dependency)" || bad "wrong selection" "$(packages crates/db/src/lib.rs)"

echo "excluded packages never appear, even when reached"
case " $(packages crates/runtime/src/lib.rs) " in *" tauri "*) bad "tauri leaked into the selection";; *) ok "tauri excluded";; esac

echo "transversal files widen to the workspace"
for f in Cargo.lock Cargo.toml rust-toolchain.toml .cargo/config.toml schemas/module.schema.json; do
    [ "$(mode "$f")" = workspace ] && ok "$f → workspace" || bad "$f should be workspace" "$(resolve "$f")"
done

echo "a Rust file nobody claims widens to the workspace"
[ "$(mode crates/newcrate/src/lib.rs)" = workspace ] && ok "unclaimed crates/… → workspace" || bad "expected workspace"

echo "reaching every testable package collapses to workspace"
[ "$(mode crates/db/src/lib.rs crates/tools/src/lib.rs)" = workspace ] && ok "db + tools (= all testable) → workspace" || bad "expected workspace" "$(resolve crates/db/src/lib.rs crates/tools/src/lib.rs)"

echo "the reason line is human-readable"
resolve crates/server/src/main.rs | sed -n 2p | grep -qE 'of [0-9]+ packages reachable' && ok "reason names the count" || bad "reason line missing"

echo "en una PR con Rust NO se acota: el check del workspace autoriza el merge (pm#58/#60)"
wf0="$repo_root/.github/workflows/test-hub.yml"
grep -qE "event_name.*==.*pull_request.*mode=workspace|PR con Rust.*workspace" "$wf0" \
    && ok "el workflow fuerza workspace en PRs con Rust" || bad "una PR con Rust podria correr acotada y mentir en el nombre del check"
# Ningun `cargo test` puede correr sin consultar el alcance: si lo hiciera, una PR sin Rust
# volveria a compilar el workspace entero (25 min) para no probar nada.
unguarded=$(awk '
    /^ *- name:/ { step=$0; has_if=0 }
    /^ *if:/     { if (index($0, "steps.scope.outputs.mode")) has_if=1 }
    /run: *cargo test/ { if (!has_if) print step }
' "$wf0")
[ -z "$unguarded" ] && ok "todo cargo test consulta steps.scope.outputs.mode" || bad "hay cargo test sin guardia de alcance" "$unguarded"

echo "test-hub.yml is wired to the resolver"
wf="$repo_root/.github/workflows/test-hub.yml"
grep -q 'scripts/ci/test-scope.py' "$wf" && ok "workflow calls the resolver" || bad "workflow does not call scripts/ci/test-scope.py"
grep -q 'scripts/tests/test-scope.test.sh' "$wf" && ok "workflow runs this test" || bad "workflow does not run this test"
grep -qE "steps\.scope\.outputs\.mode == 'workspace'" "$wf" && ok "the workspace run is gated on the scope" || bad "no workspace gate on the scope"
grep -qE "steps\.scope\.outputs\.mode == 'packages'" "$wf" && ok "the scoped run is gated on the scope" || bad "no packages gate on the scope"

echo
echo "$pass passed, $fail failed"
[ "$fail" -eq 0 ]
