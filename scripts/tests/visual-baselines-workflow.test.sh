#!/usr/bin/env bash
# Contract test for `.github/workflows/visual-baselines.yml` (ERPlora/hub#1250).
#
# What broke without this workflow, once: `test-web.yml`'s own `workflow_dispatch →
# update_baselines: true` path (hub#1240) shares its concurrency group
# (`test-web-${{ github.ref }}`) with EVERY trigger of that file — push, pull_request AND
# workflow_dispatch on the same ref land in the same group, and `cancel-in-progress: true` kills
# the older one. Run 33130949827 (2026-08-28) proved it live: Playwright reported 12 passed with
# `--update-snapshots=all`, and the run still ended `cancelled` — a push to `develop` from another
# batch cancelled it before the artifact step ran. A workflow this easy to cancel by something
# unrelated is not a usable regeneration path.
#
# `visual-baselines.yml` fixes that by living in its own file with its own concurrency group keyed
# on `run_id` (nothing can ever share it) and NO automatic trigger at all — the checks below pin
# exactly the properties that make both of those true, plus the confirmation gate and the pieces
# that make the regeneration itself correct (the right env var, the right flag, the right filter,
# the artifact upload). It is parsed as plain text (grep/awk), not real YAML, matching the sibling
# `test-web-workflow.test.sh` — dependency-free on purpose (bash + awk + grep only).
#
# `--workflow`/`--caller` let this script be pointed at a MUTATED copy to prove it catches the
# positive (see the manual run in the PR description for hub#1250).
#
# Run:  bash scripts/tests/visual-baselines-workflow.test.sh

set -uo pipefail

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repo_root=$(CDPATH= cd -- "$script_dir/../.." && pwd)
workflow="$repo_root/.github/workflows/visual-baselines.yml"
caller="$repo_root/.github/workflows/actionlint.yml"
test_web="$repo_root/.github/workflows/test-web.yml"

while [ $# -gt 0 ]; do
    case "$1" in
        --workflow) workflow="$2"; shift 2 ;;
        --caller) caller="$2"; shift 2 ;;
        --test-web) test_web="$2"; shift 2 ;;
        *) printf 'usage: %s [--workflow <path>] [--caller <path>] [--test-web <path>]\n' "$0" >&2; exit 2 ;;
    esac
done

pass=0
fail=0

ok()  { printf '  \033[32m✓\033[0m %s\n' "$1"; pass=$((pass + 1)); }
bad() { printf '  \033[31m✗\033[0m %s\n     %s\n' "$1" "$2"; fail=$((fail + 1)); }

if [ ! -f "$workflow" ]; then
    bad "$workflow existe" "no se encuentra el fichero"
    printf '\n%d passed, %d failed\n' "$pass" "$fail"
    exit 1
fi

echo "visual-baselines.yml — contrato de la regeneración de baselines (hub#1250)"

# The `on:` mapping: from the top-level `on:` key to the next top-level key. Grepping the whole
# file would accept "push" or "pull_request" from a comment, which is exactly the assertion that
# would lie here (the comments above explain both triggers in prose).
on_block() {
    awk '/^on:/ {inside=1; next} inside && /^[A-Za-z]/ {exit} inside {print}' "$workflow"
}

# ── 1. NO automatic trigger — the whole point of a dedicated, explicit workflow ──────────────
on=$(on_block)
if [ -z "$on" ]; then
    bad "visual-baselines.yml declara on:" "no hay bloque \`on:\`"
elif ! grep -q 'workflow_dispatch' <<<"$on"; then
    bad "visual-baselines.yml se dispara por workflow_dispatch" \
        "sin \`workflow_dispatch\` no hay forma de lanzarlo a mano"
elif grep -qE '^\s*push:' <<<"$on"; then
    bad "visual-baselines.yml NO se dispara en push" \
        "un \`push:\` automático puede sobrescribir baselines que nadie ha revisado"
elif grep -qE '^\s*pull_request:' <<<"$on"; then
    bad "visual-baselines.yml NO se dispara en pull_request" \
        "un \`pull_request:\` automático puede sobrescribir baselines que nadie ha revisado"
else
    ok "único trigger: workflow_dispatch (sin push ni pull_request)"
fi

# ── 2. Confirmation gate — a stray dispatch must not silently overwrite anything ─────────────
if ! grep -q 'confirm' "$workflow"; then
    bad "workflow_dispatch pide confirmación explícita" \
        "no hay ninguna entrada \`confirm\`: un dispatch por error sobrescribiría baselines sin avisar"
elif ! grep -qE "inputs\.confirm != 'true'" "$workflow"; then
    bad "el job para en seco si confirm no es true" \
        "no se encontró la guarda \`github.event.inputs.confirm != 'true'\`"
elif ! grep -qE '^\s*exit 1\s*$' "$workflow"; then
    bad "la guarda de confirmación aborta el job (exit 1)" \
        "el paso de confirmación no termina en \`exit 1\`: seguiría al resto de pasos"
else
    ok "workflow_dispatch exige la casilla confirm antes de tocar nada"
fi

# ── 3. Concurrency group unique per run — the exact bug this workflow fixes (hub#1250) ───────
concurrency_block=$(awk '/^concurrency:/ {inside=1; next} inside && /^[A-Za-z]/ {exit} inside {print}' "$workflow")
# The `group:` LINE only — the block also carries explanatory comments that mention "run_id" in
# prose (this very file does, to explain why), and grepping the whole block would pass on the
# comment alone while the actual value regressed to something shared. Only the value counts.
group_line=$(printf '%s' "$concurrency_block" | grep -E '^\s*group:')
if [ -z "$concurrency_block" ]; then
    bad "visual-baselines.yml declara concurrency:" "no hay bloque \`concurrency:\`"
elif [ -z "$group_line" ]; then
    bad "concurrency declara group:" "no se encontró una línea \`group:\` dentro del bloque"
elif ! grep -q 'run_id' <<<"$group_line"; then
    bad "el grupo de concurrencia es único por run (contiene run_id)" \
        "el valor de \`group:\` ('$group_line') no lleva \`run_id\`: puede coincidir con el de otra corrida y una la cancelaría — justo el bug que esto arregla (run 33130949827)"
elif ! grep -q 'cancel-in-progress: false' <<<"$concurrency_block"; then
    bad "cancel-in-progress: false" \
        "sin él, un futuro cambio que reintroduzca un grupo compartido volvería a cancelar la regeneración"
else
    ok "concurrency: grupo único por run_id, cancel-in-progress: false"
fi

# ── 4. The group must not be able to collide with test-web.yml's own group ───────────────────
if [ -f "$test_web" ]; then
    test_web_group=$(awk '/^concurrency:/ {inside=1; next} inside && /^[A-Za-z]/ {exit} inside {print}' "$test_web" | grep 'group:' | sed 's/^ *group: *//')
    this_group=$(printf '%s' "$concurrency_block" | grep 'group:' | sed 's/^ *group: *//')
    if [ -n "$test_web_group" ] && [ "$this_group" = "$test_web_group" ]; then
        bad "el grupo de concurrencia NO coincide con el de test-web.yml" \
            "ambos workflows usan \`$this_group\` — un push a develop volvería a cancelar la regeneración"
    else
        ok "el grupo de concurrencia es distinto del de test-web.yml (\`$test_web_group\`)"
    fi
else
    ok "test-web.yml no encontrado en esta ruta — se omite la comparación de grupos"
fi

# ── 5. The regeneration itself: right env, right flag, right filter, artifact upload ─────────
# The ACTUAL invocation line only — the file's own explanatory comments quote
# `--update-snapshots=all` in prose (this very script's neighbour, hub#1250's run history), and a
# whole-file grep would pass on that quote alone while the real `run:` line regressed under it.
playwright_run_line=$(grep -E '^\s*run: .*playwright test -c tests/playwright\.config\.ts' "$workflow")
if ! grep -q 'HUB_UPDATE_BASELINES: "1"' "$workflow"; then
    bad "el job exporta HUB_UPDATE_BASELINES=1" \
        "sin ella, \`resolveUpdateSnapshotsMode\` (src/lib/visual-baseline-gate.ts) no pasa a 'all' y los specs seguirían saltando el caso"
elif [ -z "$playwright_run_line" ]; then
    bad "hay un paso que invoca playwright test -c tests/playwright.config.ts" \
        "no se encontró ninguna línea \`run:\` con esa invocación"
elif ! grep -q -- '--update-snapshots=all' <<<"$playwright_run_line"; then
    bad "el paso de Playwright usa --update-snapshots=all" \
        "la invocación real ('$playwright_run_line') no lleva \`--update-snapshots=all\`: sin el modo explícito, Playwright no reescribe lo que ya exista y una baseline desfasada seguiría desfasada"
elif ! grep -qE '\bVisual\b' <<<"$playwright_run_line"; then
    bad "el paso de Playwright filtra a los specs *Visual.spec.ts" \
        "la invocación real ('$playwright_run_line') no lleva el filtro \`Visual\`: correría también AssistantGrounded.spec.ts, que necesita una segunda base de datos que este workflow no crea"
elif ! grep -q 'upload-artifact' "$workflow"; then
    bad "las capturas regeneradas se suben como artefacto" \
        "sin \`upload-artifact\` los PNG regenerados mueren con el runner y nadie puede commitearlos"
else
    ok "regenera con HUB_UPDATE_BASELINES=1 + --update-snapshots=all, filtra a *Visual.spec.ts y sube el artefacto"
fi

# ── 6. actionlint.yml RUNS this contract, and fires when only this file changes ─────────────
#
# TWO different properties — "a step executes it" and "a change to it triggers the workflow" —
# asserted one after the other, so whichever one breaks is the one named in the failure.
#
# A single `grep -q '<this file>' actionlint.yml` (what this check did until the merge of develop
# into hub#1325) is a FALSE GREEN: the caller names this script TWICE — once in its `paths:`
# filter and once in the step that runs it — so deleting the step still matched the `paths:` entry
# and the check stayed on ✓. Proven by mutation: with the `run:` step removed, the old check
# reported 6 passed / 0 failed. Same rule the checks above already follow (concurrency,
# `--update-snapshots=all`): assert the LINE that does the work, never any mention of it.
# `canonical-mirrors-workflow.test.sh` splits the same pair of properties for its own caller.
# Tolerated spellings of the working line: block form (`bash ./x`) or inline (`run: bash x`),
# with or without `./`; the `paths:` entry with single, double or no quotes. Anything else is red.
SELF='scripts/tests/visual-baselines-workflow.test.sh'
if [ ! -f "$caller" ]; then
    bad "actionlint.yml runs ${SELF}" \
        "the caller was not found at ${caller}"
elif ! grep -qE "^[[:space:]]*(run:[[:space:]]*)?bash (\\./)?${SELF//./\\.}[[:space:]]*$" "$caller"; then
    bad "actionlint.yml runs ${SELF}" \
        "no step invokes it (\`bash ./${SELF}\`): without that step, a PR that breaks visual-baselines.yml goes unnoticed until the first real dispatch — and naming the file in \`paths:\` alone does NOT run it"
elif ! grep -qE "^[[:space:]]*- [\"']?${SELF//./\\.}[\"']?[[:space:]]*$" "$caller"; then
    bad "actionlint.yml fires when only ${SELF} changes" \
        "the file is missing from the \`paths:\` filter: a PR touching only this test would not execute it"
else
    ok "actionlint.yml runs this contract (real step) and fires when only this test changes (paths)"
fi

# ── 7. The baselines are drawn with the OutfitKit the image SHIPS (hub#2011) ─────────────────
#
# `test-web.yml` compares against the OutfitKit `docker/Dockerfile` resolves (`@latest`, hub#1793),
# but this workflow only ran `pnpm install --frozen-lockfile` — so it redrew the baselines with the
# LOCKFILE's OutfitKit (0.1.72) while the comparison ran against 0.1.81: regenerating by the book
# produced photos that every PR would still fail. Same command as the image, taken from the
# Dockerfile (not retyped here), between the install and the Playwright run.
dockerfile="$repo_root/docker/Dockerfile"
image_resolution=$(awk 'match($0, /pnpm --filter @erplora\/web add @erplora\/outfitkit@[^[:space:]"]+/) { print substr($0, RSTART, RLENGTH); exit }' "$dockerfile")
install_at=$(awk '/^[[:space:]]*run: pnpm install --frozen-lockfile/ {print NR; exit}' "$workflow")
resolve_at=$(awk -v cmd="$image_resolution" 'index($0, cmd) && !/^[[:space:]]*#/ {print NR; exit}' "$workflow")
playwright_at=$(awk '/^[[:space:]]*run: .*playwright test -c tests\/playwright\.config\.ts/ {print NR; exit}' "$workflow")
if [ -z "$image_resolution" ]; then
    bad "la imagen resuelve OutfitKit con un comando reconocible (hub#2011)" \
        "no encuentro \`pnpm --filter @erplora/web add @erplora/outfitkit@…\` en docker/Dockerfile"
elif [ -z "$resolve_at" ]; then
    bad "las baselines se pintan con la OutfitKit que publica la imagen (hub#2011)" \
        "falta \`$image_resolution\`: se regeneran con la OutfitKit del lockfile y test-web.yml compara con otra"
elif [ -z "$install_at" ] || [ -z "$playwright_at" ] || [ "$resolve_at" -le "$install_at" ] || [ "$resolve_at" -ge "$playwright_at" ]; then
    bad "OutfitKit se resuelve ENTRE el install y Playwright (hub#2011)" \
        "orden encontrado — install: ${install_at:-?}, resolución: $resolve_at, playwright: ${playwright_at:-?}"
else
    ok "las baselines se pintan con la OutfitKit que publica la imagen (hub#2011)"
fi

# ── 8. …and they say WHICH OutfitKit drew them (hub#2304) ─────────────────────────────────────
#
# A PR's e2e compares with the OutfitKit in `apps/web/tests/e2e/baselines-outfitkit.txt`, not with
# `latest` (every release that moved a pixel turned every web PR red). So a regeneration must write
# the version it just drew with into that file, AFTER Playwright redrew the photos, and ship the file
# in the same artifact — committed together, the photos and their OutfitKit cannot drift apart.
pin_rel="apps/web/tests/e2e/baselines-outfitkit.txt"
record_at=$(awk -v f="> $pin_rel" 'index($0, f) && !/^[[:space:]]*#/ {print NR; exit}' "$workflow")
upload_at=$(awk '/uses: actions\/upload-artifact/ {print NR; exit}' "$workflow")
upload_block=$(awk -v from="${upload_at:-0}" 'NR >= from && NR < from + 8' "$workflow")
# The whole step that writes the file (from its `- name:` to the next step): a condition on it
# (`if:` copied from test-web.yml, whose `update_baselines` input does not exist here) would skip
# it silently — the artifact still has PNGs, so `if-no-files-found: error` would not fire.
record_step=$(awk -v at="${record_at:-0}" '/^      - / { if (NR > at) exit; buf = "" } { buf = buf $0 "\n" } END { printf "%s", buf }' "$workflow")
if [ -z "$record_at" ]; then
    bad "la regeneración escribe la OutfitKit con la que dibujó en \`$pin_rel\` (hub#2304)" \
        "ningún paso escribe \`> $pin_rel\`: se commitearían PNG nuevos y las PRs los compararían con la OutfitKit vieja"
elif [ -z "$playwright_at" ] || [ "$record_at" -le "$playwright_at" ] || [ -z "$upload_at" ] || [ "$record_at" -ge "$upload_at" ]; then
    bad "la versión se escribe DESPUÉS de Playwright y ANTES de subir el artefacto (hub#2304)" \
        "orden encontrado — playwright: ${playwright_at:-?}, versión: $record_at, subida: ${upload_at:-?}"
elif grep -qE '^[[:space:]]*if:' <<<"$record_step"; then  # a commented `# if:` does not match
    bad "la versión se anota en TODA regeneración, sin condición (hub#2304)" \
        "el paso que escribe \`$pin_rel\` lleva un \`if:\`: puede saltarse y el artefacto saldría con PNG nuevos y sin su OutfitKit"
elif ! grep -qF "$pin_rel" <<<"$upload_block"; then
    bad "el artefacto \`playwright-baselines\` lleva \`$pin_rel\` (hub#2304)" \
        "la subida solo lleva los PNG: el fichero de versión se queda en el runner"
else
    ok "la regeneración deja la OutfitKit con la que dibujó en \`$pin_rel\`, dentro del artefacto (hub#2304)"
fi

printf '\n%d passed, %d failed\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
