#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Contract test for the Rust lint gate of the hub — the `[workspace.lints]`
# table + the `cargo clippy` step of `.github/workflows/test-hub.yml`
# (ERPlora/hub#1242, ADR «El Hub se CIERRA como KERNEL»).
#
# Why a test and not a code review: until hub#1242 the hub had ZERO Rust lints.
# No `clippy.toml`, no `deny.toml`, no `[lints]`, no `#![deny]`, and the string
# `clippy` appeared nowhere under `.github/`, `.githooks/` or `scripts/`. The
# only guard was a local, unversioned hook that WARNS about what the AI writes —
# it never saw a human commit and it never failed a build. A missing wire leaves
# no red anywhere, so the only thing that can notice it is an assertion on the
# wire itself (same reasoning as `test-web-workflow.test.sh`, hub#1240).
#
# The contract this file pins:
#   · the workspace declares the lint table, with `correctness` at DENY;
#   · every workspace member opts in with `[lints] workspace = true` — a crate
#     that forgets this line is silently exempt, which is the exact failure mode
#     a per-crate opt-in has;
#   · the workflow runs clippy over `--all-targets` and `--workspace`, BEFORE
#     the test step (a lint error must not wait 20 min behind the suite), and
#     does not swallow its exit code — the levels come from the table, NOT from
#     a blanket `-D warnings`, which would also deny the groups still dirty;
#   · the clippy step mirrors the SAME `--exclude` pair as the test step — those
#     two crates drag GTK/webkit2gtk, which this runner does not have;
#   · this very file is executed by the workflow.
#
# Run:  bash scripts/tests/clippy-lints.test.sh
#
# Dependency-free on purpose (bash + awk + grep): it runs as a step of
# `test-hub.yml` itself, on `ci-runner-1` as well as on GitHub's image.
# ─────────────────────────────────────────────────────────────────────────────
set -uo pipefail

repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
workflow="$repo_root/.github/workflows/test-hub.yml"
root_manifest="$repo_root/Cargo.toml"

pass=0
fail=0

ok()  { printf '  \033[32m✓\033[0m %s\n' "$1"; pass=$((pass + 1)); }
bad() { printf '  \033[31m✗\033[0m %s\n     %s\n' "$1" "$2"; fail=$((fail + 1)); }

# The two crates `test-hub.yml` excludes from `--workspace` runs. The clippy
# step must mirror them or it dies on missing system libs before linting a line.
EXCLUDED_CRATES="erplora-tauri tauri-plugin-erplora-android"

# One TOML table of a manifest, from `[<header>]` to the next top-level `[`.
# Grepping the whole file would accept the words from a comment or from an
# unrelated table — that is the assertion that lies.
toml_table() { # $1 = file, $2 = table header without brackets
    awk -v header="[$2]" '
        $0 == header {inside=1; next}
        inside && /^[[:space:]]*\[/ {exit}
        inside {print}
    ' "$1"
}

# The `run:` body of the step whose `- name:` line contains $1, up to the next
# `- name:` at the same indentation.
workflow_step() { # $1 = substring of the step name
    awk -v needle="$1" '
        /^      - name:/ { inside = (index($0, needle) > 0); next }
        inside { print }
    ' "$workflow"
}

# Line number of the first step whose name contains $1 (0 when absent).
step_line() { # $1 = substring of the step name
    grep -n '^      - name:' "$workflow" | grep -F "$1" | head -1 | cut -d: -f1
}

echo "Lints Rust del hub — contrato del gate de clippy (hub#1242)"

# ── 1. The workspace declares the lint table, correctness at deny ────────────
clippy_lints=$(toml_table "$root_manifest" "workspace.lints.clippy")

if [ -z "$clippy_lints" ]; then
    bad "Cargo.toml declara \`[workspace.lints.clippy]\`" \
        "no hay tabla \`[workspace.lints.clippy]\` en el manifest raíz: sin ella \`[lints] workspace = true\` de cada crate no hereda nada"
elif ! printf '%s\n' "$clippy_lints" | grep -qE '^[[:space:]]*correctness[[:space:]]*=.*"deny"'; then
    bad "\`[workspace.lints.clippy]\` pone \`correctness\` en \`deny\`" \
        "\`correctness\` no está en \"deny\": es el grupo de los bugs de verdad (un \`unwrap()\` mal puesto tumba una caja), y en warn no para nada"
else
    ok "Cargo.toml declara \`[workspace.lints.clippy]\` con \`correctness = deny\`"
fi

# ── 2. The ratchet is documented WHERE it is operated ────────────────────────
# A ratchet nobody knows how to turn stays at its first notch forever.
if printf '%s\n' "$clippy_lints" | grep -qi 'ratchet'; then
    ok "la tabla de lints explica el ratchet (cómo se promociona un grupo)"
else
    bad "la tabla de lints explica el ratchet (cómo se promociona un grupo)" \
        "sin la nota, el siguiente que quiera subir un grupo a \`deny\` no sabe que basta con cambiar el nivel aquí"
fi

# ── 3. EVERY workspace member opts in ────────────────────────────────────────
# `[workspace.lints]` does nothing by itself: each crate must say
# `[lints] workspace = true`. A crate that forgets it is silently exempt.
members=$(toml_table "$root_manifest" "workspace" \
    | awk '/^members[[:space:]]*=/ {inside=1} inside {print} inside && /\]/ {exit}' \
    | grep -oE '"[^"]+"' | tr -d '"')

if [ -z "$members" ]; then
    bad "se pueden leer los miembros del workspace" \
        "no se pudo extraer \`members\` de \`[workspace]\` en el manifest raíz"
else
    missing=""
    for member in $members; do
        manifest="$repo_root/$member/Cargo.toml"
        if [ ! -f "$manifest" ]; then
            missing="$missing $member(sin-manifest)"
            continue
        fi
        if ! toml_table "$manifest" "lints" | grep -qE '^[[:space:]]*workspace[[:space:]]*=[[:space:]]*true'; then
            missing="$missing $member"
        fi
    done
    if [ -n "$missing" ]; then
        bad "todos los miembros del workspace heredan los lints (\`[lints] workspace = true\`)" \
            "sin esa línea el crate queda EXENTO en silencio —$missing"
    else
        ok "los $(printf '%s\n' "$members" | wc -l | tr -d ' ') miembros del workspace llevan \`[lints] workspace = true\`"
    fi
fi

# ── 4. The workflow actually runs clippy ─────────────────────────────────────
clippy_step=$(workflow_step "clippy")

if [ -z "$clippy_step" ] || ! printf '%s\n' "$clippy_step" | grep -q 'cargo clippy'; then
    bad ".github/workflows/test-hub.yml corre \`cargo clippy\`" \
        "ningún paso invoca \`cargo clippy\`: la tabla de lints no la comprueba nadie en CI"
else
    ok ".github/workflows/test-hub.yml corre \`cargo clippy\`"

    # Los niveles los manda `[workspace.lints]` (asserción 1), no un `-D warnings`
    # de brocha gorda: ese flag denegaría también los grupos que siguen sucios y el
    # gate nacería rojo. Lo que hay que asegurar aquí es que el paso no se traga su
    # propio fallo — con `|| true` o `continue-on-error` la tabla no serviría de nada.
    if printf '%s\n' "$clippy_step" | grep -qE '\|\|[[:space:]]*true|continue-on-error'; then
        bad "el paso de clippy NO se traga su código de salida" \
            "lleva \`|| true\` o \`continue-on-error\`: un \`correctness\` denegado saldría igual en verde"
    else
        ok "el paso de clippy no se traga su código de salida"
    fi

    if printf '%s\n' "$clippy_step" | grep -q -- '--all-targets'; then
        ok "el paso de clippy cubre \`--all-targets\` (tests y benches incluidos)"
    else
        bad "el paso de clippy cubre \`--all-targets\`" \
            "sin \`--all-targets\` no mira los tests, que es donde más código nuevo entra"
    fi

    if printf '%s\n' "$clippy_step" | grep -q -- '--workspace'; then
        ok "el paso de clippy cubre \`--workspace\`"
    else
        bad "el paso de clippy cubre \`--workspace\`" \
            "sin \`--workspace\` solo miraría el crate raíz"
    fi

    # ── 5. Same exclusions as the test step (GTK/webkit2gtk, ver el comentario
    #      del paso `cargo test --workspace`) ──────────────────────────────────
    missing_excl=""
    for crate in $EXCLUDED_CRATES; do
        printf '%s\n' "$clippy_step" | grep -q -- "--exclude $crate" || missing_excl="$missing_excl $crate"
    done
    if [ -n "$missing_excl" ]; then
        bad "el paso de clippy repite las exclusiones del paso de tests" \
            "falta --exclude para:$missing_excl — arrastran tauri/wry → GTK/webkit2gtk, que este runner no tiene: el paso moriría antes de lintar una línea"
    else
        ok "el paso de clippy repite las exclusiones del paso de tests (erplora-tauri, plugin Android)"
    fi
fi

# ── 6. Clippy runs BEFORE the suite ──────────────────────────────────────────
# A lint error is instantaneous; the suite takes ~20 min. Behind it, the
# feedback arrives when nobody is looking any more.
clippy_at=$(step_line "clippy")
tests_at=$(step_line "cargo test --workspace")

if [ -z "$clippy_at" ] || [ -z "$tests_at" ]; then
    bad "clippy corre ANTES del paso de tests" \
        "no se localizaron ambos pasos en el workflow (clippy='${clippy_at:-ausente}', tests='${tests_at:-ausente}')"
elif [ "$clippy_at" -ge "$tests_at" ]; then
    bad "clippy corre ANTES del paso de tests" \
        "el paso de clippy está en la línea $clippy_at, después del de tests ($tests_at): el fallo de lint llegaría ~20 min tarde"
else
    ok "clippy corre antes del paso de tests (línea $clippy_at < $tests_at)"
fi

# ── 7. This very file runs somewhere (the sin it exists to punish) ───────────
# The invocation LINE only — never any mention of the file. `test-hub.yml`
# names this script in a header comment too, so a whole-file `grep -q` stayed
# green with the `run:` step deleted (proven by mutation: 10 passed, exit 0).
# Same false green as the visual-baselines contract fixed in hub#1363; the
# family issue is hub#1365 (test-web-workflow.test.sh has the twin).
SELF='scripts/tests/clippy-lints.test.sh'
if grep -qE "^[[:space:]]*(run:[[:space:]]*)?bash (\./)?${SELF//./\\.}[[:space:]]*$" "$workflow"; then
    ok "test-hub.yml corre este mismo contrato (paso real, no una mención)"
else
    bad "test-hub.yml corre este mismo contrato" \
        "ningún paso invoca \`bash ${SELF}\` — exactamente el defecto que hub#1242 arregla; nombrarlo en un comentario no lo ejecuta"
fi

printf '\n%d passed, %d failed\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
