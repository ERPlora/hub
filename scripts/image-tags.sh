#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# image-tags.sh — what the hub image gets called, and the guard in front of it (hub#515).
#
# ONE source of truth: `[workspace.package] version` in the workspace `Cargo.toml`. The Rust
# crates already inherit it (`version.workspace = true`), so `env!("CARGO_PKG_VERSION")` — what
# `/system` reports and what `error_sink` stamps on every reported error — is that same number.
# Deriving the image name from the same file is what keeps the tag and the binary from drifting.
#
# Before this, the version came from the git ref: a `v1.2.3` tag said "1.2.3" and a push to `main`
# said the short sha. So the image was called one thing, the binary called itself `0.0.0`, and the
# shell's footer showed a SHA where a version belongs.
#
# What it prints (and writes to $GITHUB_OUTPUT when set):
#
#   version=X.Y.Z
#   <image>:X.Y.Z      ← immutable, RELEASE ONLY. What a rollback pins to.
#   <image>:X.Y        ← moving: "the latest 1.2.*"
#   <image>:X          ← moving: "the latest 1.*"
#   <image>:latest     ← the tag the provisioning registers on every real hub
#   <image>:<sha>      ← immutable per commit
#
# On a push to `main` only `:latest` and `:<sha>` are published: `main` is an integration build,
# not a release, and minting `:X.Y.Z` there would move an immutable tag on every merge.
#
# NIEGA la publicación (exit 1) cuando:
#   · la versión no es semver `X.Y.Z`, o sigue siendo el hueco `0.0.0`;
#   · esa versión YA está en el registro. Un tag inmutable que un segundo build puede mover
#     convierte «vuelve a 1.2.3» en una promesa vacía — y es el tag del que depende el rollback;
#   · la versión es MENOR O IGUAL que la última publicada. Retroceder no es un error que se corrija:
#     las stores no vuelven atrás;
#   · no se puede LEER el registro. Refuse-by-default a propósito: una release es un gesto raro y
#     deliberado, y publicar sin poder comprobar la monotonía es justo lo que no se deshace.
#     Override consciente: `IMAGE_TAGS_ALLOW_UNVERIFIED=1`.
#
# Usage:
#   scripts/image-tags.sh --image ghcr.io/erplora/hub --ref "$GITHUB_REF" --sha "$GITHUB_SHA"
#
# Seam used by scripts/tests/image-tags.test.sh:
#   IMAGE_TAGS_PUBLISHED_CMD  <cmd> → escribe en stdout las versiones ya publicadas, una por línea.
#                                     Exit != 0 = no se pudo leer el registro.
# ─────────────────────────────────────────────────────────────────────────────
set -uo pipefail

manifest=""
image=""
ref=""
sha=""

while [ $# -gt 0 ]; do
    case "$1" in
        --manifest) manifest="$2"; shift 2 ;;
        --image)    image="$2";    shift 2 ;;
        --ref)      ref="$2";      shift 2 ;;
        --sha)      sha="$2";      shift 2 ;;
        *) echo "image-tags: argumento desconocido: $1" >&2; exit 2 ;;
    esac
done

if [ -z "$manifest" ]; then
    manifest="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)/Cargo.toml"
fi
[ -n "$image" ] || { echo "image-tags: falta --image" >&2; exit 2; }
[ -n "$sha" ] || { echo "image-tags: falta --sha" >&2; exit 2; }

# Lowercase: GHCR rejects uppercase in a package name, and `github.repository_owner` keeps its case.
image=$(printf '%s' "$image" | tr '[:upper:]' '[:lower:]')

# `a > b` en semver, campo a campo. Sin `sort -V`: el `sort` de BSD no siempre lo trae y esto corre
# tanto en el runner (GNU) como en el portátil.
version_gt() {
    a_major="${1%%.*}"; a_rest="${1#*.}"; a_minor="${a_rest%%.*}"; a_patch="${a_rest#*.}"
    b_major="${2%%.*}"; b_rest="${2#*.}"; b_minor="${b_rest%%.*}"; b_patch="${b_rest#*.}"
    [ "$a_major" -gt "$b_major" ] && return 0
    [ "$a_major" -lt "$b_major" ] && return 1
    [ "$a_minor" -gt "$b_minor" ] && return 0
    [ "$a_minor" -lt "$b_minor" ] && return 1
    [ "$a_patch" -gt "$b_patch" ]
}

# ── ¿Es esto una release? ────────────────────────────────────────────────────
is_release=0
case "$ref" in
    refs/tags/v*) is_release=1 ;;
esac

# ── La versión ───────────────────────────────────────────────────────────────
# En una release sale del TAG. Fuera, del manifest (build de integración).
if [ "$is_release" -eq 1 ]; then
    version="${ref#refs/tags/v}"
    source_of_version="el tag $ref"
else
    # Anclado a la sección: un `version = "…"` aparece también bajo cada `[dependencies.*]`, y
    # coger la primera coincidencia del fichero pillaría la dependencia que ordenase antes.
    version=$(awk '
        /^\[workspace\.package\]/ { in_section = 1; next }
        /^\[/                       { in_section = 0 }
        in_section && /^[[:space:]]*version[[:space:]]*=/ {
            gsub(/.*=[[:space:]]*"|".*/, ""); print; exit
        }
    ' "$manifest")
    source_of_version="[workspace.package] de $manifest"
fi

if [ -z "$version" ]; then
    echo "❌ image-tags: no encuentro la versión en $source_of_version" >&2
    exit 1
fi

if ! printf '%s' "$version" | grep -qE '^[0-9]+\.[0-9]+\.[0-9]+$'; then
    echo "❌ image-tags: '$version' no es semver X.Y.Z (viene de $source_of_version)." >&2
    echo "   El criterio de qué es MAJOR/MINOR/PATCH: architecture/hub/versioning.md" >&2
    exit 1
fi

if [ "$version" = "0.0.0" ]; then
    echo "❌ image-tags: la versión es '0.0.0' — eso es el hueco sin rellenar, no una versión." >&2
    exit 1
fi

major="${version%%.*}"
minor="${version%.*}"   # X.Y.Z → X.Y

# ── El tag no se cree a ciegas ───────────────────────────────────────────────
if [ "$is_release" -eq 1 ]; then
    published_cmd="${IMAGE_TAGS_PUBLISHED_CMD:-}"
    if [ -n "$published_cmd" ]; then
        published=$("$published_cmd") || published_failed=1
    else
        # Por defecto: las etiquetas del paquete en GHCR. Necesita `packages: read`, que el
        # workflow ya tiene.
        owner="${image#ghcr.io/}"; owner="${owner%%/*}"
        package="${image##*/}"
        published=$(gh api --paginate \
            "/orgs/$owner/packages/container/$package/versions" \
            --jq '.[].metadata.container.tags[]' 2>/dev/null) || published_failed=1
    fi

    if [ "${published_failed:-0}" = "1" ] && [ "${IMAGE_TAGS_ALLOW_UNVERIFIED:-0}" != "1" ]; then
        echo "❌ image-tags: no he podido leer las versiones publicadas de $image." >&2
        echo "   No publico sin comprobarlo: el MISMO tag dispara la app hacia Microsoft Store y" >&2
        echo "   Google Play, y ahí una versión no se republica ni se retira." >&2
        echo "   Override consciente: IMAGE_TAGS_ALLOW_UNVERIFIED=1" >&2
        exit 1
    fi

    # Solo semver X.Y.Z: los tags móviles (`1.2`, `1`, `latest`) no son versiones.
    published=$(printf '%s\n' "$published" | grep -E '^[0-9]+\.[0-9]+\.[0-9]+$' || true)

    if printf '%s\n' "$published" | grep -qxF "$version"; then
        echo "❌ image-tags: '$image:$version' YA está publicado." >&2
        echo "   Un tag inmutable que se puede mover convierte «vuelve a $version» en una promesa" >&2
        echo "   vacía — y es el tag del que depende el rollback. Sube la versión y re-etiqueta." >&2
        exit 1
    fi

    # Monótona: la más alta publicada tiene que quedarse por debajo.
    highest=""
    for candidate in $published; do
        if [ -z "$highest" ] || version_gt "$candidate" "$highest"; then highest="$candidate"; fi
    done
    if [ -n "$highest" ] && ! version_gt "$version" "$highest"; then
        echo "❌ image-tags: '$version' no es mayor que la última publicada ('$highest')." >&2
        echo "   Retroceder no es un error que se corrija: el MISMO tag publica la app en Microsoft" >&2
        echo "   Store y Google Play, y ahí las versiones son monótonas e IRREVERSIBLES." >&2
        exit 1
    fi
fi

# ── The tags ─────────────────────────────────────────────────────────────────
tags=""
if [ "$is_release" -eq 1 ]; then
    tags="$image:$version
$image:$minor
$image:$major
"
fi
tags="$tags$image:latest
$image:$sha"

echo "version=$version"
printf '%s\n' "$tags"

if [ -n "${GITHUB_OUTPUT:-}" ]; then
    {
        echo "version=$version"
        echo "image=$image"
        echo "is_release=$is_release"
        echo "tags<<TAGS_EOF"
        printf '%s\n' "$tags"
        echo "TAGS_EOF"
    } >> "$GITHUB_OUTPUT"
fi
