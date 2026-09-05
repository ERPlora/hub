#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Contract test for PUBLISHING THE TWO SDKs — ERPlora/hub#1236.
#
# What it guards. `@erplora/module-sdk` was `private: true, version "0.0.0"`, declared by the 24
# module repos as `workspace:*`, and `erplora-guest-sdk` was reached by
# `path = "../../../../hub/crates/guest-sdk"`. So a published `dist/<id>.esm.js` had no way of
# saying which SDK it compiled against — the honest answer was "whatever checkout of the hub the
# developer had open" — and the handler's wasm could not be built on a runner at all, because that
# relative path does not exist there (`handler WASM SIN VERIFICAR`, ADR-0287 D5).
#
# The fix is a NUMBER, carried identically by the three files a release stamps, and published:
#
#   Cargo.toml `[workspace.package] version`   → every crate, `erplora-guest-sdk` included
#   packages/module-sdk/package.json `version` → what `npm publish` puts in GitHub Packages
#   packages/module-sdk/src/version.ts         → what a BUNDLE can print at runtime
#
# Why a test and not a review: nothing in this repository fails when a release forgets one of the
# three. The image would still build, the tag would still move, and the drift would only surface
# in a customer's hub as a bundle claiming a version that was never served.
#
# The stamping is not asserted by grep: this file RUNS `scripts/stamp-version.sh` over a throwaway
# copy of the three files and reads back what it wrote. A grep on the workflow would pass over a
# script that silently stamped nothing — which is the failure mode this exists for.
#
# Run:  bash scripts/tests/publish-sdks.test.sh
#
# Dependency-free on purpose (bash + grep + awk + python3's stdlib `json`): it runs as a step of
# `test-hub.yml` and of `build-hub.yml`, on `ci-runner-1` as well as on GitHub's image.
# ─────────────────────────────────────────────────────────────────────────────
set -uo pipefail

repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
stamp="$repo_root/scripts/stamp-version.sh"
sdk_package_json="$repo_root/packages/module-sdk/package.json"
sdk_version_ts="$repo_root/packages/module-sdk/src/version.ts"
guest_sdk_manifest="$repo_root/crates/guest-sdk/Cargo.toml"
build_workflow="$repo_root/.github/workflows/build-hub.yml"
test_workflow="$repo_root/.github/workflows/test-hub.yml"

pass=0
fail=0

ok()  { printf '  \033[32m✓\033[0m %s\n' "$1"; pass=$((pass + 1)); }
bad() { printf '  \033[31m✗\033[0m %s\n     %s\n' "$1" "$2"; fail=$((fail + 1)); }

json_field() { # $1 = file, $2 = dotted path
    python3 - "$1" "$2" <<'PY' 2>/dev/null
import json, sys
value = json.load(open(sys.argv[1], encoding="utf-8"))
for key in sys.argv[2].split("."):
    if not isinstance(value, dict) or key not in value:
        sys.exit(0)
    value = value[key]
print("" if value is None else (value if isinstance(value, str) else json.dumps(value)))
PY
}

# The `version = "…"` of a NAMED section of a Cargo manifest. Anchored to the section on purpose:
# a bare grep would pick the `version` of whichever `[dependencies.*]` sorted first.
cargo_section_version() { # $1 = manifest, $2 = section name
    awk -v want="[$2]" '
        $0 == want { inside = 1; next }
        /^\[/      { inside = 0 }
        inside && /^[[:space:]]*version[[:space:]]*=/ {
            gsub(/.*=[[:space:]]*"|".*/, ""); print; exit
        }
    ' "$1"
}

echo "hub#1236 — contrato de publicación de @erplora/module-sdk y erplora-guest-sdk"

# ── 1. The npm package is publishable at all ─────────────────────────────────
if [ ! -f "$sdk_package_json" ]; then
    bad "packages/module-sdk/package.json existe" "no está: no hay paquete que publicar"
else
    private=$(json_field "$sdk_package_json" private)
    registry=$(json_field "$sdk_package_json" publishConfig.registry)
    files=$(json_field "$sdk_package_json" files)
    pkg_version=$(json_field "$sdk_package_json" version)

    if [ -n "$private" ]; then
        bad "el paquete no es \`private\`" \
            "\`\"private\": $private\` → \`npm publish\` se niega y el paquete nunca sale del monorepo"
    else
        ok "packages/module-sdk/package.json no es \`private\`"
    fi

    if [ "$registry" != "https://npm.pkg.github.com" ]; then
        bad "publishConfig.registry apunta a GitHub Packages" \
            "es '${registry:-<vacío>}': sin él \`npm publish\` iría al registro PÚBLICO de npmjs, y este paquete es de un repo privado"
    else
        ok "publishConfig.registry = https://npm.pkg.github.com"
    fi

    # `main`/`types` apuntan a `src/index.ts`: el paquete se consume como FUENTE TypeScript
    # (así lo transpilan vitest y esbuild), así que el tarball TIENE que llevar `src/`.
    if ! grep -q '"src"' <<<"$files"; then
        bad "el tarball publicado incluye \`src/\`" \
            "\`files\` = ${files:-<sin declarar>} — \`main\` apunta a \`src/index.ts\`: sin \`src\` el paquete publicado no resuelve nada"
    else
        ok "\`files\` incluye \`src\` (el paquete se consume como fuente TS)"
    fi

    if ! grep -qE '^[0-9]+\.[0-9]+\.[0-9]+' <<<"$pkg_version"; then
        bad "la versión del paquete es semver" "es '${pkg_version:-<vacía>}'"
    elif [ "$pkg_version" = "0.0.0" ]; then
        bad "la versión del paquete no es el hueco 0.0.0" \
            "sigue siendo '0.0.0' — el hueco sin rellenar, que es justo el defecto de hub#1236"
    else
        ok "versión publicable: $pkg_version"
    fi
fi

# ── 2. The three carriers of the number agree in the COMMITTED tree ──────────
core_version=$(cargo_section_version "$repo_root/Cargo.toml" workspace.package)
ts_versions=$(sed -n "s/^export const SDK_VERSION = '\([^']*\)'.*/\1/p" "$sdk_version_ts" 2>/dev/null)
ts_version=${ts_versions%%$'\n'*}
pkg_version=$(json_field "$sdk_package_json" version)

if [ -z "$ts_version" ]; then
    bad "packages/module-sdk/src/version.ts exporta SDK_VERSION" \
        "no encuentro \`export const SDK_VERSION = '…'\`: un bundle no puede decir contra qué SDK compiló"
elif [ "$ts_version" != "$pkg_version" ] || [ "$ts_version" != "$core_version" ]; then
    bad "las tres versiones del árbol commiteado coinciden" \
        "Cargo.toml='$core_version' · package.json='$pkg_version' · version.ts='$ts_version' — una release las estampa a la vez, así que aquí un desacuerdo es una edición a mano"
else
    ok "Cargo.toml = package.json = version.ts = $core_version"
fi

# ── 3. The stamping REALLY stamps — se ejecuta, no se promete ────────────────
if [ ! -x "$stamp" ]; then
    bad "scripts/stamp-version.sh existe y es ejecutable" \
        "sin él la release solo sabe reescribir Cargo.toml, y el paquete npm saldría con la versión del árbol"
else
    sandbox=$(mktemp -d)
    mkdir -p "$sandbox/packages/module-sdk/src"
    cp "$repo_root/Cargo.toml" "$sandbox/Cargo.toml"
    cp "$sdk_package_json" "$sandbox/packages/module-sdk/package.json"
    cp "$sdk_version_ts" "$sandbox/packages/module-sdk/src/version.ts" 2>/dev/null || true

    if "$stamp" --root "$sandbox" --version 9.8.7 >/dev/null 2>&1; then
        stamped_cargo=$(cargo_section_version "$sandbox/Cargo.toml" workspace.package)
        stamped_pkg=$(json_field "$sandbox/packages/module-sdk/package.json" version)
        stamped_tss=$(sed -n "s/^export const SDK_VERSION = '\([^']*\)'.*/\1/p" "$sandbox/packages/module-sdk/src/version.ts" 2>/dev/null)
        stamped_ts=${stamped_tss%%$'\n'*}
        missed=""
        [ "$stamped_cargo" = "9.8.7" ] || missed="$missed Cargo.toml(='$stamped_cargo')"
        [ "$stamped_pkg" = "9.8.7" ]   || missed="$missed packages/module-sdk/package.json(='$stamped_pkg')"
        [ "$stamped_ts" = "9.8.7" ]    || missed="$missed packages/module-sdk/src/version.ts(='$stamped_ts')"
        if [ -n "$missed" ]; then
            bad "stamp-version.sh escribe la versión en los TRES ficheros" \
                "no la escribió en:$missed — la release publicaría un número distinto del que sirve la imagen"
        else
            ok "stamp-version.sh 9.8.7 → Cargo.toml + package.json + version.ts"
        fi
    else
        bad "stamp-version.sh acepta \`--root <dir> --version <X.Y.Z>\`" \
            "falló sobre una copia de los tres ficheros; ese es el contrato que build-hub.yml invoca"
    fi

    # Refuse-by-default: a version it cannot write is a version nobody notices is missing.
    if "$stamp" --root "$sandbox" --version "no-soy-semver" >/dev/null 2>&1; then
        bad "stamp-version.sh rechaza una versión que no es semver" \
            "aceptó 'no-soy-semver': estampar basura en los tres ficheros es peor que no estampar"
    else
        ok "stamp-version.sh rechaza una versión que no es semver"
    fi
    rm -rf "$sandbox"
fi

# ── 4. The release publishes the npm package — on a tag, and only on a tag ───
if [ ! -f "$build_workflow" ]; then
    bad ".github/workflows/build-hub.yml existe" "no está"
else
    # Un `npm publish` REAL, no solo el `--dry-run` que imprime el tarball. Es la distinción que
    # esta línea existe para hacer: un workflow que solo ensaya sale VERDE y no publica nada, y ese
    # es el modo de fallo caro (un release «hecho» del que no hay paquete).
    real_publish=$(grep -nE '^[^#]*npm publish' "$build_workflow" | grep -v -- '--dry-run')
    if [ -z "$real_publish" ]; then
        bad "build-hub.yml publica @erplora/module-sdk de verdad" \
            "no hay ningún \`npm publish\` sin \`--dry-run\`: el paquete seguiría sin salir del monorepo tras un tag"
    elif ! grep -q "startsWith(github.ref, 'refs/tags/v')" "$build_workflow"; then
        bad "la publicación se limita a un tag \`v*\`" \
            "sin la guarda \`startsWith(github.ref, 'refs/tags/v')\` un push a develop publicaría una versión npm — y una versión npm no se despublica"
    elif ! grep -q 'packages: write' "$build_workflow"; then
        bad "el job de publicación tiene \`packages: write\`" \
            "sin ese permiso el \`npm publish\` a GitHub Packages muere con 401"
    elif ! grep -q 'scripts/stamp-version.sh' "$build_workflow"; then
        bad "la publicación estampa la versión con scripts/stamp-version.sh" \
            "publicaría la versión del árbol (el hueco «en desarrollo»), no la del tag"
    elif ! grep -q 'NODE_AUTH_TOKEN' "$build_workflow"; then
        bad "el \`npm publish\` lleva credencial (NODE_AUTH_TOKEN)" \
            "npm no lee \`secrets.GITHUB_TOKEN\` por sí solo: sin \`NODE_AUTH_TOKEN\` el publish sale 401"
    else
        ok "build-hub.yml publica el paquete en GitHub Packages, solo desde un tag \`v*\`"
    fi

    # A PRERELEASE (`vX.Y.Z-rc.N`, the canary channel) must not become npm's `latest`. Without
    # `--tag`, `npm publish` moves the `latest` dist-tag to whatever was published last, so a bare
    # `npm install @erplora/module-sdk` would pull the candidate. Same rule `image-tags.sh` already
    # enforces on the image: an rc NEVER moves `:latest`.
    if [ -n "$real_publish" ]; then
        if ! grep -q -- '--tag' <<<"$real_publish"; then
            bad "una prerelease (rc) no se publica como \`latest\`" \
                "el \`npm publish\` real no lleva \`--tag\`: una \`X.Y.Z-rc.N\` movería \`latest\` en GitHub Packages, y \`npm install @erplora/module-sdk\` se llevaría la candidata"
        elif ! grep -qE '^[[:space:]]*\*-\*\)' "$build_workflow"; then
            bad "el dist-tag de npm distingue prerelease de final" \
                "no hay un \`case\` con la rama \`*-*)\` que mande una \`X.Y.Z-rc.N\` a un dist-tag distinto de \`latest\`"
        else
            ok "una rc se publica con su propio dist-tag (\`next\`), nunca como \`latest\`"
        fi
    fi
fi

# ── 5. `erplora-guest-sdk` es consumible por git tag ─────────────────────────
# Un módulo lo declarará `erplora-guest-sdk = { git = "…/hub", tag = "vX.Y.Z" }`. Cargo clona el
# repo y resuelve el crate DENTRO de su workspace, así que basta con que el crate no dependa de
# nada por ruta: un `path = "…"` fuera de este repo lo haría irresoluble en el clon.
if [ ! -f "$guest_sdk_manifest" ]; then
    bad "crates/guest-sdk/Cargo.toml existe" "no está"
else
    if grep -qE '^[[:space:]]*version\.workspace[[:space:]]*=[[:space:]]*true' "$guest_sdk_manifest"; then
        ok "erplora-guest-sdk hereda la versión del workspace (la que estampa el tag)"
    else
        bad "erplora-guest-sdk hereda \`version.workspace = true\`" \
            "con una versión propia se desengancha del tag y vuelve a haber dos números"
    fi

    path_deps=$(grep -nE '^[^#]*\bpath[[:space:]]*=[[:space:]]*"' "$guest_sdk_manifest")
    if [ -n "$path_deps" ]; then
        bad "erplora-guest-sdk no depende de nada por ruta" \
            "$(printf '%s' "$path_deps" | tr '\n' ' ') — en un clon por git tag esas rutas no existen"
    else
        ok "erplora-guest-sdk no tiene dependencias \`path =\` (resuelve en un clon por tag)"
    fi

    if grep -qE '^[[:space:]]*publish[[:space:]]*=[[:space:]]*false' "$guest_sdk_manifest"; then
        ok "erplora-guest-sdk lleva \`publish = false\` (se consume por git tag, nunca por crates.io)"
    else
        bad "erplora-guest-sdk lleva \`publish = false\`" \
            "sin él un \`cargo publish\` mandaría al registro PÚBLICO el SDK de un repo privado, y en crates.io una versión no se retira"
    fi
fi

# ── 6. Este mismo contrato corre en algún sitio ──────────────────────────────
runs_in=""
grep -q 'scripts/tests/publish-sdks.test.sh' "$build_workflow" 2>/dev/null && runs_in="build-hub.yml"
grep -q 'scripts/tests/publish-sdks.test.sh' "$test_workflow" 2>/dev/null && runs_in="${runs_in:+$runs_in y }test-hub.yml"
if [ -n "$runs_in" ]; then
    ok "este contrato lo corre $runs_in"
else
    bad "este contrato lo corre algún workflow" \
        "no lo invoca nadie — un guardarraíl que no se ejecuta es una creencia (hub#1240)"
fi

printf '\n%d passed, %d failed\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
