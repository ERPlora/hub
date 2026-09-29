#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Contract test for `scripts/ci/install-published-outfitkit.sh` — the step of
# `test-web.yml` that, when ERPlora/outfitkit announces a release
# (`repository_dispatch: outfitkit-published`, hub#2321), installs EXACTLY the
# version it announced before `pnpm verify` and the e2e run.
#
# Why exact and not `@latest`: the notice leaves `publish.yml` seconds after
# `npm publish`, and the registry's metadata is cached for minutes. `latest`
# could still resolve to the PREVIOUS release, and the run would come back green
# having tested the library customers already had — the one false green this
# trigger exists to avoid. The version comes from another repository's payload,
# so it is validated as `X.Y.Z` before it reaches a command line.
#
# Refusals, by CODE (ADR-0055: tests assert codes, never prose):
#   outfitkit_published_version_missing   the payload carried no version
#   outfitkit_published_version_invalid   the version is not X.Y.Z
#   outfitkit_published_not_installable   pnpm never managed to install it
#   outfitkit_published_version_mismatch  node_modules holds another version
#
# Hermetic: a fake `pnpm` on PATH records its arguments and writes the
# package.json a real install would. No network.
#
# Run:  bash scripts/tests/install-published-outfitkit.test.sh
# ─────────────────────────────────────────────────────────────────────────────
set -uo pipefail

repo_root=$(CDPATH='' cd -- "$(dirname -- "$0")/../.." && pwd)
script="$repo_root/scripts/ci/install-published-outfitkit.sh"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

pass=0
fail=0
ok()  { printf '  \033[32m✓\033[0m %s\n' "$1"; pass=$((pass + 1)); }
bad() { printf '  \033[31m✗\033[0m %s\n     %s\n' "$1" "$2"; fail=$((fail + 1)); }

# Fake pnpm: logs every call; fails the first $FAKE_PNPM_FAILS calls (the
# registry not serving the version yet), then "installs" $FAKE_PNPM_INSTALLS
# (default: the version it was asked for) into $OUTFITKIT_WEB_DIR.
mkdir -p "$TMP/bin"
cat > "$TMP/bin/pnpm" <<'SH'
#!/usr/bin/env bash
echo "$*" >> "$FAKE_PNPM_LOG"
calls=$(wc -l < "$FAKE_PNPM_LOG")
if [ "$calls" -le "${FAKE_PNPM_FAILS:-0}" ]; then
    echo "ERR_PNPM_NO_MATCHING_VERSION" >&2
    exit 1
fi
spec=${*: -1}
dir="$OUTFITKIT_WEB_DIR/node_modules/@erplora/outfitkit"
mkdir -p "$dir"
printf '{"name":"@erplora/outfitkit","version":"%s"}\n' "${FAKE_PNPM_INSTALLS:-${spec##*@}}" > "$dir/package.json"
SH
chmod +x "$TMP/bin/pnpm"

# run <case> [VAR=value ...] — runs the script in a clean web dir; sets $rc,
# $out (stdout+stderr), $calls (number of pnpm invocations), $log, $summary and
# $job_env (what the script appended to $GITHUB_ENV for the steps that follow).
run() {
    local case_dir="$TMP/$1"
    shift
    mkdir -p "$case_dir/web"
    : > "$case_dir/pnpm.log"
    out=$(env PATH="$TMP/bin:$PATH" \
        OUTFITKIT_WEB_DIR="$case_dir/web" FAKE_PNPM_LOG="$case_dir/pnpm.log" \
        OUTFITKIT_PUBLISH_WAIT=0 GITHUB_STEP_SUMMARY="$case_dir/summary.md" \
        GITHUB_ENV="$case_dir/github.env" \
        "$@" bash "$script" 2>&1)
    rc=$?
    log=$(cat "$case_dir/pnpm.log")
    calls=$(wc -l < "$case_dir/pnpm.log" | tr -d ' ')
    summary=$(cat "$case_dir/summary.md" 2>/dev/null || true)
    job_env=$(cat "$case_dir/github.env" 2>/dev/null || true)
}

echo "install-published-outfitkit.sh — la OutfitKit que anuncia el aviso (hub#2321)"

if [ ! -f "$script" ]; then
    bad "scripts/ci/install-published-outfitkit.sh existe" "no está: el aviso de OutfitKit no tiene quién instale la versión anunciada"
    printf '\n%d passed, %d failed\n' "$pass" "$fail"
    exit 1
fi

# 1. Happy path: exactly the announced version, once, into @erplora/web.
run happy OUTFITKIT_PUBLISHED=0.1.112
if [ "$rc" -eq 0 ] && [ "$calls" -eq 1 ] && [ "$log" = "--filter @erplora/web add @erplora/outfitkit@0.1.112" ]; then
    ok "instala la versión anunciada exacta (no \`latest\`) en @erplora/web"
else
    bad "instala la versión anunciada exacta" "rc=$rc calls=$calls pnpm='$log' out: $out"
fi
if grep -qF '0.1.112' <<<"$summary"; then
    ok "deja la versión probada en el resumen del run"
else
    bad "deja la versión probada en el resumen del run" "GITHUB_STEP_SUMMARY: '$summary'"
fi

# 2. No version in the payload → refused loudly, pnpm never called.
run missing OUTFITKIT_PUBLISHED=
if [ "$rc" -ne 0 ] && [ "$calls" -eq 0 ] && grep -qF 'outfitkit_published_version_missing' <<<"$out"; then
    ok "sin versión en el aviso: se niega (outfitkit_published_version_missing) sin instalar nada"
else
    bad "sin versión en el aviso: se niega" "rc=$rc calls=$calls out: $out"
fi

# 3. Anything that is not X.Y.Z never reaches the command line.
for v in 'latest' '0.1' '0.1.112-rc.1' '0.1.112; touch pwned' 'v0.1.112' ' 0.1.112'; do
    run "invalid-$RANDOM" OUTFITKIT_PUBLISHED="$v"
    if [ "$rc" -ne 0 ] && [ "$calls" -eq 0 ] && grep -qF 'outfitkit_published_version_invalid' <<<"$out"; then
        ok "versión '$v' rechazada (outfitkit_published_version_invalid) sin llamar a pnpm"
    else
        bad "versión '$v' rechazada" "rc=$rc calls=$calls out: $out"
    fi
done

# 4. The registry does not serve it yet: retries until it does.
run retry OUTFITKIT_PUBLISHED=0.1.112 FAKE_PNPM_FAILS=2 OUTFITKIT_PUBLISH_ATTEMPTS=5
if [ "$rc" -eq 0 ] && [ "$calls" -eq 3 ]; then
    ok "reintenta mientras el registro aún no sirve la versión (3 intentos)"
else
    bad "reintenta mientras el registro aún no sirve la versión" "rc=$rc calls=$calls out: $out"
fi

# 5. …but gives up after the configured attempts, by code.
run give-up OUTFITKIT_PUBLISHED=0.1.112 FAKE_PNPM_FAILS=99 OUTFITKIT_PUBLISH_ATTEMPTS=3
if [ "$rc" -ne 0 ] && [ "$calls" -eq 3 ] && grep -qF 'outfitkit_published_not_installable' <<<"$out"; then
    ok "se rinde tras los intentos configurados (outfitkit_published_not_installable)"
else
    bad "se rinde tras los intentos configurados" "rc=$rc calls=$calls out: $out"
fi

# 6. pnpm said yes but node_modules holds another version → red, not green.
run mismatch OUTFITKIT_PUBLISHED=0.1.112 FAKE_PNPM_INSTALLS=0.1.111
if [ "$rc" -ne 0 ] && grep -qF 'outfitkit_published_version_mismatch' <<<"$out"; then
    ok "si node_modules no tiene la versión anunciada, falla (outfitkit_published_version_mismatch)"
else
    bad "si node_modules no tiene la versión anunciada, falla" "rc=$rc out: $out"
fi

# 7. The bench guard (apps/web/tests/outfitkit-latest-guard.ts, hub#2259) fails a run whose
#    install was already behind `latest`. With two releases minutes apart, the run of the FIRST
#    notice installs a version that is behind by the time pnpm writes node_modules — a red that
#    says nothing about that release. The announced version is deliberate, so the script says so
#    the way the pull_request step does (hub#2304): HUB_BENCH_OUTFITKIT in $GITHUB_ENV.
run pins-the-guard OUTFITKIT_PUBLISHED=0.1.112
if [ "$rc" -eq 0 ] && [ "$job_env" = "HUB_BENCH_OUTFITKIT=0.1.112" ]; then
    ok "tells the bench guard the announced version is deliberate (HUB_BENCH_OUTFITKIT in \$GITHUB_ENV)"
else
    bad "tells the bench guard the announced version is deliberate" "rc=$rc GITHUB_ENV: '$job_env'"
fi

# 8. …and only once the install is proven: a refused run pins nothing for later steps.
run pins-nothing-on-mismatch OUTFITKIT_PUBLISHED=0.1.112 FAKE_PNPM_INSTALLS=0.1.111
if [ "$rc" -ne 0 ] && [ -z "$job_env" ]; then
    ok "a refused install exports no HUB_BENCH_OUTFITKIT"
else
    bad "a refused install exports no HUB_BENCH_OUTFITKIT" "rc=$rc GITHUB_ENV: '$job_env'"
fi

# 9. Outside Actions there is no \$GITHUB_ENV: the script still installs and does not fail.
run no-github-env OUTFITKIT_PUBLISHED=0.1.112 GITHUB_ENV=
if [ "$rc" -eq 0 ] && [ "$calls" -eq 1 ]; then
    ok "runs without \$GITHUB_ENV (outside Actions)"
else
    bad "runs without \$GITHUB_ENV (outside Actions)" "rc=$rc calls=$calls out: $out"
fi

printf '\n%d passed, %d failed\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
