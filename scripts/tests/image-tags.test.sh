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
for v in $PUBLISHED; do [ "$v" = "$1" ] && exit 0; done
exit 1
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
make_manifest "1.2.3"
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

# ── The version comes from Cargo.toml, NOT from the ref ──────────────────────────────
# `:X.Y.Z` naming itself after the git ref is how the image and the binary drift apart.
make_manifest "2.5.0"
PUBLISHED="" run "refs/heads/main"
[ "$status" -eq 0 ] || fail "a push to main should be accepted (got $status): $(cat "$tmp_dir/out")"
grep -qxF "ghcr.io/erplora/hub:latest" "$tmp_dir/out" || fail "main must publish :latest"
grep -qxF "ghcr.io/erplora/hub:abc1234def" "$tmp_dir/out" || fail "main must publish the sha tag"
grep -qxF "ghcr.io/erplora/hub:2.5.0" "$tmp_dir/out" \
    && fail "a push to main must NOT publish the immutable :X.Y.Z — only a release tag does"
grep -q "^version=2.5.0$" "$tmp_dir/out" || fail "the reported version must come from Cargo.toml"
passed=$((passed + 1))

# ── A tag that disagrees with Cargo.toml is refused ──────────────────────────────────
make_manifest "1.2.3"
PUBLISHED="" run "refs/tags/v9.9.9"
[ "$status" -ne 0 ] || fail "a tag that does not match Cargo.toml must be REFUSED"
grep -qi "1.2.3" "$tmp_dir/out" || fail "the refusal should name the version it found"
grep -qi "9.9.9" "$tmp_dir/out" || fail "the refusal should name the tag it was given"
passed=$((passed + 1))

# ── Republishing a version already in the registry is refused ────────────────────────
# `:1.2.3` is what a rollback pins to. If a second build can move it, the pin is a lie.
make_manifest "1.2.3"
PUBLISHED="1.2.3" run "refs/tags/v1.2.3"
[ "$status" -ne 0 ] || fail "an already-published version must be REFUSED, not overwritten"
grep -qi "1.2.3" "$tmp_dir/out" || fail "the refusal should name the version"
passed=$((passed + 1))

# ── A published NEIGHBOUR does not block a new version ───────────────────────────────
make_manifest "1.2.4"
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
PUBLISHED="" run "refs/tags/v1.2"
[ "$status" -ne 0 ] || fail "a non-semver version must be REFUSED"
passed=$((passed + 1))

printf 'PASS: %s image-tags contract cases\n' "$passed"
