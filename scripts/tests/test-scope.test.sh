#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Contract test for `scripts/ci/test-scope.py` — the resolver that decides which
# Rust packages a push's `cargo test` must cover, instead of the whole workspace
# every time.
#
# Why: measured on 2026-08-29, `cargo test --workspace` takes 25 min of a runner
# slot, and the pre-push gate runs on every push of every worker of the fleet.
# The gate has run scoped since hub#1207 and scoped is its default outside
# develop/main since hub#1451 — it is the resolver's ONLY consumer.
#
# It was CI's too, briefly, and that is the second half of this file: `test-hub.yml`
# carried a scope step that branched on `pull_request` after pm#197 took that
# trigger away, so the branch was unreachable and the assertions that pinned it
# were green over nothing. hub#1463 removed the step; the cases at the bottom pin
# what is true instead — CI runs the workspace, always, and nothing branches on an
# event that never arrives.
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

# `--workflow PATH` points the CI-wiring cases at a COPY, so the guard can be proven to catch the
# positive without editing the real file: copy the tree, put the dead scope step back, run this
# against the copy, watch it fail naming it. Same reasoning as `ci-prose-matches-triggers.test.sh`.
workflow="$repo_root/.github/workflows/test-hub.yml"
while [ $# -gt 0 ]; do
    case "$1" in
        --workflow) workflow="$2"; shift 2 ;;
        *) printf 'usage: %s [--workflow PATH]\n' "$0" >&2; exit 2 ;;
    esac
done
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

# ── hub#1463: en CI la suite NO se acota, y eso se AFIRMA en vez de suponerse ────────────────
# Lo que había aquí eran cinco aserciones sobre un contrato imposible: pinaban el paso `scope` de
# `test-hub.yml`, que bifurcaba por `github.event_name == 'pull_request'`. Ese trigger salió del
# `on:` el 2026-08-29 (pm#197), así que la rama de la PR era INALCANZABLE y las cinco pasaban sin
# ejercer nada — el verde de una comprobación que no podía fallar.
#
# El alcance en CI se decide ahora en una frase: a este workflow solo lo disparan `push` a
# develop/main y `workflow_dispatch`, y en los dos se corre el WORKSPACE entero. Quien acota es el
# gate pre-push (hub#1207/#1451), que es también el consumidor vivo del resolutor.
wf="$workflow"

echo "el resolutor tiene un consumidor VIVO: el gate pre-push (hub#1346/#1347)"
grep -q 'scripts/ci/test-scope.py' "$repo_root/.githooks/pre-push" \
    && ok "el hook pre-push llama al resolutor canonico" \
    || bad "nadie consume scripts/ci/test-scope.py: el resolutor y esta bateria sobrarian"
grep -q 'scripts/tests/test-scope.test.sh' "$wf" \
    && ok "test-hub.yml corre esta bateria" \
    || bad "esta bateria no la invoca ningun workflow (hub#1392): no deja rojo en ningun sitio"

echo "hub#1463: ningun PASO de test-hub.yml bifurca por un evento que su on: no produce"
# Sobre el YAML PARSEADO, y con las DOS formas dentro del mismo patron: la expresion de Actions
# y la de bash dentro de un run:, que es la que tenia el paso `scope` y la que no vigilaba nadie.
#
# Solo los PASOS, a proposito. El `if:` a nivel de JOB es la superficie de la regla D de
# `scripts/tests/ci-prose-matches-triggers.test.sh` (hub#1443); duplicarla aqui crearia dos
# guardias que pueden discrepar sobre el mismo fichero, que es la deriva que ya tumbo `main`
# una vez (hub#647). Cada uno vigila su mitad: alli el job, aqui los pasos que deciden el alcance.
python3 - "$wf" > "$tmp/dead" <<'PYEOF'
import re
import sys

import yaml

TRIGGERS = {"pull_request_target", "repository_dispatch", "workflow_dispatch",
            "workflow_call", "pull_request", "schedule", "push"}
QUOTE = "[\x22\x27]"
EVENT = re.compile(r"github\.event_name[^\n]{0,24}?(?:==|!=)\s*" + QUOTE + r"([a-z_]+)" + QUOTE)

doc = yaml.safe_load(open(sys.argv[1], encoding="utf-8"))
# YAML 1.1 turns the bare key `on` into the boolean True — the classic Actions gotcha.
on = doc.get("on", doc.get(True))
real = set(on) if isinstance(on, (dict, list)) else {on}
steps = [step for job in (doc.get("jobs") or {}).values() for step in (job.get("steps") or [])]


def strings(node):
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for key, value in node.items():
            yield from strings(key)
            yield from strings(value)
    elif isinstance(node, list):
        for value in node:
            yield from strings(value)


for text in strings(steps):
    for event in sorted(set(EVENT.findall(text))):
        if event in TRIGGERS and event not in real:
            print("bifurca por %s, pero el on: es %s" % (event, sorted(real)))
PYEOF
# A dead interpreter must not look like a clean file: the redirect creates $tmp/dead empty, so
# without this check a missing PyYAML would pass the case vacuously (ci-prose-matches-triggers
# fails closed on the same dependency).
[ $? -eq 0 ] || bad "the guard itself could not run (python3 with PyYAML is required)"
dead=$(sort -u "$tmp/dead")
[ -z "$dead" ] && ok "ningun paso filtra por un evento imposible" \
    || bad "hay una rama inalcanzable en test-hub.yml" "$dead"

echo "hub#1463: la suite del workspace corre SIEMPRE, sin condicion que la pueda saltar"
python3 - "$wf" > "$tmp/gated" <<'PYEOF'
import sys

import yaml

doc = yaml.safe_load(open(sys.argv[1], encoding="utf-8"))
for job in (doc.get("jobs") or {}).values():
    for step in (job.get("steps") or []):
        if "cargo test" not in (step.get("run") or ""):
            continue
        if step.get("if"):
            print("%s -> if: %s" % (step.get("name", "?"), step["if"]))
PYEOF
[ $? -eq 0 ] || bad "the guard itself could not run (python3 with PyYAML is required)"
gated=$(cat "$tmp/gated")
[ -z "$gated" ] && ok "cargo test --workspace no lleva if:" \
    || bad "un cargo test puede saltarse en silencio" "$gated"

echo "hub#1463: nadie lee una salida del paso borrado"
# Una referencia colgante a steps.<id>.outputs.* NO es un error en Actions: evalua a cadena vacia.
# Un `if:` comparado con 'workspace' seria entonces falso y la suite se saltaria EN SILENCIO, que
# es peor que el paso muerto que se quita.
dangling=$(grep -n "steps\.scope\.outputs" "$wf" || true)
[ -z "$dangling" ] && ok "no quedan referencias a steps.scope.outputs" \
    || bad "referencia colgante: evalua a cadena vacia y salta el paso sin avisar" "$dangling"

echo
echo "$pass passed, $fail failed"
[ "$fail" -eq 0 ]
