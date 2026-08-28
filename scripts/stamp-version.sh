#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# stamp-version.sh — writes ONE version number into every file that carries it (hub#1236).
#
# The version of a release is decided by `scripts/image-tags.sh` (the tag, or the prerelease
# derived from `git describe`), and until now only ONE file was rewritten with it: the
# `[workspace.package] version` of the Cargo workspace, inline in `build-hub.yml`. That was enough
# while the Rust binary was the only thing that had a version to report.
#
# It stopped being enough with hub#1236. Two more artifacts leave this repository with a version
# on them, and a release that stamps one and forgets the others publishes a lie nobody can see:
#
#   Cargo.toml `[workspace.package] version`     → every crate (`env!("CARGO_PKG_VERSION")`):
#                                                  `/readyz`, `/api/hub/context`, `error_sink`,
#                                                  and `erplora-guest-sdk`, consumed by git tag.
#   packages/module-sdk/package.json `version`   → what `npm publish` puts in GitHub Packages.
#   packages/module-sdk/src/version.ts           → `SDK_VERSION`, the only thing a COMPILED
#                                                  `dist/<id>.esm.js` can print about the SDK it
#                                                  was built against.
#
# It never stamps HALFWAY: a file whose anchor is missing is an error, not a quieter success.
# Stamping two of three and exiting 0 is precisely how the three numbers drift apart, and the
# drift is only visible in a customer's hub.
#
# Usage:
#   scripts/stamp-version.sh --version 1.2.3 [--root <repo>]
#
# Contract test: scripts/tests/publish-sdks.test.sh (it runs this script over a throwaway copy of
# the three files and reads back what it wrote).
# ─────────────────────────────────────────────────────────────────────────────
set -uo pipefail

version=""
root=""

while [ $# -gt 0 ]; do
    case "$1" in
        --version) version="${2:-}"; shift 2 ;;
        --root)    root="${2:-}";    shift 2 ;;
        *) echo "stamp-version: argumento desconocido: $1" >&2; exit 2 ;;
    esac
done

[ -n "$version" ] || { echo "stamp-version: falta --version" >&2; exit 2; }
if [ -z "$root" ]; then
    root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
fi
[ -d "$root" ] || { echo "stamp-version: --root '$root' no es un directorio" >&2; exit 2; }

# Semver 2.0: X.Y.Z con prerelease y metadatos opcionales — `1.2.3`, `1.2.3-rc.1`,
# `1.2.3-dev.7+gabc1234` (el canal `dev` de image-tags.sh). Cualquier otra cosa se rechaza:
# estampar basura en los tres ficheros es peor que no estampar nada.
if ! printf '%s' "$version" | grep -qE '^[0-9]+\.[0-9]+\.[0-9]+(-[0-9A-Za-z.-]+)?(\+[0-9A-Za-z.-]+)?$'; then
    echo "❌ stamp-version: '$version' no es semver X.Y.Z[-prerelease][+build]" >&2
    exit 1
fi
if [ "$version" = "0.0.0" ]; then
    echo "❌ stamp-version: '0.0.0' es el hueco sin rellenar, no una versión (hub#1236)." >&2
    exit 1
fi

VERSION="$version" ROOT="$root" python3 - <<'PY'
import json
import os
import pathlib
import re
import sys

version = os.environ["VERSION"]
root = pathlib.Path(os.environ["ROOT"])

failures = []
written = []


def rewrite(relative, transform):
    """Applies `transform` to a file's text; a file that does not move is an error."""
    path = root / relative
    if not path.exists():
        failures.append(f"{relative}: no existe")
        return
    before = path.read_text(encoding="utf-8")
    try:
        after = transform(before)
    except ValueError as error:
        failures.append(f"{relative}: {error}")
        return
    if after != before:
        path.write_text(after, encoding="utf-8")
    written.append(relative)


def cargo_workspace_version(text):
    # Anclado a `[workspace.package]`: un `version = "…"` aparece bajo cada `[dependencies.*]`,
    # y coger la primera coincidencia del fichero pillaría la dependencia que ordenase antes.
    stamped, count = re.subn(
        r'(\[workspace\.package\][^\[]*?version\s*=\s*)"[^"]*"',
        lambda m: f'{m.group(1)}"{version}"',
        text,
        count=1,
        flags=re.DOTALL,
    )
    if count != 1:
        raise ValueError("no encuentro `[workspace.package].version` que estampar")
    return stamped


def package_json_version(text):
    # Por regex y no por `json.dumps` del objeto entero: reescribir el JSON reordena y reindenta
    # el fichero, y un diff de release no debe tocar nada más que el número.
    stamped, count = re.subn(
        r'(^\s*"version"\s*:\s*)"[^"]*"',
        lambda m: f'{m.group(1)}"{version}"',
        text,
        count=1,
        flags=re.MULTILINE,
    )
    if count != 1:
        raise ValueError('no encuentro la clave `"version"` que estampar')
    json.loads(stamped)  # el fichero sigue siendo JSON válido tras tocarlo
    return stamped


def sdk_version_ts(text):
    stamped, count = re.subn(
        r"(^export const SDK_VERSION = )'[^']*'",
        lambda m: f"{m.group(1)}'{version}'",
        text,
        count=1,
        flags=re.MULTILINE,
    )
    if count != 1:
        raise ValueError("no encuentro `export const SDK_VERSION = '…'` que estampar")
    return stamped


rewrite("Cargo.toml", cargo_workspace_version)
rewrite("packages/module-sdk/package.json", package_json_version)
rewrite("packages/module-sdk/src/version.ts", sdk_version_ts)

if failures:
    print("❌ stamp-version: la versión NO quedó estampada en todas partes:", file=sys.stderr)
    for failure in failures:
        print(f"   · {failure}", file=sys.stderr)
    print(
        "   Estampar solo una parte publica una imagen y un paquete npm que dicen números\n"
        "   distintos, y el desfase solo se ve en el hub de un cliente (hub#1236).",
        file=sys.stderr,
    )
    sys.exit(1)

for relative in written:
    print(f'  {relative} → "{version}"')
PY
