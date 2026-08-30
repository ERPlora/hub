#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Contract test for `.github/workflows/test-web.yml` + `apps/web/package.json`
# — the wiring that makes the Playwright suite RUN somewhere (hub#1240).
#
# Why a test and not a code review: the six specs in `apps/web/tests/e2e/` were
# written, reviewed and merged, and then executed by nobody — no npm script, no
# workflow, no hook. Nothing was broken; a wire was simply missing, and a missing
# wire leaves no red anywhere. The only thing that can notice it is an assertion
# on the wire itself.
#
# It also pins the two triggers that made the hole invisible:
#   · `push: develop` — `test-web.yml` only ran on `main`, so hub#1200 (a red web
#     test) sat on `develop` unseen; `test-hub.yml` has had this trigger since
#     hub#572 and this file was never brought in line.
#   · the alert issue — a red post-merge run notifies nobody by itself
#     (image-freshness.yml, hub#652, proved Actions notifications reach no one).
#   · `HUB_CLOUD_API_URL` on the runtime `webServer` (hub#1279) — without it,
#     `cloud_base_url` falls back to PRODUCTION (`erplora.com`) and the bench
#     calls it FROM THE CI RUNNER, exactly what happened before hub#1277 pinned
#     this one env var. A missing env var leaves no red either, same as above.
#
# Run:  bash scripts/tests/test-web-workflow.test.sh
#
# Dependency-free on purpose (bash + awk + grep + python3's stdlib `json`): it
# runs as a step of `test-web.yml` itself, on `ci-runner-1` as well as on
# GitHub's image, and PyYAML is not guaranteed on either.
# ─────────────────────────────────────────────────────────────────────────────
set -uo pipefail

repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
workflow="$repo_root/.github/workflows/test-web.yml"
package_json="$repo_root/apps/web/package.json"
playwright_config="$repo_root/apps/web/tests/playwright.config.ts"

pass=0
fail=0

ok()  { printf '  \033[32m✓\033[0m %s\n' "$1"; pass=$((pass + 1)); }
bad() { printf '  \033[31m✗\033[0m %s\n     %s\n' "$1" "$2"; fail=$((fail + 1)); }

# The `on:` mapping of the workflow: from the top-level `on:` key to the next
# top-level key. Grepping the whole file would accept the word "develop" from a
# comment or from an unrelated step, which is exactly the assertion that lies.
on_block() {
    awk '/^on:/ {inside=1; next} inside && /^[A-Za-z]/ {exit} inside {print}' "$workflow"
}

# One sub-block of `on:` (e.g. `push`), from `  <name>:` to the next 2-space key.
on_sub_block() { # $1 = name
    on_block | awk -v key="  $1:" '
        $0 == key {inside=1; next}
        inside && /^  [A-Za-z]/ {exit}
        inside {print}
    '
}

echo "test-web.yml — contrato del gate del web (hub#1240)"

# ── 1. The npm script the workflow (and a developer) invokes ─────────────────
e2e_script=$(python3 -c '
import json, sys
with open(sys.argv[1], encoding="utf-8") as fh:
    print(json.load(fh).get("scripts", {}).get("test:e2e", ""))
' "$package_json" 2>/dev/null)

if [ -z "$e2e_script" ]; then
    bad "apps/web/package.json define el script \`test:e2e\`" \
        "no hay \`scripts.test:e2e\`: la suite Playwright no la invoca nadie"
elif ! printf '%s' "$e2e_script" | grep -q 'playwright test'; then
    bad "el script \`test:e2e\` corre Playwright" \
        "\`test:e2e\` = '$e2e_script' (no invoca \`playwright test\`)"
elif ! printf '%s' "$e2e_script" | grep -q 'tests/playwright.config.ts'; then
    bad "el script \`test:e2e\` usa tests/playwright.config.ts" \
        "\`test:e2e\` = '$e2e_script' (sin \`-c tests/playwright.config.ts\` corre con el config por defecto y no encuentra los specs)"
else
    ok "apps/web/package.json → \`test:e2e\` corre Playwright con tests/playwright.config.ts"
fi

# ── 2. The workflow runs it ──────────────────────────────────────────────────
if grep -q 'test:e2e' "$workflow"; then
    ok ".github/workflows/test-web.yml ejecuta \`test:e2e\`"
else
    bad ".github/workflows/test-web.yml ejecuta \`test:e2e\`" \
        "ningún paso invoca \`test:e2e\`: los specs de apps/web/tests/e2e/ no los corre nadie"
fi

# ── 3. …with browsers installed (a runner has none by default) ───────────────
if grep -q 'playwright install' "$workflow"; then
    ok "el job e2e instala los navegadores (\`playwright install\`)"
else
    bad "el job e2e instala los navegadores (\`playwright install\`)" \
        "sin \`playwright install\` el runner no tiene Chromium y el job muere antes del primer spec"
fi

# ── 4. Post-merge trigger on develop (hub#572 lo tiene; este fichero no) ─────
push_block=$(on_sub_block push)
if [ -z "$push_block" ]; then
    bad "test-web.yml se dispara en push" "no hay bloque \`push:\` en \`on:\`"
elif ! printf '%s' "$push_block" | grep -q 'develop'; then
    bad "test-web.yml se dispara en push a develop" \
        "\`on.push.branches\` no incluye develop: un test web rojo en develop no lo ve nadie (hub#1200)"
elif ! printf '%s' "$push_block" | grep -q 'main'; then
    bad "test-web.yml se sigue disparando en push a main" \
        "\`on.push.branches\` perdió main"
else
    ok "on.push.branches incluye main y develop"
fi

# ── 5. The develop-broken alert issue (hub#572/#652) ─────────────────────────
if ! grep -q "refs/heads/develop" "$workflow"; then
    bad "el paso de alerta se limita a push sobre develop" \
        "no hay guarda \`github.ref == 'refs/heads/develop'\`: la alerta se abriría también desde PRs y main"
# El paso ya no llama a `gh issue` a mano: delega en el lookup compartido (hub#1327). El grep
# excluye las líneas de comentario (`^[^#]*`) — si no, un comentario que MENCIONE el script
# satisfaría la guarda con el paso borrado, que es justo el fallo de hub#1365.
elif ! grep -qE '^[^#]*\./scripts/ci/alert-issue\.sh' "$workflow"; then
    bad "el fallo post-merge en develop abre/refresca una issue de alerta" \
        "ningún paso llama a \`./scripts/ci/alert-issue.sh\`: un rojo en develop solo notifica a Actions, o sea a nadie (hub#652)"
elif ! grep -q 'issues: write' "$workflow"; then
    bad "el job puede escribir issues" \
        "falta \`issues: write\` en \`permissions\`: el paso de alerta fallaría con 403"
else
    ok "un fallo post-merge en develop abre o refresca la issue de alerta"
fi

# ── 6. The baseline update path (hub#1240) ───────────────────────────────────
dispatch_block=$(on_sub_block workflow_dispatch)
if ! printf '%s' "$dispatch_block" | grep -q 'update_baselines'; then
    bad "workflow_dispatch ofrece la entrada \`update_baselines\`" \
        "sin ella no hay forma de regenerar las capturas DONDE CORREN (Linux): las de un Mac nunca casan"
elif ! grep -q 'update-snapshots' "$workflow"; then
    bad "la vía de actualización corre Playwright con --update-snapshots" \
        "\`update_baselines\` no llega a \`--update-snapshots\`: no regeneraría nada"
elif ! grep -q 'upload-artifact' "$workflow"; then
    bad "la vía de actualización sube las capturas como artefacto" \
        "sin \`upload-artifact\` los PNG regenerados mueren con el runner y nadie puede commitearlos"
else
    ok "workflow_dispatch → update_baselines regenera las capturas y las sube como artefacto"
fi

# ── 7. This very file runs somewhere (the sin it exists to punish) ───────────
if grep -q 'scripts/tests/test-web-workflow.test.sh' "$workflow"; then
    ok "test-web.yml corre este mismo contrato"
else
    bad "test-web.yml corre este mismo contrato" \
        "este fichero no lo ejecuta ningún workflow — exactamente el defecto que hub#1240 arregla"
fi

# ── 8. The runtime `webServer` never falls back to production (hub#1279) ─────
# `webServer` is an array: the first entry starts the Rust runtime (`cargo run`)
# and the second starts Vite (`pnpm exec vite`). Only the runtime's `env` block
# matters here, so it's sliced out up to the vite entry's `command` line —
# grepping the whole file would also accept `HUB_CLOUD_API_URL` sitting in the
# vite block (which the runtime never reads) or in a comment.
runtime_webserver_block() {
    awk '
        /webServer: *\[/ {inside=1}
        /command: .pnpm exec vite/ {exit}
        inside {print}
    ' "$playwright_config"
}

if [ ! -f "$playwright_config" ]; then
    bad "existe apps/web/tests/playwright.config.ts" \
        "no se encontró el fichero — no hay banco que pueda arrancar el runtime"
else
    runtime_block=$(runtime_webserver_block)
    if [ -z "$runtime_block" ]; then
        bad "el webServer del runtime tiene un bloque \`env\`" \
            "no se pudo aislar el primer \`webServer\` (¿cambió la forma del fichero?) — revisa \`runtime_webserver_block\`"
    elif ! printf '%s' "$runtime_block" | grep -q 'HUB_CLOUD_API_URL'; then
        bad "el webServer del runtime fija HUB_CLOUD_API_URL" \
            "sin ella \`cloud_base_url\` cae al default de PRODUCCIÓN (\`https://erplora.com\`, hub#1279): el banco llamaría a erplora.com DESDE EL RUNNER, tal como pasó antes de hub#1277"
    elif printf '%s' "$runtime_block" | grep -Eq "HUB_CLOUD_API_URL: *['\"]https://erplora\.com"; then
        bad "HUB_CLOUD_API_URL del banco no apunta a producción" \
            "el webServer del runtime fija HUB_CLOUD_API_URL a la propia URL de PRODUCCIÓN — un valor \"puesto\" que sigue llamando a erplora.com no cierra hub#1279"
    else
        ok "el webServer del runtime fija HUB_CLOUD_API_URL a algo que no es producción (hub#1279)"
    fi
fi

printf '\n%d passed, %d failed\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
