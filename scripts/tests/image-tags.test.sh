#!/usr/bin/env bash
# Contract tests for scripts/image-tags.sh — the guard that stands between a build and GHCR (hub#515).
#
# What it protects, and why each case is here:
#
#   · `Cargo.toml` is the ONE source of truth for the hub's version. Before this, the image
#     version came from the git ref: a `v1.2.3` tag said "1.2.3" and a push to `main` said the
#     short sha. So the number on the image and the number the binary reports could disagree,
#     and on `main` the shell's footer showed a SHA where a version belongs.
#
#   · An immutable tag that gets overwritten is worse than no tag. `:1.2.3` is the thing a
#     rollback pins to; if a second build can move it, "roll back to 1.2.3" stops meaning
#     anything. Publishing an already-published version must FAIL, not overwrite.
#
#   · A `v*` tag that does not match `Cargo.toml` is always a mistake — either the bump was
#     forgotten or the tag was typed wrong — and it is the kind that only shows up much later,
#     as a hub reporting a version nobody released.
#
# The registry is stubbed (IMAGE_TAGS_PUBLISHED_CMD seam) so these stay hermetic and offline.

set -uo pipefail

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
script="$script_dir/../image-tags.sh"
tmp_dir=$(mktemp -d "${TMPDIR:-/tmp}/erplora-image-tags-test.XXXXXX")
trap 'rm -rf "$tmp_dir"' EXIT HUP INT TERM

passed=0

fail() {
    printf 'FAIL: %s\n' "$1" >&2
    exit 1
}

# A workspace manifest carrying `version` in [workspace.package], like the real one.
make_manifest() { # $1=version
    mkdir -p "$tmp_dir/repo"
    cat > "$tmp_dir/repo/Cargo.toml" <<EOF
[workspace]
resolver = "2"
members = ["crates/server"]

[workspace.package]
edition = "2021"
version = "$1"
license = "MIT"
EOF
}

# Stub registry: PUBLISHED lists the versions it should claim already exist.
published_stub="$tmp_dir/published"
cat > "$published_stub" <<'EOF'
#!/bin/sh
# Lista las versiones ya publicadas, una por línea (el registro real hace lo mismo vía GHCR).
# El centinela simula un registro que no se puede leer (red caída, token sin permiso).
[ "$PUBLISHED" = "__unreadable__" ] && exit 1
for v in $PUBLISHED; do echo "$v"; done
EOF
chmod +x "$published_stub"

run() { # $1=git ref ; stdout+stderr -> $tmp_dir/out ; sets $status
    PUBLISHED="${PUBLISHED:-}" \
    IMAGE_TAGS_PUBLISHED_CMD="$published_stub" \
        "$script" --manifest "$tmp_dir/repo/Cargo.toml" --image ghcr.io/erplora/hub \
                  --ref "$1" --sha abc1234def > "$tmp_dir/out" 2>&1
    status=$?
}

# ── A version tag publishes the three moving/immutable tags ──────────────────────────
# La versión sale del TAG, no del manifest: el mismo tag dispara `tauri-release.yml`, así que el
# número que va a las stores y el de la imagen tienen que ser EL MISMO, y solo hay un sitio donde
# se escribe una vez — el tag.
make_manifest "0.9.0"
PUBLISHED="" run "refs/tags/v1.2.3"
[ "$status" -eq 0 ] || fail "a matching tag should be accepted (got $status): $(cat "$tmp_dir/out")"
for expected in \
    "ghcr.io/erplora/hub:1.2.3" \
    "ghcr.io/erplora/hub:1.2" \
    "ghcr.io/erplora/hub:1" \
    "ghcr.io/erplora/hub:latest" \
    "ghcr.io/erplora/hub:abc1234def"
do
    grep -qxF "$expected" "$tmp_dir/out" || fail "a version tag must publish $expected — got: $(cat "$tmp_dir/out")"
done
passed=$((passed + 1))

# ── Fuera de una release, la versión sale de Cargo.toml (build de integración) ────────
make_manifest "2.5.0"
PUBLISHED="" run "refs/heads/main"
[ "$status" -eq 0 ] || fail "a push to main should be accepted (got $status): $(cat "$tmp_dir/out")"
grep -qxF "ghcr.io/erplora/hub:latest" "$tmp_dir/out" || fail "main must publish :latest"
grep -qxF "ghcr.io/erplora/hub:abc1234def" "$tmp_dir/out" || fail "main must publish the sha tag"
grep -qxF "ghcr.io/erplora/hub:2.5.0" "$tmp_dir/out" \
    && fail "a push to main must NOT publish the immutable :X.Y.Z — only a release tag does"
grep -q "^version=2.5.0$" "$tmp_dir/out" || fail "the reported version must come from Cargo.toml"
passed=$((passed + 1))

# ── Un tag que NO coincide con Cargo.toml se acepta: manda el tag ─────────────────────
# Decisión de Ioan (2026-08-09): el tag `v*` ES el evento de release —dispara la imagen Y la app
# hacia Microsoft Store / Google Play—, así que la versión se escribe una sola vez, ahí. El CI
# reescribe `Cargo.toml` desde el tag antes de compilar, para que `env!("CARGO_PKG_VERSION")` diga
# lo mismo que la imagen.
make_manifest "1.2.3"
PUBLISHED="" run "refs/tags/v2.0.0"
[ "$status" -eq 0 ] || fail "manda el tag: no tiene que coincidir con Cargo.toml"
grep -q "^version=2.0.0$" "$tmp_dir/out" || fail "la versión publicada es la del TAG"
grep -qxF "ghcr.io/erplora/hub:2.0.0" "$tmp_dir/out" || fail "el tag inmutable sale del tag de git"
passed=$((passed + 1))

# ── …pero un tag que NO es semver se rechaza ─────────────────────────────────────────
make_manifest "1.2.3"
PUBLISHED="" run "refs/tags/vdos"
[ "$status" -ne 0 ] || fail "un tag que no es semver debe RECHAZARSE"
passed=$((passed + 1))

# ── …y uno MENOR que la última publicada, también ────────────────────────────────────
# Esta es la que de verdad protege: `tauri-release.yml` corre con el MISMO tag, y las versiones de
# Microsoft Store y Google Play son monótonas e IRREVERSIBLES. Retroceder no es un error que se
# corrija: quema ese número para siempre.
make_manifest "1.2.3"
PUBLISHED="1.5.0 1.4.2" run "refs/tags/v1.3.0"
[ "$status" -ne 0 ] || fail "un tag MENOR que la última publicada debe RECHAZARSE (las stores no vuelven atrás)"
grep -qi "1.5.0" "$tmp_dir/out" || fail "el rechazo debe decir cuál es la última publicada"
passed=$((passed + 1))

# ── Y no se puede verificar el registro → no se publica ──────────────────────────────
# Refuse-by-default a propósito: una release es un gesto raro y deliberado, y publicar sin poder
# comprobar la monotonía es justo lo que no se puede deshacer. Hay override consciente.
make_manifest "1.2.3"
PUBLISHED="__unreadable__" run "refs/tags/v1.2.3"
[ "$status" -ne 0 ] || fail "si no se puede leer el registro, no se publica"
passed=$((passed + 1))

# ── Republishing a version already in the registry is refused ────────────────────────
# `:1.2.3` is what a rollback pins to. If a second build can move it, the pin is a lie.
make_manifest "0.0.1"
PUBLISHED="1.2.3" run "refs/tags/v1.2.3"
[ "$status" -ne 0 ] || fail "an already-published version must be REFUSED, not overwritten"
grep -qi "1.2.3" "$tmp_dir/out" || fail "the refusal should name the version"
passed=$((passed + 1))

# ── A published NEIGHBOUR does not block a new version ───────────────────────────────
make_manifest "0.0.1"
PUBLISHED="1.2.3 1.2.2" run "refs/tags/v1.2.4"
[ "$status" -eq 0 ] || fail "an unpublished version must pass even if its neighbours exist"
passed=$((passed + 1))

# ── `main` never consults the registry: it only moves :latest ────────────────────────
# Otherwise every dev build would be blocked by its own last release.
make_manifest "1.2.3"
PUBLISHED="1.2.3" run "refs/heads/main"
[ "$status" -eq 0 ] || fail "a push to main must not be blocked by an already-published version"
passed=$((passed + 1))

# ── 0.0.0 is refused everywhere: it is the placeholder, not a version ────────────────
make_manifest "0.0.0"
PUBLISHED="" run "refs/heads/main"
[ "$status" -ne 0 ] || fail "0.0.0 is the unset placeholder and must never reach the registry"
passed=$((passed + 1))

# ── A version that is not semver is refused ──────────────────────────────────────────
make_manifest "1.2"
PUBLISHED="" run "refs/heads/main"
[ "$status" -ne 0 ] || fail "a non-semver version must be REFUSED"
passed=$((passed + 1))

# ── The default lookup asks the REGISTRY, and never `gh` ─────────────────────────────
# Every case above stubs the lookup through the seam, so the path that actually runs in CI was
# the one nothing covered. It used to be `gh api /orgs/<org>/packages/...`, which tied the build
# to the `gh` binary and to a token with ORGANIZATION scope. On 2026-08-11, moving CI to the
# self-hosted `ci-runner-1` made that call fail, and this guard — refuse-by-default, correctly —
# blocked the whole release with nothing wrong in the tag. The published versions live in the
# registry: it is where they get published, and the workflow has already `docker login`ed to it.
#
# Unreachable registry (port 1, nothing listens) so this stays hermetic and offline: it asserts
# WHO gets asked, not what the network answers. The refusal itself is the case below it.
gh_sentinel="$tmp_dir/gh-was-called"
mkdir -p "$tmp_dir/fakebin"
cat > "$tmp_dir/fakebin/gh" <<EOF
#!/bin/sh
touch "$gh_sentinel"
exit 1
EOF
chmod +x "$tmp_dir/fakebin/gh"

make_manifest "1.4.0"
rm -f "$gh_sentinel"
PATH="$tmp_dir/fakebin:$PATH" IMAGE_TAGS_REGISTRY_BASE="http://127.0.0.1:1" \
    "$script" --manifest "$tmp_dir/repo/Cargo.toml" --image ghcr.io/erplora/hub \
              --ref "refs/tags/v1.4.0" --sha abc1234def > "$tmp_dir/out" 2>&1
status=$?
[ ! -e "$gh_sentinel" ] || fail "the guard still asks \`gh\`: an org-scoped API call is a CI dependency it does not need"
[ "$status" -ne 0 ] || fail "a registry it cannot read must be REFUSED, not assumed empty"
grep -q "no he podido leer las versiones publicadas" "$tmp_dir/out" ||
    fail "an unreadable registry should say so, not fail silently"
passed=$((passed + 1))

# ── …and an unreadable registry is still overridable, on purpose ─────────────────────
make_manifest "1.4.0"
IMAGE_TAGS_REGISTRY_BASE="http://127.0.0.1:1" IMAGE_TAGS_ALLOW_UNVERIFIED=1 \
    "$script" --manifest "$tmp_dir/repo/Cargo.toml" --image ghcr.io/erplora/hub \
              --ref "refs/tags/v1.4.0" --sha abc1234def > "$tmp_dir/out" 2>&1
status=$?
[ "$status" -eq 0 ] || fail "IMAGE_TAGS_ALLOW_UNVERIFIED=1 is the documented escape hatch and must work"
passed=$((passed + 1))

printf 'PASS: %s image-tags contract cases\n' "$passed"
