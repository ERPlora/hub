#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Contract test for the `publish-module-sdk` job of `.github/workflows/build-hub.yml`
# — Regression test for ERPlora/hub#1308.
#
# WHAT HAPPENED. Every `v*` tag left the release run RED with the image already in GHCR: the
# job «Publicar @erplora/module-sdk (GitHub Packages)» got `403 Forbidden - PUT
# https://npm.pkg.github.com/@erplora%2fmodule-sdk`. The GitHub UI truncated the reason to
# `Permission permission_…`, and hub#1308 was filed against that truncation: it blamed a
# missing `packages: write` or a mis-scoped package. THE FULL LINE IN THE RUN LOG SAYS
# SOMETHING ELSE:
#
#   Permission permission_denied: Account has reached its billing limit.
#
# and the same run's `GITHUB_TOKEN Permissions` group says `Packages: write`. Nothing in this
# repository was wrong. `ERPlora/hub` is a PRIVATE repo, so the npm package it publishes is a
# PRIVATE package, and private GitHub Packages consume the organisation's paid quota — which
# was exhausted. Only an org-level action (raise the spending limit, or make the package
# public) can lift it; no workflow edit can.
#
# WHY THIS FILE EXISTS. The next person to read `403` on this job will reach for the same wrong
# fix the issue proposed, and every one of those "fixes" makes things worse in a way nothing
# else in the repo would notice:
#
#   · dropping `packages: write`            → the 403 becomes real, and permanent.
#   · dropping `registry-url`/`scope`       → `npm publish` walks to the PUBLIC npmjs registry
#                                             and puts a private repo's SDK in the open, with
#                                             no way back (npm unpublish is 72 h).
#   · dropping `repository` in package.json → GitHub Packages cannot link the package to the
#                                             repo whose GITHUB_TOKEN is presenting itself.
#   · `continue-on-error: true`             → the release goes green while nothing publishes,
#                                             which is the failure mode this project calls a
#                                             `fallo mudo`.
#
# So this pins the wiring that is ALREADY correct, and pins the one thing hub#1308 does change:
# the failure must NAME the billing block instead of leaving `permission_…` for a human to
# guess, and it must reach a human through the shared alert issue — a red tag run notifies
# nobody by itself (the finding `image-freshness.yml` was built on, hub#652).
#
# Run:  bash scripts/tests/publish-module-sdk-workflow.test.sh
#
# Dependency-free on purpose (bash + awk + grep + python3's stdlib `json`): it runs as a step
# of `build-hub.yml` — the release path itself — as well as of `actionlint.yml`, on
# `ci-runner-1` as well as on GitHub's image, and PyYAML is not guaranteed on either.
# ─────────────────────────────────────────────────────────────────────────────
set -uo pipefail

repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
workflow="$repo_root/.github/workflows/build-hub.yml"
package_json="$repo_root/packages/module-sdk/package.json"

REGISTRY="https://npm.pkg.github.com"
SCOPE="@erplora"
# The literal npm/GitHub Packages answer the job has to recognise. Kept here, in the test, so
# the workflow and the guard cannot drift to two different spellings of the same block.
BILLING_MARKER="billing limit"
# Stable prefix of the alert issue's title — the idempotency key `scripts/ci/alert-issue.sh`
# matches on (`MATCH=prefix`), so the dynamic `: <version>` suffix never opens a second issue.
ALERT_TITLE="El SDK @erplora/module-sdk no se pudo publicar en GitHub Packages"

pass=0
fail=0

ok()  { printf '  \033[32m✓\033[0m %s\n' "$1"; pass=$((pass + 1)); }
bad() { printf '  \033[31m✗\033[0m %s\n     %s\n' "$1" "$2"; fail=$((fail + 1)); }

# The `publish-module-sdk:` job block, from its own key to the next job key at the same
# indentation. Grepping the whole workflow would happily accept `packages: write` from the
# `build-and-push` job above — which is exactly the assertion that lies, because that job's
# permission is not the one that was ever in question.
job_block() {
    awk '
        /^  publish-module-sdk:/ {inside=1; next}
        inside && /^  [A-Za-z]/ {exit}
        inside {print}
    ' "$workflow"
}

# The same block with comment-only lines removed: a comment that merely EXPLAINS a marker must
# never be what satisfies a check about the code that handles it.
job_code() { job_block | grep -v '^[[:space:]]*#'; }

echo "hub#1308 — contrato del job publish-module-sdk de build-hub.yml"

block=$(job_block)
if [ -z "$block" ]; then
    bad "build-hub.yml define el job \`publish-module-sdk\`" \
        "no hay job \`publish-module-sdk\`: no se publica el SDK en ningún sitio"
    printf '\nFAIL: %s caso(s) de contrato\n' "$fail"
    exit 1
fi
ok "build-hub.yml define el job \`publish-module-sdk\`"

code=$(job_code)

# ── 1. The permission hub#1308 blamed — present, and it must stay ────────────
if printf '%s' "$code" | grep -qE '^\s+packages:\s*write'; then
    ok "el job declara \`permissions: packages: write\` (lo que hub#1308 creyó que faltaba)"
else
    bad "el job declara \`permissions: packages: write\`" \
        "sin él el PUT a npm.pkg.github.com es 403 de verdad, y permanente"
fi

# ── 2. The registry and the scope: what keeps the SDK OUT of public npmjs ────
if printf '%s' "$code" | grep -qF "registry-url: '$REGISTRY'" ||
    printf '%s' "$code" | grep -qF "registry-url: $REGISTRY"; then
    ok "\`setup-node\` fija registry-url = $REGISTRY"
else
    bad "\`setup-node\` fija registry-url = $REGISTRY" \
        "sin registry-url, \`npm publish\` va al npmjs PÚBLICO: el SDK de un repo privado, en abierto y sin vuelta atrás"
fi

if printf '%s' "$code" | grep -qE "scope:\s*'?$SCOPE'?"; then
    ok "\`setup-node\` fija scope = $SCOPE"
else
    bad "\`setup-node\` fija scope = $SCOPE" \
        "sin scope, el \`.npmrc\` que escribe setup-node no asocia @erplora a $REGISTRY"
fi

# ── 3. The token that authenticates the PUT ──────────────────────────────────
if printf '%s' "$code" | grep -qE 'NODE_AUTH_TOKEN:\s*\$\{\{\s*secrets\.GITHUB_TOKEN\s*\}\}'; then
    ok "el paso de publicación cablea NODE_AUTH_TOKEN = secrets.GITHUB_TOKEN"
else
    bad "el paso de publicación cablea NODE_AUTH_TOKEN = secrets.GITHUB_TOKEN" \
        "es la variable que lee el \`.npmrc\` de setup-node; sin ella el PUT va sin credencial (401)"
fi

# ── 4. `--tag` always explicit: an rc must never move `latest` ───────────────
# Every INVOCATION — command position only. Anchoring at the start of the line would miss the
# `--dry-run` one, which lives inside an `if ! …`; matching the bare words anywhere would instead
# pick up the `echo "::error …"` texts that merely NAME the command, and a message is not a call.
publish_lines=$(printf '%s' "$code" | grep -E '^[[:space:]]*(if[[:space:]]+!?[[:space:]]*)?npm publish' || true)
if [ -z "$publish_lines" ]; then
    bad "el job ejecuta \`npm publish\`" "no hay ninguna línea \`npm publish\` en el job"
elif printf '%s' "$publish_lines" | grep -qvE '\-\-tag'; then
    bad "todo \`npm publish\` lleva \`--tag\` explícito" \
        "sin --tag, una candidata vX.Y.Z-rc.N movería el dist-tag \`latest\` y un \`npm install\` a secas se la llevaría"
else
    ok "todo \`npm publish\` lleva \`--tag\` explícito (una rc no mueve \`latest\`)"
fi

# ── 5. The silencing that must never be the fix ──────────────────────────────
if printf '%s' "$code" | grep -q 'continue-on-error'; then
    bad "el job NO lleva \`continue-on-error\`" \
        "silenciarlo deja la release en verde sin publicar nada: el fallo mudo que la regla de entrega prohíbe (hub#1308)"
else
    ok "el job no lleva \`continue-on-error\` (un fallo de publicación sigue siendo rojo)"
fi

# ── 6. hub#1308: the failure has to NAME the block and reach a human ─────────
# El marcador tiene que estar en una BÚSQUEDA sobre el log, no solo escrito en un mensaje.
# Verificado: con la rama de clasificación anulada (`if false; then`) el literal seguía
# apareciendo en el texto del `::error` y en el cuerpo de la alerta, así que un `grep` del
# marcador a secas daba VERDE con la clasificación muerta — un caso que no probaba nada.
classify_line=$(printf '%s' "$code" | grep -E "grep[^|]*$BILLING_MARKER" || true)
if [ -n "$classify_line" ]; then
    ok "el job CLASIFICA la respuesta del registro buscando '$BILLING_MARKER' en el log de npm"
else
    bad "el job CLASIFICA la respuesta del registro buscando '$BILLING_MARKER' en el log de npm" \
        "es la razón REAL del 403 y la UI la trunca a 'Permission permission_…': sin clasificarla, el siguiente lector vuelve a diagnosticar mal, como hizo hub#1308 (nombrar el marcador en un mensaje NO es clasificarlo)"
fi

if printf '%s' "$code" | grep -qF './scripts/ci/alert-issue.sh'; then
    ok "el fallo de publicación abre/refresca la incidencia por scripts/ci/alert-issue.sh"
else
    bad "el fallo de publicación abre/refresca la incidencia por scripts/ci/alert-issue.sh" \
        "un run de tag en rojo no avisa a nadie por sí solo (hub#652); y el lookup compartido es lo único idempotente (hub#1246)"
fi

if printf '%s' "$code" | grep -q -- '--search'; then
    bad "la alerta no usa \`gh issue list --search\`" \
        "lee el índice de búsqueda de GitHub, que va por detrás de la realidad (hub#1246)"
else
    ok "la alerta no inlinea \`--search\`"
fi

if printf '%s' "$code" | grep -qF "$ALERT_TITLE"; then
    ok "la alerta usa el título estable «${ALERT_TITLE}»"
else
    bad "la alerta usa el título estable «${ALERT_TITLE}»" \
        "MATCH=prefix necesita una clave estable; sin ella cada tag abriría una incidencia nueva"
fi

# ── 7. The package's own half of the contract ────────────────────────────────
pkg=$(python3 -c '
import json, sys
with open(sys.argv[1], encoding="utf-8") as fh:
    d = json.load(fh)
print(d.get("name", ""))
print((d.get("publishConfig") or {}).get("registry", ""))
print((d.get("repository") or {}).get("url", ""))
' "$package_json" 2>/dev/null)

pkg_name=$(printf '%s\n' "$pkg" | sed -n 1p)
pkg_registry=$(printf '%s\n' "$pkg" | sed -n 2p)
pkg_repo=$(printf '%s\n' "$pkg" | sed -n 3p)

if [ "$pkg_name" = "$SCOPE/module-sdk" ]; then
    ok "packages/module-sdk/package.json → name = $SCOPE/module-sdk (el scope coincide con la org)"
else
    bad "packages/module-sdk/package.json → name = $SCOPE/module-sdk" \
        "es '${pkg_name:-<vacío>}': GitHub Packages solo acepta el scope del propietario"
fi

if [ "$pkg_registry" = "$REGISTRY" ]; then
    ok "publishConfig.registry = $REGISTRY"
else
    bad "publishConfig.registry = $REGISTRY" \
        "es '${pkg_registry:-<vacío>}': es el segundo cinturón que impide publicar en npmjs por accidente"
fi

case "$pkg_repo" in
    *github.com/ERPlora/hub*)
        ok "repository.url apunta a github.com/ERPlora/hub (así enlaza Packages el paquete con el repo del token)" ;;
    *)
        bad "repository.url apunta a github.com/ERPlora/hub" \
            "es '${pkg_repo:-<vacío>}': sin ese enlace, el GITHUB_TOKEN del repo no está autorizado sobre el paquete" ;;
esac

# ═════════════════════════════════════════════════════════════════════════════
# BEHAVIOUR — the four outcomes of the publish step, EXECUTED (hub#1308)
#
# Everything above reads the workflow as TEXT. Text is enough to pin the wiring (a
# `packages: write` either is in the job or is not), but it cannot tell whether the
# classification actually WORKS: `grep -qi 'billing limit' /dev/null` and a swap of the
# `blocked_by=billing`/`blocked_by=other` assignments both leave every grep-based case above
# GREEN while the step misreports the cause — which is the exact failure hub#1308 is about.
# So the step's own `run:` script is EXTRACTED FROM THE WORKFLOW (never a copy kept in this
# file: a copy drifts the moment build-hub.yml changes and then proves nothing) and executed
# against a fake `npm` first on PATH, once per outcome. Same recipe `image-tags.test.sh` and
# `alert-issue.test.sh` already use for `gh`; bash + awk + mktemp only, no PyYAML, no network.
# ═════════════════════════════════════════════════════════════════════════════

# The `run:` body of the step whose `id:` is `publish`, de-indented. Anchoring on the `id:`
# (not the step's name, which is prose and translatable) and stopping at the first line that is
# neither blank nor indented into the block keeps the NEXT step out of the extraction.
extract_publish_run() {
    awk '
        /^      - name: / { is_publish = 0; in_run = 0 }
        /^        id: publish$/ { is_publish = 1 }
        is_publish && /^        run: \|$/ { in_run = 1; next }
        in_run && /^$/ { print ""; next }
        in_run && /^          / { sub(/^          /, ""); print; next }
        in_run { in_run = 0; is_publish = 0 }
    ' "$workflow"
}

sandbox=$(mktemp -d)
trap 'rm -rf "$sandbox"' EXIT
step_script="$sandbox/publish-step.sh"
extract_publish_run > "$step_script"

# A silent extraction failure would turn every case below into a vacuous green, so it is a
# hard stop, not a skipped case.
if ! grep -q 'npm publish' "$step_script"; then
    bad "el \`run:\` del paso \`id: publish\` se puede extraer de build-hub.yml" \
        "la extracción no contiene ningún \`npm publish\`: sin ella los casos de conducta no probarían nada"
    printf '\nFAIL: %s caso(s) de contrato en el job publish-module-sdk (hub#1308)\n' "$fail"
    exit 1
fi
ok "el \`run:\` del paso \`id: publish\` se extrae del workflow (nunca una copia que se desincronice)"

mkdir -p "$sandbox/bin"
cat > "$sandbox/bin/npm" <<'FAKE_NPM'
#!/usr/bin/env bash
# Fake `npm`, first on PATH. Records the invocation and answers what the case asked for:
# `--dry-run` gets its own exit code (the `pack` path), the real publish prints the literal
# the registry would have returned and exits with its own code.
printf '%s\n' "$*" >> "$FAKE_NPM_CALLS"
for arg in "$@"; do
    if [ "$arg" = "--dry-run" ]; then
        echo "npm notice Publishing to https://npm.pkg.github.com/ (dry-run)"
        exit "$FAKE_NPM_DRY_RUN_EXIT"
    fi
done
printf '%s\n' "$FAKE_NPM_PUBLISH_OUTPUT"
exit "$FAKE_NPM_PUBLISH_EXIT"
FAKE_NPM
chmod +x "$sandbox/bin/npm"

# The response GitHub Packages actually returned on run 33228750255 — the whole line, the one
# the UI truncated to `Permission permission_…`.
BILLING_403='npm error code E403
npm error 403 403 Forbidden - PUT https://npm.pkg.github.com/@erplora%2fmodule-sdk - Permission permission_denied: Account has reached its billing limit. Contact support or your organization admin to increase the quota.'

case_n=0
run_publish_step() {   # $1 tag, $2 dry-run exit, $3 publish exit, $4 publish output
    case_n=$((case_n + 1))
    CASE_DIR="$sandbox/case-$case_n"
    mkdir -p "$CASE_DIR"
    GITHUB_OUTPUT="$CASE_DIR/output"; : > "$GITHUB_OUTPUT"
    FAKE_NPM_CALLS="$CASE_DIR/npm-calls"; : > "$FAKE_NPM_CALLS"
    STEP_LOG="$CASE_DIR/log"
    export GITHUB_OUTPUT FAKE_NPM_CALLS
    export RUNNER_TEMP="$CASE_DIR"
    export GITHUB_REF_NAME="$1"
    export FAKE_NPM_DRY_RUN_EXIT="$2" FAKE_NPM_PUBLISH_EXIT="$3" FAKE_NPM_PUBLISH_OUTPUT="$4"
    PATH="$sandbox/bin:$PATH" bash "$step_script" > "$STEP_LOG" 2>&1
    STEP_EXIT=$?
}

# Last value written for a step output — the step appends, never rewrites.
step_output() { grep "^$1=" "$GITHUB_OUTPUT" | tail -1 | cut -d= -f2-; }

# ── B1 · The billing 403: classified, NAMED, and still red ───────────────────
run_publish_step v1.1.11 0 1 "$BILLING_403"
errs=""
[ "$STEP_EXIT" -ne 0 ] || errs="$errs sigue-en-verde"
[ "$(step_output blocked_by)" = "billing" ] || errs="$errs blocked_by=$(step_output blocked_by)"
grep -q '::error title=GitHub Packages ha rechazado la publicación por CUOTA' "$STEP_LOG" || errs="$errs sin-::error-de-cuota"
[ -z "$errs" ] \
    && ok "un 403 por cuota: el paso muere en ROJO, marca blocked_by=billing y NOMBRA la cuota" \
    || bad "un 403 por cuota: el paso muere en ROJO, marca blocked_by=billing y NOMBRA la cuota" \
        "$errs — es el fallo de hub#1308: si no se clasifica, la UI solo enseña 'Permission permission_…'"

# ── B2 · Any OTHER registry rejection must NOT be sold as the quota ──────────
run_publish_step v1.1.11 0 1 'npm error code E409
npm error 409 Conflict - PUT https://npm.pkg.github.com/@erplora%2fmodule-sdk - Cannot publish over existing version'
errs=""
[ "$STEP_EXIT" -ne 0 ] || errs="$errs sigue-en-verde"
[ "$(step_output blocked_by)" = "other" ] || errs="$errs blocked_by=$(step_output blocked_by)"
grep -q '::error title=npm publish ha fallado contra GitHub Packages' "$STEP_LOG" || errs="$errs sin-::error-generico"
grep -q 'title=GitHub Packages ha rechazado la publicación por CUOTA' "$STEP_LOG" && errs="$errs lo-vende-como-cuota"
[ -z "$errs" ] \
    && ok "un rechazo que NO es la cuota se marca blocked_by=other y no se vende como cuota" \
    || bad "un rechazo que NO es la cuota se marca blocked_by=other y no se vende como cuota" \
        "$errs — clasificar mal manda al lector a pedir cuota por un conflicto de versión"

# ── B3 · The package cannot even be packed: no real PUT is attempted ─────────
run_publish_step v1.1.11 1 0 ''
errs=""
[ "$STEP_EXIT" -ne 0 ] || errs="$errs sigue-en-verde"
[ "$(step_output blocked_by)" = "pack" ] || errs="$errs blocked_by=$(step_output blocked_by)"
grep -q '::error title=El paquete del SDK no se puede ni empaquetar' "$STEP_LOG" || errs="$errs sin-::error-de-empaquetado"
grep -qv -- '--dry-run' "$FAKE_NPM_CALLS" && errs="$errs publicó-de-verdad-tras-fallar-el-dry-run"
[ -z "$errs" ] \
    && ok "si \`--dry-run\` falla, no se intenta la publicación real y se marca blocked_by=pack" \
    || bad "si \`--dry-run\` falla, no se intenta la publicación real y se marca blocked_by=pack" "$errs"

# ── B4 · The happy path: green, no block, and `latest` for a final version ───
run_publish_step v1.1.11 0 0 '+ @erplora/module-sdk@1.1.11'
errs=""
[ "$STEP_EXIT" -eq 0 ] || errs="$errs exit=$STEP_EXIT"
[ -z "$(step_output blocked_by)" ] || errs="$errs blocked_by=$(step_output blocked_by)"
[ "$(step_output dist_tag)" = "latest" ] || errs="$errs dist_tag=$(step_output dist_tag)"
grep -q -- '^publish --tag latest$' "$FAKE_NPM_CALLS" || errs="$errs npm-sin---tag-latest"
grep -q '::error' "$STEP_LOG" && errs="$errs ::error-en-el-camino-feliz"
[ -z "$errs" ] \
    && ok "publicación correcta de una versión final: verde, sin bloqueo, dist-tag \`latest\`" \
    || bad "publicación correcta de una versión final: verde, sin bloqueo, dist-tag \`latest\`" "$errs"

# ── B5 · A release candidate must never move `latest` ────────────────────────
run_publish_step v1.2.0-rc.3 0 0 '+ @erplora/module-sdk@1.2.0-rc.3'
errs=""
[ "$STEP_EXIT" -eq 0 ] || errs="$errs exit=$STEP_EXIT"
[ "$(step_output dist_tag)" = "next" ] || errs="$errs dist_tag=$(step_output dist_tag)"
grep -q -- '^publish --tag next$' "$FAKE_NPM_CALLS" || errs="$errs npm-sin---tag-next"
grep -q -- '--tag latest' "$FAKE_NPM_CALLS" && errs="$errs la-rc-movería-latest"
[ -z "$errs" ] \
    && ok "una candidata vX.Y.Z-rc.N va al dist-tag \`next\` y NO mueve \`latest\`" \
    || bad "una candidata vX.Y.Z-rc.N va al dist-tag \`next\` y NO mueve \`latest\`" "$errs"

printf '\n'
if [ "$fail" -gt 0 ]; then
    printf 'FAIL: %s caso(s) de contrato en el job publish-module-sdk (hub#1308)\n' "$fail"
    exit 1
fi
printf 'PASS: %s caso(s) de contrato del job publish-module-sdk (hub#1308)\n' "$pass"
