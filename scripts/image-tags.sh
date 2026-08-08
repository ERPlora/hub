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
# It REFUSES (exit 1) rather than publish when:
#   · the version is not strict semver, or is the `0.0.0` placeholder;
#   · a `v*` tag disagrees with `Cargo.toml` — either the bump was forgotten or the tag was
#     mistyped, and both only surface later as a hub reporting a version nobody released;
#   · the version is ALREADY in the registry. An immutable tag that a second build can move is
#     worse than no tag: "roll back to 1.2.3" stops meaning anything.
#
# Usage:
#   scripts/image-tags.sh --image ghcr.io/erplora/hub --ref "$GITHUB_REF" --sha "$GITHUB_SHA"
#
# Seam used by scripts/tests/image-tags.test.sh:
#   IMAGE_TAGS_PUBLISHED_CMD  <cmd> <version> → exit 0 if that version is already published
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

# ── The version, read from [workspace.package] ───────────────────────────────
# Anchored to the section: a `version = "…"` line also appears under every `[dependencies.*]`,
# and taking the first match in the file would pick up whichever dependency sorted first.
version=$(awk '
    /^\[workspace\.package\]/ { in_section = 1; next }
    /^\[/                     { in_section = 0 }
    in_section && /^[[:space:]]*version[[:space:]]*=/ {
        gsub(/.*=[[:space:]]*"|".*/, ""); print; exit
    }
' "$manifest")

if [ -z "$version" ]; then
    echo "❌ image-tags: no encuentro 'version' en [workspace.package] de $manifest" >&2
    exit 1
fi

if ! printf '%s' "$version" | grep -qE '^[0-9]+\.[0-9]+\.[0-9]+$'; then
    echo "❌ image-tags: '$version' no es semver X.Y.Z (en $manifest)." >&2
    echo "   El criterio de qué es MAJOR/MINOR/PATCH: architecture/hub/versioning.md" >&2
    exit 1
fi

if [ "$version" = "0.0.0" ]; then
    echo "❌ image-tags: la versión sigue siendo '0.0.0' — eso es el hueco sin rellenar, no una versión." >&2
    echo "   Pon la versión real en [workspace.package] de $manifest." >&2
    exit 1
fi

major="${version%%.*}"
minor="${version%.*}"   # X.Y.Z → X.Y

# ── Is this a release? ───────────────────────────────────────────────────────
is_release=0
case "$ref" in
    refs/tags/v*)
        is_release=1
        tag_version="${ref#refs/tags/v}"
        if [ "$tag_version" != "$version" ]; then
            echo "❌ image-tags: el tag dice '$tag_version' y Cargo.toml dice '$version'." >&2
            echo "   Uno de los dos está mal: o falta el bump en [workspace.package], o el tag" >&2
            echo "   está mal escrito. Publicar así deja un hub reportando una versión que nadie" >&2
            echo "   ha lanzado." >&2
            exit 1
        fi
        ;;
esac

# ── Nobody overwrites an immutable tag ───────────────────────────────────────
# Only on a release: on `main` the registry is not consulted at all, or every dev build after a
# release would be blocked by that release's own tag.
if [ "$is_release" -eq 1 ]; then
    published_cmd="${IMAGE_TAGS_PUBLISHED_CMD:-}"
    if [ -z "$published_cmd" ]; then
        # Default probe: ask the registry for that exact tag. Uses the login the workflow already
        # did; no extra token and no packages API.
        published() { docker manifest inspect "$image:$1" >/dev/null 2>&1; }
    else
        published() { "$published_cmd" "$1"; }
    fi

    if published "$version"; then
        echo "❌ image-tags: '$image:$version' YA está publicado." >&2
        echo "   Un tag inmutable que se puede mover convierte «vuelve a $version» en una" >&2
        echo "   promesa vacía. Sube la versión en [workspace.package] y vuelve a etiquetar." >&2
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
