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

# Same, with the two git seams the workflow passes: the `git describe --tags --long` output
# (hub#1170 channels) and the `git tag --list 'v*'` output (hub#1625 — the `dev` base).
# `$3` empty = the flag is NOT passed, which is also how a checkout without tags is exercised.
run_channel() { # $1=git ref ; $2=git describe output ; $3=git tag --list output (optional)
    # `${extra[@]+…}` y no `"${extra[@]}"` a secas: con `set -u`, el bash 3.2 que trae macOS
    # mata el script en un array VACÍO («extra[@]: unbound variable»), y esta batería tiene que
    # correr igual la lance el runner (bash 5) o el portátil.
    local extra=()
    [ -n "${3:-}" ] && extra=(--git-tags "$3")
    PUBLISHED="${PUBLISHED:-}" \
    IMAGE_TAGS_PUBLISHED_CMD="$published_stub" \
        "$script" --manifest "$tmp_dir/repo/Cargo.toml" --image ghcr.io/erplora/hub \
                  --ref "$1" --sha abc1234def --describe "$2" ${extra[@]+"${extra[@]}"} > "$tmp_dir/out" 2>&1
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

# ── A branch other than main NEVER moves :latest (hub#872) ───────────────────────────
# `workflow_dispatch` runs the workflow from ANY ref, and `:latest` is the tag every real
# hub's service is registered with (Cloud/Dokploy provisioning). A manual build from
# `develop` — or any work branch — must never move it. (Since hub#1170 `develop` also gets
# the moving `:dev` and a prerelease version from `git describe` — see the channel cases
# below — so this case passes a describe and a tag list; the `:latest` assertions are unchanged.)
make_manifest "2.5.0"
PUBLISHED="" run_channel "refs/heads/develop" "v1.1.7-61-g60307487" "v1.1.7"
[ "$status" -eq 0 ] || fail "a dispatch from develop should be accepted (got $status): $(cat "$tmp_dir/out")"
grep -qxF "ghcr.io/erplora/hub:latest" "$tmp_dir/out" \
    && fail "a build from develop must NOT publish :latest — that moves the whole fleet (hub#872)"
grep -qxF "ghcr.io/erplora/hub:abc1234def" "$tmp_dir/out" || fail "a build from develop must still publish the immutable sha tag"
grep -qxF "ghcr.io/erplora/hub:2.5.0" "$tmp_dir/out" \
    && fail "a build from develop must NOT publish the immutable :X.Y.Z — only a release tag does"
passed=$((passed + 1))

# ── …and neither does an arbitrary work branch ───────────────────────────────────────
make_manifest "2.5.0"
PUBLISHED="" run_channel "refs/heads/fix/some-work-branch" "v1.1.7-61-g60307487" "v1.1.7"
[ "$status" -eq 0 ] || fail "a dispatch from a work branch should be accepted (got $status): $(cat "$tmp_dir/out")"
grep -qxF "ghcr.io/erplora/hub:latest" "$tmp_dir/out" \
    && fail "a build from a work branch must NOT publish :latest (hub#872)"
grep -qxF "ghcr.io/erplora/hub:abc1234def" "$tmp_dir/out" || fail "a build from a work branch must still publish the sha tag"
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

# ═════════════════════════════════════════════════════════════════════════════════════
# Release channels (hub#1170): `dev` (develop → pre) · `canary` (rc tag) · `stable` (= latest).
#
# Why: a manual build of `develop` published `:<sha>` whose binary said `1.0.0` — the Cargo
# placeholder — because the version was only stamped on `v*` tags. The canary in pre judged
# capabilities BY VERSION and quarantined an image that had them all. Every channel now carries
# an honest version: `develop` a prerelease derived from `git describe`, an rc tag its own
# `X.Y.Z-rc.N`, and only a final `vX.Y.Z` moves `:latest`/`:stable`.
# ═════════════════════════════════════════════════════════════════════════════════════

# ── A push to `develop` publishes `:dev` + `:<sha>` with a PRERELEASE version ─────────
# `X.Y.Z` is one patch above the newest `v*` tag the repo HOLDS (hub#1625); `<n>` commits
# since the last reachable one; `+g<sha>` build metadata. The version is what `build-hub.yml`
# stamps into Cargo.toml, so `/readyz` and `/api/hub/context` report it instead of the
# placeholder.
make_manifest "1.0.0"
PUBLISHED="" run_channel "refs/heads/develop" "v1.1.7-61-g60307487" "v1.1.7"
[ "$status" -eq 0 ] || fail "a push to develop should be accepted (got $status): $(cat "$tmp_dir/out")"
grep -q "^version=1.1.8-dev.61+g60307487$" "$tmp_dir/out" \
    || fail "develop must serve a prerelease ahead of the newest release — got: $(cat "$tmp_dir/out")"
grep -qxF "ghcr.io/erplora/hub:dev" "$tmp_dir/out" || fail "develop must publish the moving :dev tag (pre deploys it)"
grep -qxF "ghcr.io/erplora/hub:abc1234def" "$tmp_dir/out" || fail "develop must publish the immutable sha tag"
grep -qxF "ghcr.io/erplora/hub:latest" "$tmp_dir/out" && fail "develop must NOT move :latest (hub#872)"
grep -qxF "ghcr.io/erplora/hub:canary" "$tmp_dir/out" && fail "develop must NOT move :canary"
grep -qxF "ghcr.io/erplora/hub:stable" "$tmp_dir/out" && fail "develop must NOT move :stable"
grep -q "^ghcr.io/erplora/hub:1\.1\.[78]" "$tmp_dir/out" && fail "develop must NOT mint a version tag"
grep -q "^stamp=1$" "$tmp_dir/out" || fail "develop must ask the workflow to stamp Cargo.toml"
passed=$((passed + 1))

# ── …and a manual `workflow_dispatch` from develop is the SAME build ─────────────────
# The ref decides, not the event: the dispatched build is what pre validates (hub#1170).
make_manifest "1.0.0"
GITHUB_EVENT_NAME=workflow_dispatch PUBLISHED="" run_channel "refs/heads/develop" "v1.1.7-61-g60307487" "v1.1.7"
[ "$status" -eq 0 ] || fail "a dispatch from develop should be accepted (got $status): $(cat "$tmp_dir/out")"
grep -q "^version=1.1.8-dev.61+g60307487$" "$tmp_dir/out" || fail "a dispatch from develop must serve the same prerelease"
grep -qxF "ghcr.io/erplora/hub:dev" "$tmp_dir/out" || fail "a dispatch from develop must publish :dev"
grep -qxF "ghcr.io/erplora/hub:latest" "$tmp_dir/out" && fail "a dispatch from develop must NOT move :latest"
passed=$((passed + 1))

# ── A work branch gets the honest prerelease too, but never a moving tag ─────────────
make_manifest "1.0.0"
PUBLISHED="" run_channel "refs/heads/fix/some-work-branch" "v1.1.7-3-gdeadbeef" "v1.1.7"
[ "$status" -eq 0 ] || fail "a work branch build should be accepted (got $status): $(cat "$tmp_dir/out")"
grep -q "^version=1.1.8-dev.3+gdeadbeef$" "$tmp_dir/out" || fail "a work branch must serve the prerelease, not the placeholder"
grep -qxF "ghcr.io/erplora/hub:dev" "$tmp_dir/out" && fail "a work branch must NOT move :dev — only develop feeds pre"
grep -qxF "ghcr.io/erplora/hub:abc1234def" "$tmp_dir/out" || fail "a work branch must still publish the sha tag"
passed=$((passed + 1))

# ── `develop` sitting exactly on a tag is still a prerelease — de la SIGUIENTE (n=0) ─
# `n=0` no significa «esto es el release»: la imagen sigue siendo `:dev`, mutable, y el
# número tiene que quedar por delante del tag para no volver a rechazar módulos (hub#1625).
make_manifest "1.0.0"
PUBLISHED="" run_channel "refs/heads/develop" "v1.1.9-0-gf2354593" "v1.1.9"
[ "$status" -eq 0 ] || fail "develop on a tag should be accepted (got $status)"
grep -q "^version=1.1.10-dev.0+gf2354593$" "$tmp_dir/out" || fail "n=0 is still a dev prerelease — got: $(cat "$tmp_dir/out")"
passed=$((passed + 1))

# ── Without a usable `git describe`, develop is REFUSED — never the placeholder ──────
# Serving `1.0.0` from a develop build is the exact bug of hub#1170. A shallow checkout
# (no tags) must fail loudly here, not publish a lying image.
make_manifest "1.0.0"
PUBLISHED="" run_channel "refs/heads/develop" ""
[ "$status" -ne 0 ] || fail "develop without git describe must be REFUSED, not served as Cargo's placeholder"
grep -qi "describe" "$tmp_dir/out" || fail "the refusal should point at git describe (fetch-depth/tags)"
passed=$((passed + 1))

make_manifest "1.0.0"
PUBLISHED="" run_channel "refs/heads/develop" "60307487"
[ "$status" -ne 0 ] || fail "a describe output with no v* tag must be REFUSED"
passed=$((passed + 1))

# ═════════════════════════════════════════════════════════════════════════════════════
# hub#1625 — el canal `dev` se numera contra los tags que el repositorio TIENE.
#
# `main` es una rama HUÉRFANA (las releases se promueven con `commit-tree`), así que desde
# `develop` ningún `v1.1.8`…`v1.1.17` es alcanzable y `git describe` se queda clavado en
# `v1.1.7`: la imagen `:dev` se estampaba `1.1.7-dev.N` con DIEZ releases por debajo del
# código que ejecuta. Consecuencia medida el 2026-09-08: `whatsapp_inbox` declara suelo
# 1.1.17 y el hub de pre lo rechazaba con «requiere ERPlora 1.1.17 y este hub es 1.1.7»,
# un módulo que ese hub sí puede ejecutar.
#
# La regla: la base sale del núcleo `X.Y.Z` MÁS ALTO entre los tags `v*` que el repositorio
# tiene —alcanzables o no— y se sube UN patch. Por delante y no por debajo: `develop` ya
# contiene lo que ese tag publicó (el tag se corta de su árbol), así que `1.1.17-dev.N`
# —que en semver 2.0 va POR DEBAJO de `1.1.17`— seguiría mintiendo en el mismo sentido.
# El `<n>` y el `+g<sha>` siguen saliendo de `git describe`: son el contador que crece
# commit a commit dentro del canal.
# ═════════════════════════════════════════════════════════════════════════════════════

# ── La base va por DELANTE del último release, aunque no sea alcanzable ───────────────
make_manifest "1.0.0"
PUBLISHED="" run_channel "refs/heads/develop" "v1.1.7-326-g24ccbdc5" "v1.1.7
v1.1.15
v1.1.16
v1.1.17"
[ "$status" -eq 0 ] || fail "develop with tags should be accepted (got $status): $(cat "$tmp_dir/out")"
grep -q "^version=1.1.18-dev.326+g24ccbdc5$" "$tmp_dir/out" \
    || fail "the dev base must be one patch above the newest tag the repo HOLDS — got: $(cat "$tmp_dir/out")"
# 🔴 El positivo que este caso tiene que cazar: si alguien vuelve a derivar la base de
# `git describe`, aquí reaparece `1.1.7-dev.326` y el módulo de WhatsApp vuelve a rechazarse.
grep -q "^version=1\.1\.7-" "$tmp_dir/out" \
    && fail "the dev base must NOT come from git describe again (hub#1625) — got: $(cat "$tmp_dir/out")"
# …y sigue siendo el canal `dev`: nada de tags de versión, nada de mover `:latest`.
grep -qxF "ghcr.io/erplora/hub:dev" "$tmp_dir/out" || fail "develop must still publish the moving :dev tag"
grep -q "^ghcr.io/erplora/hub:1\.1\.18" "$tmp_dir/out" && fail "develop must NOT mint a version tag"
passed=$((passed + 1))

# ── El tag más nuevo se elige por NÚMERO, no por orden alfabético ─────────────────────
# `sort` a secas pone `v1.1.9` por encima de `v1.1.10`, y la base saldría una release corta.
make_manifest "1.0.0"
PUBLISHED="" run_channel "refs/heads/develop" "v1.1.9-4-gfeedface" "v1.1.9
v1.1.10"
[ "$status" -eq 0 ] || fail "develop should be accepted (got $status): $(cat "$tmp_dir/out")"
grep -q "^version=1.1.11-dev.4+gfeedface$" "$tmp_dir/out" \
    || fail "the newest tag is chosen by NUMBER, not alphabetically — got: $(cat "$tmp_dir/out")"
passed=$((passed + 1))

# ── Una candidata `-rc.N` también cuenta: develop ya lleva lo que publicó ─────────────
# `1.2.0-dev.N` iría por DEBAJO de `1.2.0-rc.1` en semver, que es el mismo sentido del bug.
make_manifest "1.0.0"
PUBLISHED="" run_channel "refs/heads/develop" "v1.1.7-326-g24ccbdc5" "v1.1.17
v1.2.0-rc.1"
[ "$status" -eq 0 ] || fail "develop should be accepted (got $status): $(cat "$tmp_dir/out")"
grep -q "^version=1.2.1-dev.326+g24ccbdc5$" "$tmp_dir/out" \
    || fail "an rc tag counts towards the dev base — got: $(cat "$tmp_dir/out")"
passed=$((passed + 1))

# ── Lo que no es `vX.Y.Z` en la lista se ignora; no envenena ni sube la base ──────────
make_manifest "1.0.0"
PUBLISHED="" run_channel "refs/heads/develop" "v1.1.7-326-g24ccbdc5" "nightly
v1.1
v1.1.18.1
v2.x
v1.1.17"
[ "$status" -eq 0 ] || fail "junk tags should be ignored, not fatal (got $status): $(cat "$tmp_dir/out")"
grep -q "^version=1.1.18-dev.326+g24ccbdc5$" "$tmp_dir/out" \
    || fail "only vX.Y.Z tags count towards the dev base — got: $(cat "$tmp_dir/out")"
passed=$((passed + 1))

# ── Sin un solo tag `v*`, develop se NIEGA — nunca inventa el número ──────────────────
# Un checkout sin tags no sabe contra qué release se numera, y publicar `:dev` a ciegas es
# lo que dejó a pre diez releases por debajo. Refuse-by-default, como con `git describe`.
make_manifest "1.0.0"
PUBLISHED="" run_channel "refs/heads/develop" "v1.1.7-326-g24ccbdc5"
[ "$status" -ne 0 ] || fail "develop without any v* tag must be REFUSED, not numbered blindly"
# 🔴 No `grep -qi "tag"`: the script's own name («image-tags») satisfies that on ANY error. Without
# the guard the script still refused, but for the WRONG reason («'..1-dev…' no es semver») and
# without telling anybody the tags are missing — a mutant that survived in the hub#1674 review.
grep -q "fetch-depth" "$tmp_dir/out" \
    || fail "the refusal must point at the missing tags (fetch-depth: 0) — got: $(cat "$tmp_dir/out")"
passed=$((passed + 1))

# ── Una rama de trabajo se numera igual que develop ───────────────────────────────────
make_manifest "1.0.0"
PUBLISHED="" run_channel "refs/heads/fix/some-work-branch" "v1.1.7-3-gdeadbeef" "v1.1.7
v1.1.17"
[ "$status" -eq 0 ] || fail "a work branch should be accepted (got $status): $(cat "$tmp_dir/out")"
grep -q "^version=1.1.18-dev.3+gdeadbeef$" "$tmp_dir/out" \
    || fail "a work branch gets the same base as develop — got: $(cat "$tmp_dir/out")"
passed=$((passed + 1))

# ── Un tag de release NO mira la lista: su versión es la del tag, y nada más ──────────
make_manifest "1.0.0"
PUBLISHED="1.1.9" run_channel "refs/tags/v1.2.0" "v1.2.0-0-gcafe1234" "v1.1.17
v9.9.9"
[ "$status" -eq 0 ] || fail "a final tag should be accepted (got $status): $(cat "$tmp_dir/out")"
grep -q "^version=1.2.0$" "$tmp_dir/out" \
    || fail "a release takes its version from the TAG, never from the tag list — got: $(cat "$tmp_dir/out")"
passed=$((passed + 1))

# ── An rc tag publishes the CANARY: `:X.Y.Z-rc.N` + `:canary` + `:<sha>` ─────────────
# It never moves `:latest`, `:stable`, `:X.Y` or `:X`: a candidate goes to a subset of prod
# hubs, and a new hub must keep starting on the last final release.
make_manifest "1.0.0"
PUBLISHED="1.1.9" run_channel "refs/tags/v1.2.0-rc.1" "v1.2.0-rc.1-0-gcafe1234"
[ "$status" -eq 0 ] || fail "an rc tag should be accepted (got $status): $(cat "$tmp_dir/out")"
grep -q "^version=1.2.0-rc.1$" "$tmp_dir/out" || fail "the rc version is the tag's — got: $(cat "$tmp_dir/out")"
grep -qxF "ghcr.io/erplora/hub:1.2.0-rc.1" "$tmp_dir/out" || fail "an rc must publish its immutable :X.Y.Z-rc.N"
grep -qxF "ghcr.io/erplora/hub:canary" "$tmp_dir/out" || fail "an rc must move :canary"
grep -qxF "ghcr.io/erplora/hub:abc1234def" "$tmp_dir/out" || fail "an rc must publish the sha tag"
grep -qxF "ghcr.io/erplora/hub:latest" "$tmp_dir/out" && fail "an rc must NOT move :latest"
grep -qxF "ghcr.io/erplora/hub:stable" "$tmp_dir/out" && fail "an rc must NOT move :stable"
grep -qxF "ghcr.io/erplora/hub:1.2" "$tmp_dir/out" && fail "an rc must NOT move :X.Y"
grep -qxF "ghcr.io/erplora/hub:1" "$tmp_dir/out" && fail "an rc must NOT move :X"
grep -qxF "ghcr.io/erplora/hub:dev" "$tmp_dir/out" && fail "an rc must NOT move :dev"
grep -q "^stamp=1$" "$tmp_dir/out" || fail "an rc must ask the workflow to stamp Cargo.toml"
passed=$((passed + 1))

# ── An rc is immutable too: republishing the same rc is refused ───────────────────────
make_manifest "1.0.0"
PUBLISHED="1.1.9 1.2.0-rc.1" run_channel "refs/tags/v1.2.0-rc.1" "v1.2.0-rc.1-0-gcafe1234"
[ "$status" -ne 0 ] || fail "an already-published rc must be REFUSED"
passed=$((passed + 1))

# ── …and an rc of a version that is ALREADY FINAL is refused ─────────────────────────
make_manifest "1.0.0"
PUBLISHED="1.2.0" run_channel "refs/tags/v1.2.0-rc.2" "v1.2.0-rc.2-0-gcafe1234"
[ "$status" -ne 0 ] || fail "an rc of an already-released version must be REFUSED (1.2.0 is final)"
passed=$((passed + 1))

# ── …while rc.2 after rc.1 is fine, and so is the final after its rcs ────────────────
make_manifest "1.0.0"
PUBLISHED="1.1.9 1.2.0-rc.1" run_channel "refs/tags/v1.2.0-rc.2" "v1.2.0-rc.2-0-gcafe1234"
[ "$status" -eq 0 ] || fail "rc.2 after rc.1 must pass (got $status): $(cat "$tmp_dir/out")"
make_manifest "1.0.0"
PUBLISHED="1.1.9 1.2.0-rc.1 1.2.0-rc.2" run_channel "refs/tags/v1.2.0" "v1.2.0-0-gcafe1234"
[ "$status" -eq 0 ] || fail "the final after its rcs must pass (got $status): $(cat "$tmp_dir/out")"
grep -qxF "ghcr.io/erplora/hub:1.2.0-rc.2" "$tmp_dir/out" && fail "a final must not re-tag the rc"
passed=$((passed + 1))

# ── A prerelease tag that is not `-rc.N` is refused: there is no channel for it ───────
make_manifest "1.0.0"
PUBLISHED="" run_channel "refs/tags/v1.2.0-beta.1" "v1.2.0-beta.1-0-gcafe1234"
[ "$status" -ne 0 ] || fail "only -rc.N prereleases have a channel (canary); anything else is a typo"
passed=$((passed + 1))

# ── A final tag moves `:stable` as an alias of `:latest` (same digest) ───────────────
make_manifest "1.0.0"
PUBLISHED="1.1.9" run_channel "refs/tags/v1.2.0" "v1.2.0-0-gcafe1234"
[ "$status" -eq 0 ] || fail "a final tag should be accepted (got $status): $(cat "$tmp_dir/out")"
for expected in \
    "ghcr.io/erplora/hub:1.2.0" \
    "ghcr.io/erplora/hub:1.2" \
    "ghcr.io/erplora/hub:1" \
    "ghcr.io/erplora/hub:latest" \
    "ghcr.io/erplora/hub:stable" \
    "ghcr.io/erplora/hub:abc1234def"
do
    grep -qxF "$expected" "$tmp_dir/out" || fail "a final tag must publish $expected — got: $(cat "$tmp_dir/out")"
done
grep -qxF "ghcr.io/erplora/hub:canary" "$tmp_dir/out" && fail "a final must NOT move :canary — that is the rc's tag"
grep -qxF "ghcr.io/erplora/hub:dev" "$tmp_dir/out" && fail "a final must NOT move :dev"
passed=$((passed + 1))

# ── `main` stays as it is: `:latest` + `:<sha>`, version from Cargo.toml, no stamp ────
make_manifest "2.5.0"
PUBLISHED="" run_channel "refs/heads/main" "v1.1.8-0-gf2354593"
[ "$status" -eq 0 ] || fail "main should be accepted (got $status): $(cat "$tmp_dir/out")"
grep -q "^version=2.5.0$" "$tmp_dir/out" || fail "main keeps the Cargo.toml version"
grep -qxF "ghcr.io/erplora/hub:latest" "$tmp_dir/out" || fail "main must publish :latest"
grep -qxF "ghcr.io/erplora/hub:stable" "$tmp_dir/out" && fail "main must NOT move :stable — only a final tag does"
grep -qxF "ghcr.io/erplora/hub:dev" "$tmp_dir/out" && fail "main must NOT move :dev"
grep -q "^stamp=0$" "$tmp_dir/out" || fail "main does not stamp Cargo.toml"
passed=$((passed + 1))

printf 'PASS: %s image-tags contract cases\n' "$passed"
