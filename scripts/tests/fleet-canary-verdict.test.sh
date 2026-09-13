#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Behaviour test for `scripts/ci/fleet-canary-verdict.py` — the verdict the `fleet-canary` job of
# `build-hub.yml` acts on (hub#1790).
#
# WHY. On 2026-09-11 the release `v1.1.22` promoted its digest, launched the canary, and the canary
# FAILED ten minutes later: the SaaS quarantined the release and the pointer fell back to 1.1.19.
# The job then read `current` — by then 1.1.19, verified two days earlier — and printed
# «🐤 El canario aprobó sha256:2cfc… — versión servida: 1.1.19». Green, over a veto. `current` is
# by construction the newest release nobody vetoed, so it can never answer «what happened to MINE».
#
# The verdict is decided about the job's OWN digest, against both shapes of the SaaS:
#   · with `?image=` support (`release` key, saas#2024 — PRE today): `release.canary_state`;
#   · without it (production today): `current`, but only while `current` IS this digest. The
#     pointer moving away from it is a red, never a reading of somebody else's verdict.
#
# Run:  bash scripts/tests/fleet-canary-verdict.test.sh
# Dependency-free: bash + python3's stdlib.
# ─────────────────────────────────────────────────────────────────────────────
set -uo pipefail

repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
script="$repo_root/scripts/ci/fleet-canary-verdict.py"
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

pass=0
fail=0
ok()  { printf '  \033[32m✓\033[0m %s\n' "$1"; pass=$((pass + 1)); }
bad() { printf '  \033[31m✗\033[0m %s\n     %s\n' "$1" "$2"; fail=$((fail + 1)); }

# The digests of the real incident. The job carries the owner as GitHub spells it (`ERPlora`); the
# SaaS stores it lower-cased — the same image, and the comparison must say so.
OURS="ghcr.io/ERPlora/hub@sha256:2cfc6673466486fae7074bda8a526d78f75baf03896f3540af46fff6989b4a92"
OURS_AS_STORED="ghcr.io/erplora/hub@sha256:2cfc6673466486fae7074bda8a526d78f75baf03896f3540af46fff6989b4a92"
PREVIOUS="ghcr.io/erplora/hub@sha256:9bcbbd3550e0b6fe02740ea81d7a31e6eb7dbc88f22284ad53762b4c457e44fe"

# expect <case> <json body> <expected verdict> [expected text in the detail]
expect() {
    local name=$1 body=$2 want=$3 detail=${4:-}
    printf '%s' "$body" >"$tmp/release.json"
    local out verdict got_detail
    if ! out=$(python3 "$script" "$tmp/release.json" "$OURS" 2>&1); then
        bad "$name" "the script failed: $out"
        return
    fi
    verdict=${out%%$'\t'*}
    got_detail=${out#*$'\t'}
    if [ "$verdict" != "$want" ]; then
        bad "$name" "verdict \`$verdict\`, expected \`$want\` (detail: $got_detail)"
    elif [ -n "$detail" ] && [[ "$got_detail" != *"$detail"* ]]; then
        bad "$name" "verdict ok, but the detail does not say \`$detail\`: $got_detail"
    else
        ok "$name"
    fi
}

echo "hub#1790 — el veredicto del canario es el de SU digest"

if [ ! -f "$script" ]; then
    bad "scripts/ci/fleet-canary-verdict.py existe" "el job no tiene de dónde sacar un veredicto sobre su propio digest"
    printf '\n%d passed, %d failed\n' "$pass" "$fail"
    exit 1
fi

# ── The SaaS that production runs today: `current`, no `release` ────────────
expect "🔴 v1.1.22: vetada y el puntero cayó a la anterior → ROJO, nunca el verde de la 1.1.19" \
    "{\"current\": {\"image\": \"$PREVIOUS\", \"version\": \"1.1.19\", \"canary_verified\": true, \"quarantined\": false}, \"previous\": null}" \
    moved "1.1.19"

expect "sin \`release\`: el puntero ES mi digest y está verificado → verde" \
    "{\"current\": {\"image\": \"$OURS_AS_STORED\", \"version\": \"1.1.22\", \"canary_verified\": true, \"quarantined\": false, \"canary_version_seen\": \"1.1.22\"}}" \
    verified "1.1.22"

expect "sin \`release\`: mi digest en cuarentena → vetada" \
    "{\"current\": {\"image\": \"$OURS_AS_STORED\", \"version\": \"1.1.22\", \"canary_verified\": false, \"quarantined\": true, \"quarantine_reason\": \"canary failed\"}}" \
    quarantined "canary failed"

expect "sin \`release\`: mi digest aún sin veredicto → seguir esperando" \
    "{\"current\": {\"image\": \"$OURS_AS_STORED\", \"version\": \"1.1.22\", \"canary_verified\": false, \"quarantined\": false}}" \
    pending

# ── The SaaS with `?image=` (saas#2024): `release` is MY release ─────────────
expect "🔴 con \`release\`: la vigente (otra) está verificada y la mía sigue en marcha → esperar, no verde" \
    "{\"current\": {\"image\": \"$PREVIOUS\", \"canary_verified\": true, \"canary_state\": \"verified\"}, \"release\": {\"image\": \"$OURS_AS_STORED\", \"version\": \"1.1.22\", \"canary_state\": \"running\"}}" \
    pending

expect "con \`release\`: verificada → verde" \
    "{\"release\": {\"image\": \"$OURS_AS_STORED\", \"version\": \"1.1.22\", \"canary_state\": \"verified\", \"canary_version_seen\": \"1.1.22\"}}" \
    verified "1.1.22"

expect "con \`release\`: vetada → rojo con su motivo" \
    "{\"release\": {\"image\": \"$OURS_AS_STORED\", \"canary_state\": \"quarantined\", \"quarantine_reason\": \"canary failed: JSONDecodeError\"}}" \
    quarantined "JSONDecodeError"

for state in refused errored failed; do
    expect "con \`release\`: \`$state\` → rojo inmediato con el motivo (antes: 20 min de espera)" \
        "{\"release\": {\"image\": \"$OURS_AS_STORED\", \"canary_state\": \"$state\", \"canary_run_reason\": \"no aura can host a canary\"}}" \
        "$state" "no aura can host a canary"
done

expect "con \`release\`: \`pending\` → seguir esperando" \
    "{\"release\": {\"image\": \"$OURS_AS_STORED\", \"canary_state\": \"pending\"}}" \
    pending

expect "con \`release\` = null: el SaaS no conoce mi digest → rojo" \
    "{\"current\": {\"image\": \"$PREVIOUS\", \"canary_verified\": true}, \"release\": null}" \
    missing

expect "con \`release\` de OTRO digest → rojo, nunca su veredicto" \
    "{\"release\": {\"image\": \"$PREVIOUS\", \"canary_state\": \"verified\"}}" \
    mismatch

expect "cuerpo ilegible (un 502 en HTML) → seguir esperando" \
    "<html>502 Bad Gateway</html>" \
    unknown

printf '\n%d passed, %d failed\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
