#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Contract test for the `publish-guest-sdk` job of `.github/workflows/build-hub.yml`
# — ERPlora/hub#2119.
#
# WHAT IT GUARDS. A third-party developer writing the server half of a module (a Rust handler
# compiled to WASM) needs `erplora-guest-sdk`. hub#2115 made the crate self-contained
# (`scripts/package-guest-sdk.sh`), but it was published nowhere they could reach: ERPlora/hub is
# private, so the `{ git = …, tag = … }` route of hub#1236 only works for ERPlora itself. The
# destination is crates.io — where every WASM plugin SDK of the market lives (extism-pdk,
# spin-sdk, shopify_function) — so a vendor declares `erplora-guest-sdk = "X.Y.Z"` and nothing else.
#
# The ways this job can silently stop publishing, each of which leaves the release GREEN:
#
#   · running on a branch push           → a crates.io version cannot be deleted (only yanked),
#                                          so publishing from develop would burn version numbers.
#   · publishing the tree's version       → `stamp-version.sh` is what turns the tag into the
#                                          crate version; without it every tag uploads `1.0.0`.
#   · no token / wrong secret name        → `cargo publish` asks for a login and dies; the
#                                          failure has to NAME the missing credential.
#   · `continue-on-error`                 → the release goes green with nothing published.
#   · re-running a tag                    → crates.io answers «already exists»; that version IS
#                                          published, so the re-run must not turn red.
#
# And a red tag run notifies nobody by itself (hub#652): the failure opens/refreshes an alert
# issue through the shared `scripts/ci/alert-issue.sh`.
#
# Run:  bash scripts/tests/publish-guest-sdk-workflow.test.sh
#
# Dependency-free on purpose (bash + awk + grep): it runs as a step of `build-hub.yml` and of
# `actionlint.yml`, on `ci-runner-1` as well as on GitHub's image.
# ─────────────────────────────────────────────────────────────────────────────
set -uo pipefail

repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
workflow="$repo_root/.github/workflows/build-hub.yml"
actionlint_workflow="$repo_root/.github/workflows/actionlint.yml"

CRATE="erplora-guest-sdk"
TOKEN_SECRET="CARGO_REGISTRY_TOKEN"
# The literal crates.io answer to a version that is already there (a re-run of the same tag).
ALREADY_MARKER="already exists"
# Stable prefix of the alert issue's title — the idempotency key of `alert-issue.sh`
# (`MATCH=prefix`), so the `: <version>` suffix never opens a second issue.
ALERT_TITLE="El SDK erplora-guest-sdk no se pudo publicar en crates.io"

pass=0
fail=0

ok()  { printf '  \033[32m✓\033[0m %s\n' "$1"; pass=$((pass + 1)); }
bad() { printf '  \033[31m✗\033[0m %s\n     %s\n' "$1" "$2"; fail=$((fail + 1)); }

# The `publish-guest-sdk:` job block, from its own key to the next job key at the same
# indentation — so a `permissions:` or an `if:` of ANOTHER job never satisfies a check here.
job_block() {
    awk '
        /^  publish-guest-sdk:/ {inside=1; next}
        inside && /^  [A-Za-z]/ {exit}
        inside {print}
    ' "$workflow"
}

# Comment-only lines removed: a comment that EXPLAINS a marker must never satisfy a check about
# the code that handles it.
job_code() { job_block | grep -v '^[[:space:]]*#'; }

echo "hub#2119 — contrato del job publish-guest-sdk de build-hub.yml"

block=$(job_block)
if [ -z "$block" ]; then
    bad "build-hub.yml define el job \`publish-guest-sdk\`" \
        "no hay job \`publish-guest-sdk\`: $CRATE no se publica en ningún sitio al que llegue un tercero"
    printf '\n%d passed, %d failed\n' "$pass" "$fail"
    exit 1
fi
ok "build-hub.yml define el job \`publish-guest-sdk\`"

code=$(job_code)

# ── 1. Only from a release tag, and only after the version guard approved it ─
if grep -qF "if: startsWith(github.ref, 'refs/tags/v')" <<<"$code"; then
    ok "el job solo corre en un tag \`v*\`"
else
    bad "el job solo corre en un tag \`v*\`" \
        "sin la guarda un push a develop publicaría en crates.io, y allí una versión no se borra"
fi

if grep -qE '^[[:space:]]+needs:[[:space:]]*\[?[^#]*build-and-push' <<<"$code"; then
    ok "el job espera a \`build-and-push\` (image-tags.sh ya aprobó el número)"
else
    bad "el job declara \`needs: build-and-push\`" \
        "\`image-tags.sh\` es quien rechaza un tag no semver, repetido o que retrocede; sin esperar, crates.io recibiría ese número"
fi

# ── 2. The crate carries the TAG's number ────────────────────────────────────
if grep -qF './scripts/stamp-version.sh --version' <<<"$code"; then
    ok "el job estampa la versión del tag con scripts/stamp-version.sh"
else
    bad "el job estampa la versión del tag con scripts/stamp-version.sh" \
        "sin estampar, cada tag subiría la versión del árbol (1.0.0) y el segundo tag moriría con «already exists»"
fi

# ── 3. The real publish, of THIS crate, with its credential ──────────────────
publish_lines=$(printf '%s' "$code" | grep -E '^[[:space:]]*(if[[:space:]]+!?[[:space:]]*)?cargo publish' || true)
real_publish=$(grep -v -- '--dry-run' <<<"$publish_lines" || true)
dry_publish=$(grep -- '--dry-run' <<<"$publish_lines" || true)

if [ -z "$real_publish" ]; then
    bad "el job ejecuta \`cargo publish\` de verdad" \
        "no hay ningún \`cargo publish\` sin \`--dry-run\`: la release saldría verde sin publicar nada"
elif grep -qvE -- "(-p|--package)[[:space:]]+$CRATE" <<<"$publish_lines"; then
    bad "todo \`cargo publish\` nombra \`--package $CRATE\`" \
        "sin nombrarlo cargo publicaría el paquete por defecto del workspace, no el SDK"
else
    ok "el job publica \`$CRATE\` (y solo ese paquete)"
fi

if [ -n "$dry_publish" ]; then
    ok "el job ensaya con \`cargo publish --dry-run\` antes de subir"
else
    bad "el job ensaya con \`cargo publish --dry-run\` antes de subir" \
        "el ensayo compila el crate empaquetado contra crates.io: sin él un paquete roto se descubre ya publicado"
fi

if grep -qE "$TOKEN_SECRET:[[:space:]]*\\\$\{\{[[:space:]]*secrets\.$TOKEN_SECRET[[:space:]]*\}\}" <<<"$code"; then
    ok "el paso de publicación cablea $TOKEN_SECRET = secrets.$TOKEN_SECRET"
else
    bad "el paso de publicación cablea $TOKEN_SECRET = secrets.$TOKEN_SECRET" \
        "es la variable que lee \`cargo publish\`; sin ella pide login y muere"
fi

# ── 4. A missing credential is NAMED, not left as cargo's login prompt ───────
if grep -qE "\[[[:space:]]+-z[[:space:]]+\"\\\$\{?$TOKEN_SECRET" <<<"$code"; then
    ok "el job detecta que falta $TOKEN_SECRET antes de intentar publicar"
else
    bad "el job detecta que falta $TOKEN_SECRET antes de intentar publicar" \
        "sin comprobarlo, el rojo es un «please provide a non-empty token» de cargo que no dice qué secreto crear"
fi

# ── 5. A re-run of the same tag is not a failure ─────────────────────────────
if grep -qE "grep[^|]*$ALREADY_MARKER" <<<"$code"; then
    ok "el job CLASIFICA «${ALREADY_MARKER}» en la respuesta de crates.io (re-ejecutar un tag no es rojo)"
else
    bad "el job CLASIFICA «${ALREADY_MARKER}» en la respuesta de crates.io" \
        "relanzar un tag ya publicado pondría en rojo una versión que SÍ está en el registro"
fi

# ── 6. The silencing that must never be the fix ──────────────────────────────
if grep -q 'continue-on-error' <<<"$code"; then
    bad "el job NO lleva \`continue-on-error\`" \
        "silenciarlo deja la release en verde sin publicar nada: el fallo mudo que la regla de entrega prohíbe"
else
    ok "el job no lleva \`continue-on-error\` (un fallo de publicación sigue siendo rojo)"
fi

# ── 7. The failure reaches a human ───────────────────────────────────────────
if grep -qE '^[[:space:]]+issues:[[:space:]]*write' <<<"$code"; then
    ok "el job declara \`issues: write\` para abrir la alerta"
else
    bad "el job declara \`issues: write\`" "sin él \`alert-issue.sh\` no puede abrir la incidencia (403)"
fi

if grep -qF './scripts/ci/alert-issue.sh' <<<"$code"; then
    ok "el fallo abre/refresca la incidencia por scripts/ci/alert-issue.sh"
else
    bad "el fallo abre/refresca la incidencia por scripts/ci/alert-issue.sh" \
        "un run de tag en rojo no avisa a nadie por sí solo (hub#652)"
fi

if grep -qF "$ALERT_TITLE" <<<"$code"; then
    ok "la alerta usa el título estable «${ALERT_TITLE}»"
else
    bad "la alerta usa el título estable «${ALERT_TITLE}»" \
        "MATCH=prefix necesita una clave estable; sin ella cada tag abriría una incidencia nueva"
fi

if grep -q -- '--search' <<<"$code"; then
    bad "la alerta no usa \`gh issue list --search\`" \
        "lee el índice de búsqueda de GitHub, que va por detrás de la realidad (hub#1246)"
else
    ok "la alerta no inlinea \`--search\`"
fi

# ── 8. Nothing in the release still sends vendors down the private git route ─
workflow_code=$(grep -v '^[[:space:]]*#' "$workflow")
if grep -qE 'git = \\"https://github\.com/ERPlora/hub\\"' <<<"$workflow_code"; then
    bad "build-hub.yml ya no anuncia la vía por git tag del hub privado" \
        "sigue imprimiendo \`{ git = \"https://github.com/ERPlora/hub\", … }\`, que un tercero no puede clonar"
else
    ok "build-hub.yml no anuncia la vía por git tag del hub privado"
fi

# ── 9. This contract runs somewhere ──────────────────────────────────────────
runs_in=""
grep -q 'scripts/tests/publish-guest-sdk-workflow.test.sh' "$workflow" 2>/dev/null && runs_in="build-hub.yml"
grep -q 'scripts/tests/publish-guest-sdk-workflow.test.sh' "$actionlint_workflow" 2>/dev/null &&
    runs_in="${runs_in:+$runs_in y }actionlint.yml"
if [ -n "$runs_in" ]; then
    ok "este contrato lo corre $runs_in"
else
    bad "este contrato lo corre algún workflow" \
        "no lo invoca nadie — un guardarraíl que no se ejecuta es una creencia (hub#1240)"
fi

printf '\n%d passed, %d failed\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
