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
#   version=…          ← what the workflow stamps into Cargo.toml before the build (stamp=1),
#                        so `/readyz`, `/api/hub/context`, the heartbeat and `error_sink` all
#                        report the number the image is called by.
#   stamp=0|1          ← whether the workflow must rewrite Cargo.toml with `version`.
#
# Release CHANNELS (hub#1170, decision of 2026-08-25). Every build also gets `:<sha>` (immutable):
#
#   final tag vX.Y.Z    → version X.Y.Z            tags :X.Y.Z :X.Y :X :latest :stable
#                          `stable` is an ALIAS of `latest` (same digest): the tag every real hub's
#                          service is registered with, and what a new hub starts on.
#   rc tag vX.Y.Z-rc.N  → version X.Y.Z-rc.N       tags :X.Y.Z-rc.N :canary
#                          The candidate promoted to a SUBSET of prod hubs. Never moves `:latest`,
#                          `:X.Y` or `:X`: a new hub must keep starting on the last final release.
#   push to develop     → version X.Y.Z-dev.<n>+g<sha>   tags :dev
#                          (also a manual `workflow_dispatch` from develop — the REF decides, not
#                          the event.) X.Y.Z is the last reachable `v*` tag and <n> the commits
#                          since, both from `git describe --tags --long`. This is what pre deploys.
#   push to main        → version from Cargo.toml   tags :latest         (unchanged: main = prod)
#   any other branch    → version X.Y.Z-dev.<n>+g<sha>   tags (sha only) — point ONE hub at it.
#
# Why the prerelease version exists: a manual build of `develop` used to publish `:<sha>` whose
# binary said `1.0.0` — the Cargo placeholder — because only `v*` tags were stamped. The canary in
# pre judged capabilities BY VERSION and quarantined an image that had every one of them.
#
# NIEGA la publicación (exit 1) cuando:
#   · la versión no es semver `X.Y.Z` (o `X.Y.Z-rc.N` en un tag rc), o sigue siendo el hueco `0.0.0`;
#   · en `develop`/una rama no hay `git describe` utilizable (checkout sin tags): servir el hueco
#     del Cargo desde ahí es exactamente el bug de hub#1170;
#   · esa versión YA está en el registro. Un tag inmutable que un segundo build puede mover
#     convierte «vuelve a 1.2.3» en una promesa vacía — y es el tag del que depende el rollback;
#   · la versión es MENOR O IGUAL que la última publicada. Retroceder no es un error que se corrija:
#     las stores no vuelven atrás;
#   · no se puede LEER el registro. Refuse-by-default a propósito: una release es un gesto raro y
#     deliberado, y publicar sin poder comprobar la monotonía es justo lo que no se deshace.
#     Override consciente: `IMAGE_TAGS_ALLOW_UNVERIFIED=1`.
#
# Usage:
#   scripts/image-tags.sh --image ghcr.io/erplora/hub --ref "$GITHUB_REF" --sha "$GITHUB_SHA" \
#                         [--describe "$(git describe --tags --long --match 'v*')"]
#   Without `--describe` the script runs that `git describe` itself in the manifest's directory.
#
# Seam used by scripts/tests/image-tags.test.sh:
#   IMAGE_TAGS_PUBLISHED_CMD  <cmd> → escribe en stdout las versiones ya publicadas, una por línea.
#                                     Exit != 0 = no se pudo leer el registro.
#   --describe <text>         → la salida de `git describe --tags --long --match 'v*'` (vacío = falló).
# ─────────────────────────────────────────────────────────────────────────────
set -uo pipefail

manifest=""
image=""
ref=""
sha=""
describe=""
describe_given=0

while [ $# -gt 0 ]; do
    case "$1" in
        --manifest) manifest="$2"; shift 2 ;;
        --image)    image="$2";    shift 2 ;;
        --ref)      ref="$2";      shift 2 ;;
        --sha)      sha="$2";      shift 2 ;;
        --describe) describe="$2"; describe_given=1; shift 2 ;;
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

# ── ¿Qué canal es esto? ──────────────────────────────────────────────────────
#   release  → tag `vX.Y.Z` (final)          canal `stable` (= `latest`)
#   rc       → tag `vX.Y.Z-rc.N`             canal `canary`
#   main     → push a `main`                 `latest` (como siempre: main = prod)
#   develop  → push/dispatch en `develop`    canal `dev` (lo que despliega pre)
#   branch   → cualquier otra rama           solo `:<sha>`
is_release=0
channel="branch"
case "$ref" in
    refs/tags/v*)
        tag_version="${ref#refs/tags/v}"
        case "$tag_version" in
            *-*) channel="rc" ;;
            *)   channel="release"; is_release=1 ;;
        esac ;;
    refs/heads/main)    channel="main" ;;
    refs/heads/develop) channel="develop" ;;
esac

# ── La versión ───────────────────────────────────────────────────────────────
# release/rc: del TAG. main: del manifest (como siempre). develop/rama: prerelease derivada de
# `git describe` — el Cargo del árbol es el hueco «en desarrollo» y servirlo es el bug de hub#1170.
stamp=1
if [ "$channel" = "release" ] || [ "$channel" = "rc" ]; then
    version="$tag_version"
    source_of_version="el tag $ref"
elif [ "$channel" = "develop" ] || [ "$channel" = "branch" ]; then
    if [ "$describe_given" -eq 0 ]; then
        describe=$(git -C "$(dirname -- "$manifest")" describe --tags --long --match 'v*' 2>/dev/null || true)
    fi
    # vX.Y.Z-<n>-g<sha>  →  X.Y.Z-dev.<n>+g<sha>   (semver 2.0: prerelease + build metadata)
    if ! grep -qE '^v[0-9]+\.[0-9]+\.[0-9]+-[0-9]+-g[0-9a-f]+$' <<<"$describe"; then
        echo "❌ image-tags: no hay un \`git describe --tags --long --match 'v*'\` utilizable para $ref" >&2
        echo "   (salida: '${describe:-<vacía>}'). Sin él la imagen serviría el hueco del Cargo.toml —" >&2
        echo "   exactamente el bug de hub#1170. ¿El checkout trae los tags? (fetch-depth: 0)" >&2
        exit 1
    fi
    base="${describe#v}"; base="${base%%-*}"
    rest="${describe#v*-}"; count="${rest%%-*}"; gsha="${rest#*-g}"
    version="$base-dev.$count+g$gsha"
    source_of_version="git describe ($describe)"
else
    stamp=0
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

# Núcleo X.Y.Z de la versión (sin prerelease ni metadatos): lo que se compara y lo que da `:X.Y`/`:X`.
core="${version%%[-+]*}"
if ! grep -qE '^[0-9]+\.[0-9]+\.[0-9]+$' <<<"$core"; then
    echo "❌ image-tags: '$version' no es semver X.Y.Z (viene de $source_of_version)." >&2
    echo "   El criterio de qué es MAJOR/MINOR/PATCH: architecture/hub/versioning.md" >&2
    exit 1
fi
if [ "$channel" = "rc" ] && ! grep -qE '^[0-9]+\.[0-9]+\.[0-9]+-rc\.[0-9]+$' <<<"$version"; then
    echo "❌ image-tags: '$version' no es una candidata \`X.Y.Z-rc.N\` (viene de $source_of_version)." >&2
    echo "   Solo las \`-rc.N\` tienen canal (canary); cualquier otra prerelease en un tag es un error." >&2
    exit 1
fi

if [ "$version" = "0.0.0" ]; then
    echo "❌ image-tags: la versión es '0.0.0' — eso es el hueco sin rellenar, no una versión." >&2
    exit 1
fi

major="${core%%.*}"
minor="${core%.*}"   # X.Y.Z → X.Y

# Las etiquetas que el REGISTRO dice tener, una por línea. Devuelve ≠0 si no se puede leer: el
# que llama decide, y decide negarse.
#
# Antes esto se lo preguntaba a la API de paquetes de la ORGANIZACIÓN
# (`gh api /orgs/<org>/packages/container/<pkg>/versions`), lo que ataba el build a dos cosas que
# no hacen falta: el binario `gh` y un token con alcance de organización. El 2026-08-11, al mover
# la CI al runner propio (`ci-runner-1`), esa llamada empezó a fallar y este guardarraíl —que se
# niega por defecto, y hace bien— bloqueó una release entera sin que el tag tuviera nada malo.
# El registro es la fuente que importa (es donde se publica) y el workflow ya se ha autenticado
# contra él con el `docker login` del paso anterior, así que basta el mismo `GITHUB_TOKEN`.
registry_tags() { # $1 = <owner>/<package>
    local repo="$1" base token url headers body
    base="${IMAGE_TAGS_REGISTRY_BASE:-https://ghcr.io}"
    token=$(curl -fsS --max-time 30 -u "${GITHUB_ACTOR:-github-actions}:${GH_TOKEN:-}" \
        "$base/token?service=ghcr.io&scope=repository:${repo}:pull" 2>/dev/null |
        jq -r '.token // empty' 2>/dev/null) || return 1
    [ -n "$token" ] || return 1

    headers=$(mktemp); body=$(mktemp)
    # `n=1000` y aun así se pagina: cada push a `main` publica un tag por commit, así que la lista
    # crece sin parar. Una página perdida es una versión que no se ve — y una versión que no se ve
    # es una que este guardarraíl dejaría republicar encima de la que ya está en producción.
    url="$base/v2/${repo}/tags/list?n=1000"
    while [ -n "$url" ]; do
        if ! curl -fsS --max-time 60 -D "$headers" -o "$body" \
            -H "Authorization: Bearer $token" "$url" 2>/dev/null; then
            rm -f "$headers" "$body"
            return 1
        fi
        jq -r '.tags[]?' < "$body" 2>/dev/null
        # Link: <...>; rel="next"  → ruta relativa al registro.
        url=$(sed -n 's/.*[Ll]ink:[[:space:]]*<\([^>]*\)>;[[:space:]]*rel="next".*/\1/p' "$headers" | head -1)
        [ -n "$url" ] && url="$base$url"
    done
    rm -f "$headers" "$body"
}

# ── El tag no se cree a ciegas ───────────────────────────────────────────────
# Vale para la final Y la rc: las dos publican un tag inmutable (`:X.Y.Z` / `:X.Y.Z-rc.N`).
if [ "$is_release" -eq 1 ] || [ "$channel" = "rc" ]; then
    published_cmd="${IMAGE_TAGS_PUBLISHED_CMD:-}"
    if [ -n "$published_cmd" ]; then
        published=$("$published_cmd") || published_failed=1
    else
        published=$(registry_tags "${image#ghcr.io/}") || published_failed=1
    fi

    if [ "${published_failed:-0}" = "1" ] && [ "${IMAGE_TAGS_ALLOW_UNVERIFIED:-0}" != "1" ]; then
        echo "❌ image-tags: no he podido leer las versiones publicadas de $image." >&2
        echo "   No publico sin comprobarlo: el MISMO tag dispara la app hacia Microsoft Store y" >&2
        echo "   Google Play, y ahí una versión no se republica ni se retira." >&2
        echo "   Override consciente: IMAGE_TAGS_ALLOW_UNVERIFIED=1" >&2
        exit 1
    fi

    # Finales `X.Y.Z` y candidatas `X.Y.Z-rc.N`: los tags móviles (`1.2`, `1`, `latest`, `canary`,
    # `dev`) no son versiones.
    published=$(printf '%s\n' "$published" | grep -E '^[0-9]+\.[0-9]+\.[0-9]+(-rc\.[0-9]+)?$' || true)
    published_final=$(printf '%s\n' "$published" | grep -E '^[0-9]+\.[0-9]+\.[0-9]+$' || true)

    if grep -qxF "$version" <<<"$published"; then
        echo "❌ image-tags: '$image:$version' YA está publicado." >&2
        # `${version}` con llaves a propósito: pegado a `»` (un byte alto), bash se come el primer
        # byte del carácter como parte del nombre y `set -u` mata el script con «unbound variable»
        # JUSTO en la rama que existe para explicar la negativa. Salía con código 1, sí, pero el
        # operador leía un error del intérprete en vez del motivo.
        echo "   Un tag inmutable que se puede mover convierte «vuelve a ${version}» en una promesa" >&2
        echo "   vacía — y es el tag del que depende el rollback. Sube la versión y re-etiqueta." >&2
        exit 1
    fi

    # Monótona: la FINAL más alta publicada tiene que quedarse por debajo del núcleo X.Y.Z.
    # Para una rc eso también dice «no hay candidata de una versión ya cerrada»: 1.2.0 publicada
    # ⇒ v1.2.0-rc.2 se rechaza. Entre rcs de la misma versión manda la inmutabilidad de arriba.
    highest=""
    for candidate in $published_final; do
        if [ -z "$highest" ] || version_gt "$candidate" "$highest"; then highest="$candidate"; fi
    done
    if [ -n "$highest" ] && ! version_gt "$core" "$highest"; then
        echo "❌ image-tags: '$version' no es mayor que la última publicada ('$highest')." >&2
        echo "   Retroceder no es un error que se corrija: el MISMO tag publica la app en Microsoft" >&2
        echo "   Store y Google Play, y ahí las versiones son monótonas e IRREVERSIBLES." >&2
        exit 1
    fi
fi

# ── The tags ─────────────────────────────────────────────────────────────────
# `:latest` is the tag every real hub's service is registered with (Cloud/Dokploy
# provisioning), so it may only move from `main` or from a release tag `v*` (hub#872).
# `workflow_dispatch` runs this from ANY ref: a manual build from `develop` or a work
# branch publishes ONLY the immutable `:<sha>` — enough to point one specific hub at it
# without changing the code of the whole fleet.
# Channels (hub#1170): `stable` is an alias of `latest` (a final tag moves both, same digest),
# `canary` follows the last rc tag, `dev` follows `develop`. A prerelease `X.Y.Z-dev.n+g…` is
# NOT a docker tag (`+` is not allowed, and it is not immutable anyway): `:dev` + `:<sha>` only.
tags=""
case "$channel" in
    release) tags="$image:$version
$image:$minor
$image:$major
$image:latest
$image:stable
" ;;
    rc)      tags="$image:$version
$image:canary
" ;;
    main)    tags="$image:latest
" ;;
    develop) tags="$image:dev
" ;;
    branch)  tags="" ;;
esac
tags="$tags$image:$sha"

echo "version=$version"
echo "channel=$channel"
echo "stamp=$stamp"
printf '%s\n' "$tags"

if [ -n "${GITHUB_OUTPUT:-}" ]; then
    {
        echo "version=$version"
        echo "channel=$channel"
        echo "stamp=$stamp"
        echo "image=$image"
        echo "is_release=$is_release"
        echo "tags<<TAGS_EOF"
        printf '%s\n' "$tags"
        echo "TAGS_EOF"
    } >> "$GITHUB_OUTPUT"
fi
