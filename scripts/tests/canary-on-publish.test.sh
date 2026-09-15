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
# ADR-0467 (saas#1928): the credential is an API key of the `ci` superuser carrying exactly
# `fleet:read fleet:promote fleet:canary` — the one mechanism for everything that is not a
# browser. `X-Fleet-Token` was the third machine secret the SaaS grew in a week; it is gone.
TOKEN_HEADER="X-Api-Key"
RETIRED_HEADER="X-Fleet-Token"
SECRET_NAME="FLEET_API_KEY"
RETIRED_SECRET="FLEET_PUBLISH_TOKEN"

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
    ok "se autentica con \`${TOKEN_HEADER}\` (una API key acotada por scopes, no la credencial del plano hub↔cloud)"
else
    bad "se autentica con \`${TOKEN_HEADER}\`" "sin ella el SaaS responde 401 y el lazo no existe"
fi

if grep -qF "$RETIRED_HEADER" <<<"$code"; then
    bad "ya no manda \`${RETIRED_HEADER}\`" "ese header se jubiló con ADR-0467: el SaaS lo retira en cuanto este job deje de mandarlo"
else
    ok "ya no manda \`${RETIRED_HEADER}\` (jubilado por ADR-0467)"
fi

if grep -qE "secrets\.${SECRET_NAME}" <<<"$code"; then
    ok "la llave sale de \`secrets.${SECRET_NAME}\`, no del workflow"
else
    bad "la llave sale de \`secrets.${SECRET_NAME}\`" "un secreto en el fichero es un secreto público"
fi

if grep -qE "secrets\.${RETIRED_SECRET}" <<<"$code"; then
    bad "ya no lee \`secrets.${RETIRED_SECRET}\`" "el secreto viejo se borra del repo con este cambio; leerlo lo mantendría vivo"
else
    ok "ya no lee \`secrets.${RETIRED_SECRET}\`"
fi

# ── 4. Lo que separa «lanzar un canario» de «probar la imagen» ───────────────
if grep -qF "$VERDICT_PATH" <<<"$code"; then
    ok "vuelve a por el VEREDICTO (GET \`/api/v1/fleet/release/\`), no se queda en lanzarlo"
else
    bad "vuelve a por el veredicto" \
        "lanzar un canario no prueba nada: el veredicto tarda minutos (un pull en frío no son segundos) y es el producto del job"
fi

# hub#1790: the verdict is about THIS digest. `current` after a veto is another release, and reading
# it gave v1.1.22 a green over its own quarantine (2026-09-11). The decision lives in a script with
# a behaviour test (`fleet-canary-verdict.test.sh`); here only the wiring is pinned.
if grep -qF 'image=${DIGEST}' <<<"$code"; then
    ok "pregunta por SU digest (\`?image=\`), no por la release vigente"
else
    bad "pregunta por su digest (\`?image=\`)" "tras un veto, la vigente es OTRA release: leerla dio verde en v1.1.22 sobre su propia cuarentena"
fi
if grep -qE 'uses:\s*actions/checkout@' <<<"$code"; then
    ok "hace checkout del repo (el script del veredicto vive en él)"
else
    bad "hace checkout del repo" "sin checkout, \`scripts/ci/fleet-canary-verdict.py\` no existe en el runner y el sondeo muere en el primer intento"
fi
if grep -qF 'scripts/ci/fleet-canary-verdict.py' <<<"$code"; then
    ok "decide con \`scripts/ci/fleet-canary-verdict.py\` (probado con los casos reales en fleet-canary-verdict.test.sh)"
else
    bad "decide con \`scripts/ci/fleet-canary-verdict.py\`" "un veredicto escrito a mano en el YAML no tiene test que lo pruebe — así se coló el verde de v1.1.22"
fi
if grep -qE "current\"\)|get\(\"current\"\)" <<<"$code"; then
    bad "no lee \`current\` en el YAML" "\`current\` no habla de este digest después de un veto"
else
    ok "no decide leyendo \`current\` en el YAML"
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

# ── 5b. Una referencia que Docker pueda descargar (hub#1869) ─────────────────
# `github.repository_owner` is `ERPlora`. Docker refuses a repository with capitals, so a promoted
# `ghcr.io/ERPlora/hub:X.Y.Z` left the canary hub unable to pull, never booted, and vetoed 1.1.20 to
# 1.1.23 for a capital letter (2026-09-09 → 2026-09-15). The job may read the owner, but only lowered
# BEFORE the reference it promotes is built.
owner_line=$(grep -nF 'repository_owner' <<<"$code" | head -1 | cut -d: -f1)
lower_line=$(grep -nE "IMAGE_REPO=.*tr '\[:upper:\]' '\[:lower:\]'|IMAGE_REPO=\"\\\$\{IMAGE_REPO,,\}\"" <<<"$code" | head -1 | cut -d: -f1)
ref_line=$(grep -nF 'ref="${IMAGE_REPO}' <<<"$code" | head -1 | cut -d: -f1)
if [ -z "$owner_line" ]; then
    if grep -qE 'ghcr\.io/[^"$ ]*[A-Z]' <<<"$code"; then
        bad "promociona una referencia en minúsculas" "hay una imagen ghcr.io con mayúsculas escrita en el job"
    else
        ok "promociona una referencia en minúsculas (no depende de \`repository_owner\`)"
    fi
elif [ -n "$lower_line" ] && [ -n "$ref_line" ] && [ "$lower_line" -lt "$ref_line" ]; then
    ok "pasa \`repository_owner\` a minúsculas antes de construir la referencia que promociona"
else
    bad "pasa \`repository_owner\` a minúsculas antes de promocionar" \
        "\`ghcr.io/ERPlora/hub\` no se puede descargar: el hub canario no arranca y la release se veta sola (hub#1869)"
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
