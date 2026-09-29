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
self_path="$repo_root/scripts/tests/test-web-workflow.test.sh"

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
elif ! grep -q 'playwright test' <<<"$e2e_script"; then
    bad "el script \`test:e2e\` corre Playwright" \
        "\`test:e2e\` = '$e2e_script' (no invoca \`playwright test\`)"
elif ! grep -q 'tests/playwright.config.ts' <<<"$e2e_script"; then
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
elif ! grep -q 'develop' <<<"$push_block"; then
    bad "test-web.yml se dispara en push a develop" \
        "\`on.push.branches\` no incluye develop: un test web rojo en develop no lo ve nadie (hub#1200)"
elif ! grep -q 'main' <<<"$push_block"; then
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
if ! grep -q 'update_baselines' <<<"$dispatch_block"; then
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

# ── 7. This very file runs somewhere for REAL, and its own path still triggers ──
#      test-web.yml when only it changes (hub#1365) ─────────────────────────────
# `test-web.yml` names this file THREE times: a header comment, twice in `paths:`
# (push and pull_request) and the step that runs it. A whole-file `grep -q` on the
# bare name treated all three the same, so deleting only the `run:` step still
# matched a `paths:` entry and this check stayed on ✓ — proven by mutation: with
# the step removed, the old one-liner kept reporting the file green. Same split
# `visual-baselines-workflow.test.sh` and `canonical-mirrors-workflow.test.sh`
# already use for their own caller. Tolerated spellings of the working line:
# block form (`bash ./x`) or inline (`run: bash x`), with or without `./`.
SELF='scripts/tests/test-web-workflow.test.sh'
if ! grep -qE "^[[:space:]]*(run:[[:space:]]*)?bash (\\./)?${SELF//./\\.}[[:space:]]*$" "$workflow"; then
    bad "test-web.yml corre este mismo contrato" \
        "ningún paso lo EJECUTA (\`bash ./${SELF}\`) — nombrarlo en un comentario o en \`paths:\` no cuenta, y sin ese paso el resto de esta guardia no corre nunca (hub#1365)"
elif ! grep -qE "^[[:space:]]*- [\"']?${SELF//./\\.}[\"']?[[:space:]]*$" "$workflow"; then
    bad "$SELF sigue en el filtro \`paths:\` de test-web.yml" \
        "sin él, una PR que solo tocara este test no dispararía ningún check"
else
    ok "test-web.yml corre este mismo contrato y sigue en su filtro \`paths:\`"
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
grep -q "event_name == 'schedule'" <<<"$verify_job" && grep -q "'develop'" <<<"$verify_job" || verify_has_ref=0
grep -q "event_name == 'schedule'" <<<"$e2e_job" && grep -q "'develop'" <<<"$e2e_job" || e2e_has_ref=0
if [ -z "$schedule_block" ]; then
    bad "test-web.yml has a nightly \`schedule\`" \
        "no \`schedule:\` block under \`on:\`: a runtime change that breaks the shell is not seen until the next PR to the web (hub#1253)"
elif ! grep -q 'cron:' <<<"$schedule_block"; then
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
elif ! grep -q "event_name == 'schedule'" <<<"$alert_job"; then
    bad "the develop-broken alert also fires on \`schedule\`" \
        "\`alert-develop\`'s \`if:\` only checks \`github.event_name == 'push'\`: a red cron run neither opens nor refreshes the alert issue (hub#1253)"
else
    ok "alert-develop also fires when the trigger is \`schedule\`"
fi

# ── 10. The guard's `scripts/**` file triggers the gate (hub#1247) ───────────
# `pnpm verify` runs `node --test scripts/tests/no-dead-packages.test.mjs` as its first
# step (hub#1244), but that file was missing from the `paths`: a change that only touched
# the guard triggered no check at all.
#
# This asked for `pull_request` too until 2026-08-29, when that trigger was removed on
# purpose (see the header of test-web.yml): the heavy suite runs in the pre-push gate, and
# what survives in the cloud is `push` over the merged tree. Keeping the old assertion
# would demand a trigger the workflow is not supposed to have any more.
guard_path="scripts/tests/no-dead-packages.test.mjs"
if ! grep -qF "$guard_path" <<<"$push_block"; then
    bad "the \`no-dead-packages\` guard triggers test-web.yml on push" \
        "\`on.push.paths\` does not include \`$guard_path\` (hub#1247)"
else
    ok "\`$guard_path\` is in the push \`paths\`"
fi

# ── 10bis. `pull_request` is BACK, with its draft filter (hub#1466, 2026-09-03) ──
# From 2026-08-29 to 2026-09-03 this file asserted the opposite: the heavy suite ran in the
# pre-push gate and a cloud run on PRs was a third execution of the same suite. Measured on
# tanda R2 (02/09): that gate is ONE lock for the whole machine, ~20 min per pass, and every
# reviewer fix pays it again — 6 serial passes were the whole 2 h of the tanda. hub#1466 splits
# it: the local gate keeps only check + fmt + clippy (~27 s warm, no attestation) and the heavy
# suite comes back here, where ci-runner-1 runs 4 at a time. `merge-pr.sh` authorises with THIS
# check when the local attestation is absent (it always did; pm#197 only added the fallback).
#
# What must not come back with it: the 29/08 waste. Half the runner minutes went to runs
# cancelled by the reviewer's re-push on DRAFT PRs, so the trigger returns WITH the draft
# filter on every job that costs minutes — a draft PR is 0 CI minutes until `gh pr ready`.
wf_self="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)/.github/workflows/test-web.yml"
on_txt="$(on_block)"
# Here-strings, never `printf … | grep -q`: under `pipefail`, grep -q closes the pipe at the first
# match and printf dies with "Broken pipe" → a MATCH becomes a failure (red only on Linux; the
# Mac's printf finishes first). Bit us on the first CI run of hub#1471.
pr_sub="$(on_sub_block pull_request)"
if ! grep -qE '^  pull_request:' <<<"$on_txt"; then
    bad "test-web.yml runs on \`pull_request\` again (hub#1466)" \
        "\`on.pull_request\` is missing: the heavy suite moved back to Actions on 2026-09-03 and the local gate no longer attests — without this trigger nothing green ever authorises a web PR"
elif ! grep -qE 'ready_for_review' <<<"$pr_sub"; then
    bad "\`pull_request.types\` includes \`ready_for_review\`" \
        "without it a draft that becomes ready never gets a run (the draft filter skipped the earlier events)"
else
    ok "\`pull_request\` is back, with \`ready_for_review\` in its types"
fi
pr_paths="$(on_sub_block pull_request)"
for p in "apps/web/**" "packages/**" "$guard_path" ".github/workflows/test-web.yml"; do
    grep -qF "$p" <<<"$pr_paths" \
        && ok "\`pull_request.paths\` includes \`$p\`" \
        || bad "\`pull_request.paths\` includes \`$p\`" "a PR touching it would open with no web check"
done
draft_if="github.event_name != 'pull_request' || !github.event.pull_request.draft"
# Every job that runs pnpm/cargo costs minutes and must skip drafts; alert jobs are push-only.
minute_jobs="$(awk '/^jobs:/{f=1;next} f&&/^  [a-z_-]+:$/{sub(/:$/,"",$1); j=$1} f&&j!=""&&/run: *(pnpm|cargo)/{print j; j=""}' "$wf_self" | sort -u)"
[ -n "$minute_jobs" ] || bad "test-web.yml has jobs that run pnpm/cargo" "none parsed — the draft-filter assertion below would be vacuous"
for job in $minute_jobs; do
    job_body="$(awk -v J="  $job:" '$0==J{f=1;next} f&&/^  [a-z-]+:$/{exit} f' "$wf_self")"
    if grep -qF "$draft_if" <<<"$job_body"; then
        ok "job \`$job\` skips draft PRs (\`if:\` with the draft filter)"
    else
        bad "job \`$job\` skips draft PRs" "no \`if: $draft_if\` on the job: a draft PR would burn runner minutes and get cancelled on the reviewer's re-push (measured 29/08: half the minutes)"
    fi
done
if false; then
    :
fi

# ── 11. The runtime `webServer` never falls back to production (hub#1279) ─────
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
    elif ! grep -q 'HUB_CLOUD_API_URL' <<<"$runtime_block"; then
        bad "el webServer del runtime fija HUB_CLOUD_API_URL" \
            "sin ella \`cloud_base_url\` cae al default de PRODUCCIÓN (\`https://erplora.com\`, hub#1279): el banco llamaría a erplora.com DESDE EL RUNNER, tal como pasó antes de hub#1277"
    elif grep -Eq "HUB_CLOUD_API_URL: *['\"]https://erplora\.com" <<<"$runtime_block"; then
        bad "HUB_CLOUD_API_URL del banco no apunta a producción" \
            "el webServer del runtime fija HUB_CLOUD_API_URL a la propia URL de PRODUCCIÓN — un valor \"puesto\" que sigue llamando a erplora.com no cierra hub#1279"
    else
        ok "el webServer del runtime fija HUB_CLOUD_API_URL a algo que no es producción (hub#1279)"
    fi
fi

# ── 12. This file never pipes into a reader that short-circuits (hub#1534) ────
# `printf '%s' "$block" | grep -q PATTERN` under `pipefail` is a guard that lies in
# the WORST direction: `grep -q` exits at the first match and closes the pipe,
# `printf` takes EPIPE and dies with 141, and `pipefail` hands the pipeline
# `printf`'s status — so a MATCH is reported as a failure. It is a race (whoever
# finishes first wins), which is why it goes green on macOS and on an idle runner
# and red on a loaded one: hub#1471 hit it, wrote the warning above §10 and fixed
# only the block it was writing, leaving fourteen live. One of them then failed the
# PR of hub#1530 claiming `HUB_CLOUD_API_URL` was missing from the bench — a line
# that has been there since July.
#
# Two assertions, because a grep for a forbidden string is a style lint until
# somebody shows the string is actually harmful: the first proves the mechanism,
# the second is the guard.

# The match must be on the FIRST line and the filler AFTER it: `grep` works
# line-wise, so a single 200 KB line with the pattern at the start would force it
# to read the whole thing and there would be no early exit to race with.
sigpipe_block="HUB_CLOUD_API_URL
$(head -c 200000 /dev/zero | tr '\0' 'x')"
piped_verdict=present;      ! printf '%s' "$sigpipe_block" | grep -q 'HUB_CLOUD_API_URL' && piped_verdict=absent # sigpipe-demo
herestring_verdict=present; ! grep -q 'HUB_CLOUD_API_URL' <<<"$sigpipe_block" && herestring_verdict=absent

if [ "$piped_verdict" != absent ]; then
    # NOT a pass: it means this platform did not reproduce the race, so the guard
    # below is unproven here and only Linux would catch a reintroduction.
    bad "el patrón \`printf … | grep -q\` se rompe con un bloque mayor que el buffer del pipe" \
        "esta plataforma NO reprodujo el SIGPIPE (printf ganó la carrera): el control de abajo queda sin demostrar aquí — reprodúcelo en Linux antes de fiarte de su verde"
elif [ "$herestring_verdict" != present ]; then
    bad "el here-string sobrevive donde la tubería muere" \
        "\`grep -q … <<<\"\$bloque\"\` también dio «ausente» sobre un bloque que SÍ contiene el patrón: el arreglo de hub#1534 no vale en esta plataforma"
else
    ok "el patrón \`printf … | grep -q\` miente bajo pipefail y el here-string no (hub#1534)"
fi

# ONE awk over the file: no pipe and no short-circuiting reader, because a counter
# written with the very defect it hunts is the joke that writes itself. Comments are
# skipped (they talk ABOUT the pattern) and so is the single line tagged
# `sigpipe-demo`, which uses it on purpose two assertions above.
piped_greps=$(awk '
    /^[[:space:]]*#/  { next }
    /sigpipe-demo/    { next }
    /printf .%s. "\$[A-Za-z_]+" \| *grep/ { n++ }
    END { print n + 0 }
' "$self_path")
if [ "$piped_greps" -ne 0 ]; then
    bad "este fichero no canaliza hacia un lector que corta (hub#1534)" \
        "quedan $piped_greps usos de \`printf … | grep -q\`: bajo \`pipefail\` un MATCH se reporta como fallo y este guard tumba PRs sanas. Usa \`grep -q PATRÓN <<<\"\$bloque\"\`"
else
    ok "este fichero no canaliza hacia un lector que corta (hub#1534)"
fi

# ── OutfitKit: the CI verifies the version the image SHIPS (hub#1793) ────────
#
# `docker/Dockerfile` re-resolves `@erplora/outfitkit@latest` on every image
# (product decision, 2026-06-22), ignoring the lockfile pin. With only
# `pnpm install --frozen-lockfile` here, `vue-tsc`, vitest and the e2e ran against
# the LOCKFILE's OutfitKit (0.1.52) while the image shipped 0.1.72: a change of the
# library that breaks a hub screen went through with everything green. So both
# jobs that verify the shell run the image's own resolution command, taken from the
# Dockerfile (not retyped here), between the install and what they verify.
#
# hub#2304 — except the e2e of a PULL REQUEST. Its screenshots are compared with
# baselines drawn with ONE OutfitKit, and `latest` there turned every web PR red
# on each release that moved a pixel (0.1.80 on 24/09, 0.1.109 on 28/09) until
# someone redrew the photo. A PR's e2e installs the version the baselines were
# drawn with (`apps/web/tests/e2e/baselines-outfitkit.txt`), so it only measures
# the PR's own diff; `verify` and every non-PR e2e (push to develop/main, the
# nightly cron) keep the image's `latest`, and THOSE are the runs a release turns
# red — with the develop alert issue, not on somebody else's PR.
dockerfile="$repo_root/docker/Dockerfile"
baselines_outfitkit="$repo_root/apps/web/tests/e2e/baselines-outfitkit.txt"
baselines_outfitkit_rel="apps/web/tests/e2e/baselines-outfitkit.txt"
# awk reads the FILE and stops at the first match: no pipe into a reader that cuts (hub#1534).
image_resolution=$(awk 'match($0, /pnpm --filter @erplora\/web add @erplora\/outfitkit@[^[:space:]"]+/) { print substr($0, RSTART, RLENGTH); exit }' "$dockerfile")
pin_resolution='pnpm --filter @erplora/web add "@erplora/outfitkit@${HUB_BENCH_OUTFITKIT}"'

# The step of a job block (from its `- name:` to the next one) whose non-comment lines contain $2.
step_with() { # $1 = job block, $2 = fixed string
    awk -v needle="$2" '
        /^      - / { if (found) exit; buf = $0; if (index($0, needle)) found = 1; next }
        { buf = buf "\n" $0; if (index($0, needle) && !/^[[:space:]]*#/) found = 1 }
        END { if (found) print buf }
    ' <<<"$1"
}
line_of() { # $1 = block, $2 = fixed string → first non-comment line number
    awk -v cmd="$2" 'index($0, cmd) && !/^[[:space:]]*#/ {print NR; exit}' <<<"$1"
}

if [ -z "$image_resolution" ]; then
    bad "la imagen resuelve OutfitKit con un comando reconocible (hub#1793)" \
        "no encuentro \`pnpm --filter @erplora/web add @erplora/outfitkit@…\` en docker/Dockerfile: si la imagen cambió de forma de resolverla, este control y los jobs de test-web.yml tienen que seguirla"
else
    for pair in "verify:pnpm verify" "e2e:test:e2e"; do
        job=${pair%%:*}
        verifies=${pair#*:}
        block=$(job_block "$job")
        install_at=$(awk '/pnpm install --frozen-lockfile/ {print NR; exit}' <<<"$block")
        resolve_at=$(line_of "$block" "$image_resolution")
        verify_at=$(awk -v cmd="$verifies" 'index($0, "run:") && index($0, cmd) {print NR; exit}' <<<"$block")
        if [ -z "$resolve_at" ]; then
            bad "el job \`$job\` verifica la OutfitKit que publica la imagen (hub#1793)" \
                "falta \`$image_resolution\` en el job: verifica la del lockfile y la imagen publica otra"
        elif [ -z "$install_at" ] || [ -z "$verify_at" ] || [ "$resolve_at" -le "$install_at" ] || [ "$resolve_at" -ge "$verify_at" ]; then
            bad "el job \`$job\` resuelve OutfitKit ENTRE el install y \`$verifies\` (hub#1793)" \
                "orden encontrado — install: ${install_at:-?}, resolución: $resolve_at, verificación: ${verify_at:-?}"
        else
            ok "el job \`$job\` verifica la OutfitKit que publica la imagen (hub#1793)"
        fi
    done

    verify_step=$(step_with "$(job_block verify)" "$image_resolution")
    if grep -qF 'if:' <<<"$verify_step"; then
        bad "\`verify\` resuelve la OutfitKit de la imagen en TODOS los eventos (hub#2304)" \
            "el paso lleva un \`if:\`: vue-tsc y vitest de una PR comprobarían otra OutfitKit que la que sale en la imagen"
    else
        ok "\`verify\` resuelve la OutfitKit de la imagen en TODOS los eventos (hub#2304)"
    fi

    e2e_block=$(job_block e2e)
    image_step=$(step_with "$e2e_block" "$image_resolution")
    pin_step=$(step_with "$e2e_block" "$pin_resolution")
    if ! grep -qF "if: \${{ github.event_name != 'pull_request' }}" <<<"$image_step"; then
        bad "el e2e resuelve \`latest\` solo FUERA de las PRs (hub#2304)" \
            "el paso de \`$image_resolution\` del job e2e no lleva \`if: \${{ github.event_name != 'pull_request' }}\`: cada release de OutfitKit que mueve un píxel vuelve a tumbar las PRs ajenas"
    else
        ok "el e2e resuelve \`latest\` solo FUERA de las PRs (hub#2304)"
    fi
    if [ -z "$pin_step" ]; then
        bad "el e2e de una PR instala la OutfitKit de las capturas (hub#2304)" \
            "falta un paso con \`$pin_resolution\` en el job e2e"
    elif ! grep -qF "if: \${{ github.event_name == 'pull_request' }}" <<<"$pin_step"; then
        bad "el e2e de una PR instala la OutfitKit de las capturas (hub#2304)" \
            "el paso fijado no lleva \`if: \${{ github.event_name == 'pull_request' }}\`: develop y el cron dejarían de probar lo que publica la imagen"
    elif ! grep -qF "$baselines_outfitkit_rel" <<<"$pin_step" || ! grep -qF 'HUB_BENCH_OUTFITKIT=' <<<"$pin_step" || ! grep -qF 'GITHUB_ENV' <<<"$pin_step"; then
        bad "el e2e de una PR instala la OutfitKit de las capturas (hub#2304)" \
            "el paso fijado tiene que leer \`$baselines_outfitkit_rel\` y exportar HUB_BENCH_OUTFITKIT a \$GITHUB_ENV (la guarda del banco lo necesita para no exigir \`latest\`)"
    else
        ok "el e2e de una PR instala la OutfitKit de las capturas (hub#2304)"
    fi
    install_at=$(awk '/pnpm install --frozen-lockfile/ {print NR; exit}' <<<"$e2e_block")
    pin_at=$(line_of "$e2e_block" "$pin_resolution")
    build_at=$(line_of "$e2e_block" 'vite build')
    if [ -z "$pin_at" ] || [ -z "$install_at" ] || [ -z "$build_at" ] || [ "$pin_at" -le "$install_at" ] || [ "$pin_at" -ge "$build_at" ]; then
        bad "la OutfitKit de las capturas se instala ENTRE el install y el build del shell (hub#2304)" \
            "orden encontrado — install: ${install_at:-?}, fijada: ${pin_at:-?}, vite build: ${build_at:-?}"
    else
        ok "la OutfitKit de las capturas se instala ENTRE el install y el build del shell (hub#2304)"
    fi
fi

# The pin itself: one exact published-looking version, nothing a `pnpm add` could widen.
pinned_version=""
[ -f "$baselines_outfitkit" ] && pinned_version=$(<"$baselines_outfitkit")
if [[ "$pinned_version" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    ok "\`$baselines_outfitkit_rel\` fija una versión exacta ($pinned_version) (hub#2304)"
else
    bad "\`$baselines_outfitkit_rel\` fija una versión exacta (hub#2304)" \
        "contenido: '${pinned_version}' — tiene que ser X.Y.Z, la OutfitKit con la que se dibujaron las capturas"
fi

# Redrawing the baselines by the book must also move the pin, or the next PR compares new photos
# with the old OutfitKit. The dispatch path writes the version it drew with and uploads it with them.
record_step=$(step_with "$(job_block e2e)" "> $baselines_outfitkit_rel")
upload_step=$(step_with "$(job_block e2e)" 'name: playwright-baselines')
if ! grep -qF "update_baselines == 'true'" <<<"$record_step"; then
    bad "regenerar capturas reescribe \`$baselines_outfitkit_rel\` (hub#2304)" \
        "no hay un paso de la vía update_baselines que escriba la OutfitKit instalada en el fichero"
elif ! grep -qF "$baselines_outfitkit_rel" <<<"$upload_step"; then
    bad "regenerar capturas reescribe \`$baselines_outfitkit_rel\` (hub#2304)" \
        "el artefacto \`playwright-baselines\` no lleva el fichero: se commitearían PNG nuevos con la versión vieja"
else
    ok "regenerar capturas reescribe \`$baselines_outfitkit_rel\` y lo sube con los PNG (hub#2304)"
fi

# The develop alert is where a release that moves pixels now lands: it has to say how to fix it.
if grep -qF "$baselines_outfitkit_rel" <<<"$(job_block alert-develop)"; then
    ok "la alerta de develop explica el rojo de una release de OutfitKit (hub#2304)"
else
    bad "la alerta de develop explica el rojo de una release de OutfitKit (hub#2304)" \
        "el cuerpo de la issue no nombra \`$baselines_outfitkit_rel\`: quien la lea no sabe que hay que redibujar y mover el fichero"
fi

# ── 13. The merge-time check of the MERGED tree (ERPlora/pm#331) ─────────────
# The per-PR run proves the merge with the base AS IT WAS when it started; on
# 2026-09-11 two PRs green on their own left `develop` red for 2 h 58 min. So
# `merge-pr.sh` dispatches this workflow with `pr` + `head_sha` + `base_sha` when
# the base moved, and merges on THAT run. What it relies on, pinned here:
#   · the three inputs exist (a dispatch with an unknown input is a 422);
#   · `run-name` titles the run `merge-check hub#<pr> <head> onto <base>` — the
#     only way the door tells ITS run from a neighbour's on the same develop;
#   · the concurrency group carries the PR, or two merges cancel each other and
#     the develop push run;
#   · `verify` checks out `base_sha` with history and builds the merge BEFORE
#     `pnpm verify` — a check of `develop` alone would prove nothing;
#   · `e2e` (~20 min) does not run on it: the door waits on this run.
dispatch_block=$(on_sub_block workflow_dispatch)
mc_missing=""
for input in pr head_sha base_sha; do
    grep -qE "^      ${input}:" <<<"$dispatch_block" || mc_missing="$mc_missing $input"
done
if [ -n "$mc_missing" ]; then
    bad "workflow_dispatch takes the merge-check inputs (pm#331)" \
        "missing under \`on.workflow_dispatch.inputs\`:$mc_missing — merge-pr.sh's dispatch would be refused"
else
    ok "workflow_dispatch takes \`pr\`, \`head_sha\` and \`base_sha\` (pm#331)"
fi

run_name=$(awk '/^run-name:/ {print; exit}' "$workflow")
if ! grep -qF "format('merge-check hub#{0} {1} onto {2}', inputs.pr, inputs.head_sha, inputs.base_sha)" <<<"$run_name"; then
    bad "run-name titles a merge-check \`merge-check hub#<pr> <head> onto <base>\` (pm#331)" \
        "top-level run-name is '${run_name:-absent}': merge-pr.sh finds its run by that exact title"
elif ! grep -qF "|| ''" <<<"$run_name"; then
    bad "run-name falls back to GitHub's default title on every other event (pm#331)" \
        "'$run_name' has no \`|| ''\`: push and PR runs would lose their commit/PR title"
else
    ok "run-name titles a merge-check run and leaves every other run's title alone (pm#331)"
fi

concurrency_group=$(awk '/^concurrency:/ {f=1; next} f && /^  group:/ {print; exit} f && /^[A-Za-z]/ {exit}' "$workflow")
if ! grep -qF 'inputs.pr' <<<"$concurrency_group"; then
    bad "the concurrency group carries the merge-check's PR (pm#331)" \
        "'$concurrency_group': every dispatch shares \`refs/heads/develop\` and cancel-in-progress kills the other merges' checks and the develop push run"
else
    ok "the concurrency group carries the merge-check's PR (pm#331)"
fi

verify_job=$(job_block verify)
mc_step_at=$(awk '/bash \.\/scripts\/ci\/merge-check-tree\.sh/ && !/^[[:space:]]*#/ {print NR; exit}' <<<"$verify_job")
verify_at=$(awk '/run: pnpm verify/ {print NR; exit}' <<<"$verify_job")
install_at=$(awk '/pnpm install --frozen-lockfile/ {print NR; exit}' <<<"$verify_job")
# On the checkout's `ref:` itself — the merge step's env also names `inputs.base_sha`.
if ! grep -qE '^ +ref: .*inputs\.base_sha' <<<"$verify_job"; then
    bad "\`verify\` checks out base_sha on a merge-check (pm#331)" \
        "no \`inputs.base_sha\` in the job: it would test develop's tip, not the base the door read"
elif ! grep -qE "fetch-depth: .*inputs\.pr" <<<"$verify_job"; then
    bad "\`verify\` fetches the history a merge needs on a merge-check (pm#331)" \
        "no \`fetch-depth\` conditioned on \`inputs.pr\`: a depth-1 checkout has no merge base"
elif [ -z "$mc_step_at" ]; then
    bad "\`verify\` builds the merged tree (\`bash ./scripts/ci/merge-check-tree.sh\`) (pm#331)" \
        "no step runs it: the dispatch would re-test the base alone"
elif [ -z "$install_at" ] || [ -z "$verify_at" ] || [ "$mc_step_at" -ge "$install_at" ]; then
    bad "\`verify\` builds the merged tree BEFORE install and \`pnpm verify\` (pm#331)" \
        "order — merge: $mc_step_at, install: ${install_at:-?}, verify: ${verify_at:-?}"
elif ! awk -v at="$mc_step_at" 'NR < at && /if: .*inputs\.pr/ {f=1} END {exit !f}' <<<"$verify_job"; then
    bad "the merge step runs only on a merge-check (\`if:\` on inputs.pr) (pm#331)" \
        "without the guard, every push and PR run would try to merge with empty inputs"
else
    ok "\`verify\` checks out base_sha with history and builds the merge before \`pnpm verify\` (pm#331)"
fi

e2e_job=$(job_block e2e)
if ! grep -qE "^    if: .*!inputs\.pr" <<<"$e2e_job"; then
    bad "\`e2e\` does not run on a merge-check (pm#331)" \
        "no job-level \`if:\` excluding \`inputs.pr\`: the door would wait ~20 min more per merge"
else
    ok "\`e2e\` is skipped on a merge-check (pm#331)"
fi

# The merged-tree builder and its test trigger the gate, and the test RUNS.
for p in scripts/ci/merge-check-tree.sh scripts/tests/merge-check-tree.test.sh; do
    if grep -qF "$p" <<<"$push_block" && grep -qF "$p" <<<"$(on_sub_block pull_request)"; then
        ok "\`$p\` is in the push and pull_request \`paths\` (pm#331)"
    else
        bad "\`$p\` is in the push and pull_request \`paths\` (pm#331)" \
            "a change to it alone would trigger no check"
    fi
done
if grep -qE '^[[:space:]]*(run:[[:space:]]*)?bash (\./)?scripts/tests/merge-check-tree\.test\.sh[[:space:]]*$' "$workflow"; then
    ok "test-web.yml runs \`scripts/tests/merge-check-tree.test.sh\` (pm#331)"
else
    bad "test-web.yml runs \`scripts/tests/merge-check-tree.test.sh\` (pm#331)" \
        "no step executes it: the builder's contract would never run"
fi

printf '\n%d passed, %d failed\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
