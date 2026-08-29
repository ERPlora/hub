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

# One job's block under `jobs:` (e.g. `verify`), from `  <name>:` to the next
# 2-space job key. Job-scoped, not file-wide: a whole-file grep would say a
# guard is present because a DIFFERENT job happens to mention the same words
# (caught by mutation testing — removing the checkout override from `verify`
# alone did not fail check 8 until this scoping was added).
job_block() { # $1 = name
    awk -v key="  $1:" '
        $0 == key {inside=1; print; next}
        inside && /^  [A-Za-z0-9_-]+:/ {exit}
        inside {print}
    ' "$workflow"
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
elif ! grep -q 'gh issue' "$workflow"; then
    bad "el fallo post-merge en develop abre/refresca una issue de alerta" \
        "ningún paso llama a \`gh issue\`: un rojo en develop solo notifica a Actions, o sea a nadie (hub#652)"
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

# ── 8. Nightly schedule on develop (hub#1253) ────────────────────────────────
# `crates/**` is deliberately left out of `paths` (see the workflow header): a
# Rust-only merge on develop never triggers this file. Without a `schedule`, a
# runtime regression that breaks the shell does not surface until the next PR
# that touches `apps/web/**`.
schedule_block=$(on_sub_block schedule)
verify_job=$(job_block verify)
e2e_job=$(job_block e2e)
# Each job's checkout must carry BOTH the event guard and the `develop` literal —
# checked PER JOB, not with a whole-file grep: `e2e` alone having the override
# would satisfy a file-wide grep while `verify` (vue-tsc + vitest) silently kept
# testing whatever `main` happens to be, and a scheduled run would then mix
# develop's e2e result with main's typecheck result under one "develop is
# broken" alert.
verify_has_ref=1
e2e_has_ref=1
printf '%s' "$verify_job" | grep -q "event_name == 'schedule'" && printf '%s' "$verify_job" | grep -q "'develop'" || verify_has_ref=0
printf '%s' "$e2e_job" | grep -q "event_name == 'schedule'" && printf '%s' "$e2e_job" | grep -q "'develop'" || e2e_has_ref=0
if [ -z "$schedule_block" ]; then
    bad "test-web.yml has a nightly \`schedule\`" \
        "no \`schedule:\` block under \`on:\`: a runtime change that breaks the shell is not seen until the next PR to the web (hub#1253)"
elif ! printf '%s' "$schedule_block" | grep -q 'cron:'; then
    bad "the \`schedule\` declares a \`cron\`" \
        "\`on.schedule\` exists but without \`cron:\`, so GitHub never fires it"
elif [ "$verify_has_ref" -eq 0 ]; then
    bad "the \`verify\` job's checkout forces develop on the cron" \
        "\`schedule\` only fires the file living on \`main\` (native GitHub behaviour) and by default would check out THAT branch — the opposite of what hub#1253 asks. The \`verify\` job is missing a \`ref:\` conditioned on \`github.event_name == 'schedule'\` that forces \`develop\`"
elif [ "$e2e_has_ref" -eq 0 ]; then
    bad "the \`e2e\` job's checkout forces develop on the cron" \
        "same defect as \`verify\` but on the \`e2e\` job: without the conditional \`ref:\`, the cron would test \`main\` instead of \`develop\`"
else
    ok "on.schedule has a cron and the verify+e2e checkouts force develop on that path"
fi

# ── 9. The alert also covers the cron (hub#1253) ─────────────────────────────
# The `alert-develop` job only checked `github.event_name == 'push'`: a red cron run
# at 3am is seen by nobody (the same hole hub#572/#1239 closed for push).
alert_job=$(job_block alert-develop)
if [ -z "$alert_job" ]; then
    bad "the \`alert-develop\` job exists" "\`  alert-develop:\` was not found in $workflow"
elif ! printf '%s' "$alert_job" | grep -q "event_name == 'schedule'"; then
    bad "the develop-broken alert also fires on \`schedule\`" \
        "\`alert-develop\`'s \`if:\` only checks \`github.event_name == 'push'\`: a red cron run neither opens nor refreshes the alert issue (hub#1253)"
else
    ok "alert-develop also fires when the trigger is \`schedule\`"
fi

# ── 10. The guard's `scripts/**` file triggers the gate (hub#1247) ───────────
# `pnpm verify` runs `node --test scripts/tests/no-dead-packages.test.mjs` as its first
# step (hub#1244), but that file was missing from the push/pull_request `paths`: a PR
# that only touched the guard triggered no check at all.
guard_path="scripts/tests/no-dead-packages.test.mjs"
if ! printf '%s' "$push_block" | grep -qF "$guard_path"; then
    bad "the \`no-dead-packages\` guard triggers test-web.yml on push" \
        "\`on.push.paths\` does not include \`$guard_path\` (hub#1247)"
elif ! printf '%s' "$(on_sub_block pull_request)" | grep -qF "$guard_path"; then
    bad "the \`no-dead-packages\` guard triggers test-web.yml on pull_request" \
        "\`on.pull_request.paths\` does not include \`$guard_path\` (hub#1247)"
else
    ok "\`$guard_path\` is in both push and pull_request \`paths\`"
fi

printf '\n%d passed, %d failed\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
