#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Contract test for the `fleet-canary` job of `.github/workflows/build-hub.yml`
# — ERPlora/saas#1895, punto 3 de Ioan (2026-09-06): «los Actions deberían crear el canario».
#
# WHY THE JOB EXISTS. Publishing a `v*` tag put an image in GHCR and stopped there. Whether that
# image WORKS was answered by a person remembering to run `manage.py hub_canary --execute` inside
# the production container — and on 2026-08-10 the cost of not answering it was measured: a
# campaign reported `On target: 100.0%` while the node had REJECTED the image and went on serving
# the old task. The report was true about what it asked (Dokploy, which is not on the traffic
# path) and false about the world. The canary is the only piece of the chain that asks the hub
# itself, so «somebody remembers to run it» is not a good enough trigger for it.
#
# WHAT THE JOB MUST NOT BECOME, and why each one is worse than having no job at all:
#
#   · `continue-on-error: true`     → the release goes green while the image was never proven.
#                                     A green tick that means nothing is worse than a red one:
#                                     it is the `fallo mudo` this project keeps paying for.
#   · fire-and-forget (no polling)  → same thing with extra steps. Launching a canary proves
#                                     nothing; the VERDICT is the product, and it arrives minutes
#                                     later because a cold image pull is minutes.
#   · promoting a prerelease        → `image_pointer.current()` is what EVERY NEW HUB is created
#                                     from, not just what the fleet rolls to. Auto-promoting an
#                                     `rc` would have customers' hubs born on a release candidate.
#   · rolling the fleet from here   → a merge reaching customers must stay a deliberate act by a
#                                     person (ADR-0118, kept by ADR-0269 §10). The token this job
#                                     carries lives in a GitHub repository; the SaaS refuses it
#                                     for `rollout/` on purpose, and the job must not ask.
#   · skipping when unconfigured    → recreates the exact bug: the canary quietly stops happening
#                                     and nobody learns until an incident. Missing configuration
#                                     is a LOUD failure, naming what to set.
#
# Run:  bash scripts/tests/canary-on-publish.test.sh
#
# Dependency-free (bash + awk + grep): it runs as a step of `build-hub.yml` itself and of
# `actionlint.yml`, on `ci-runner-1` as well as on GitHub's image.
# ─────────────────────────────────────────────────────────────────────────────
set -uo pipefail

repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
workflow="$repo_root/.github/workflows/build-hub.yml"

JOB="fleet-canary"
PROMOTE_PATH="/api/v1/fleet/release/promote/"
CANARY_PATH="/api/v1/fleet/canary/"
# 🔴 Con la barra y la comilla de cierre: `/api/v1/fleet/release/` a secas es PREFIJO de
# `/api/v1/fleet/release/promote/`, que el paso de lanzamiento ya llama — así que la asercion
# pasaba aunque se borrase el sondeo entero. Lo cazo un mutante el 2026-09-07.
VERDICT_PATH='/api/v1/fleet/release/"'

ROLLOUT_PATH="/api/v1/fleet/rollout/"
TOKEN_HEADER="X-Fleet-Token"

pass=0
fail=0

ok() { printf '  \033[32m✓\033[0m %s\n' "$1"; pass=$((pass + 1)); }
bad() { printf '  \033[31m✗\033[0m %s\n     %s\n' "$1" "$2"; fail=$((fail + 1)); }

# The job's own block only. Grepping the whole workflow would happily accept a marker from
# `build-and-push` above — the assertion that lies.
job_block() {
    awk -v job="  ${JOB}:" '
        $0 == job {inside=1; next}
        inside && /^  [A-Za-z]/ {exit}
        inside {print}
    ' "$workflow"
}

# The same block without comment-only lines: a comment that EXPLAINS a marker must never be what
# satisfies a check about the code handling it.
job_code() { job_block | grep -v '^[[:space:]]*#'; }

echo "saas#1895 — contrato del job ${JOB} de build-hub.yml"

block=$(job_block)
if [ -z "$block" ]; then
    bad "build-hub.yml define el job \`${JOB}\`" \
        "sin él, publicar un tag vuelve a dejar la imagen sin probar hasta que alguien se acuerde"
    printf '\nFAIL: %s caso(s) de contrato\n' "$fail"
    exit 1
fi
ok "build-hub.yml define el job \`${JOB}\`"

code=$(job_code)

# ── 1. Corre DESPUÉS de que la imagen exista, y solo para un tag ─────────────
if grep -qE '^\s+needs:.*build-and-push' <<<"$code"; then
    ok "espera a \`build-and-push\` (no hay nada que probar antes de publicar)"
else
    bad "espera a \`build-and-push\`" "sin \`needs\`, el canario correría contra una imagen que aún no está en GHCR"
fi

if grep -qF "refs/tags/v" <<<"$code"; then
    ok "solo corre para un tag \`v*\`"
else
    bad "solo corre para un tag \`v*\`" "un push a develop no es una release: crearía un hub por commit"
fi

# ── 2. Prerelease NO: el puntero es de donde NACE cada hub nuevo ─────────────
if grep -qE "channel.*==.*'release'|channel.*!=.*'release'" <<<"$code"; then
    ok "solo promociona el canal \`release\` (un \`rc\` no se convierte en el puntero de la flota)"
else
    bad "solo promociona el canal \`release\`" \
        "\`image_pointer.current()\` es la imagen con la que se CREA cada hub nuevo: promocionar un rc los pone a todos en una release candidate"
fi

# ── 3. Las dos llamadas que cierran el lazo ──────────────────────────────────
for path in "$PROMOTE_PATH" "$CANARY_PATH"; do
    if grep -qF "$path" <<<"$code"; then
        ok "llama a \`${path}\`"
    else
        bad "llama a \`${path}\`" "es la mitad del lazo que la issue pide cerrar sin una persona en medio"
    fi
done

if grep -qF "$TOKEN_HEADER" <<<"$code"; then
    ok "se autentica con \`${TOKEN_HEADER}\` (credencial estrecha, no la del plano hub↔cloud)"
else
    bad "se autentica con \`${TOKEN_HEADER}\`" "sin ella el SaaS responde 403 y el lazo no existe"
fi

if grep -qE 'secrets\.FLEET_PUBLISH_TOKEN' <<<"$code"; then
    ok "el token sale de \`secrets.FLEET_PUBLISH_TOKEN\`, no del workflow"
else
    bad "el token sale de \`secrets.FLEET_PUBLISH_TOKEN\`" "un secreto en el fichero es un secreto público"
fi

# ── 4. Lo que separa «lanzar un canario» de «probar la imagen» ───────────────
if grep -qF "$VERDICT_PATH" <<<"$code"; then
    ok "vuelve a por el VEREDICTO (GET \`/api/v1/fleet/release/\`), no se queda en lanzarlo"
else
    bad "vuelve a por el veredicto" \
        "lanzar un canario no prueba nada: el veredicto tarda minutos (un pull en frío no son segundos) y es el producto del job"
fi

if grep -qE 'canary_verified' <<<"$code"; then
    ok "lee \`canary_verified\` — que ya incluye el veto: un digest probado a las 10:00 y vetado a las 11:00 NO está verificado"
else
    bad "lee \`canary_verified\`" "sin mirar el veredicto, el job va verde pase lo que pase"
fi

if grep -qE '^\s+continue-on-error:\s*true' <<<"$code"; then
    bad "no lleva \`continue-on-error: true\`" \
        "la release iría verde con la imagen sin probar — exactamente el fallo mudo que este job existe para impedir"
else
    ok "no lleva \`continue-on-error: true\` (un canario que no puede poner el run en rojo no es un canario)"
fi

if grep -qE '\bexit 1\b' <<<"$code"; then
    ok "falla el job cuando el canario veta la imagen o falta configuración"
else
    bad "falla el job cuando el canario veta" "un job que nunca sale en rojo no informa de nada"
fi

# ── 5. El límite del plano de CI ─────────────────────────────────────────────
if grep -qF "$ROLLOUT_PATH" <<<"$code"; then
    bad "NO llama a \`${ROLLOUT_PATH}\`" \
        "llevar la flota a una versión es un acto deliberado de una persona (ADR-0118, mantenida por ADR-0269 §10): el token de CI no lo puede hacer, y el job no lo debe intentar"
else
    ok "no intenta rodar la flota: publicar prueba la imagen, no la lleva a los clientes"
fi

printf '\n'
if [ "$fail" -gt 0 ]; then
    printf 'FAIL: %s caso(s) de contrato (%s ok)\n' "$fail" "$pass"
    exit 1
fi
printf 'OK: %s caso(s) de contrato\n' "$pass"
