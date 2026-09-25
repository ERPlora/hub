#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Contract test: a THIRD-PARTY handler compiles against `erplora-guest-sdk` with NO ERPlora
# repository next to it — ERPlora/hub#2115 (from module-toolkit#277).
#
# What it guards. A vendor writes the server half of their module as a Rust handler compiled to
# WASM. Every route to the SDK they had was closed:
#
#   * `path = "../../../../hub/crates/guest-sdk"` — the directory only exists inside ERPlora/hub;
#   * copying that directory out — `crates/guest-sdk/Cargo.toml` inherits `version`, `edition`,
#     `license` and `[lints]` from the hub workspace, so cargo stops at «failed to find a
#     workspace root»;
#   * `{ git = "…/hub", tag = "vX.Y.Z" }` (hub#1236) — ERPlora/hub is a PRIVATE repository.
#
# The consumable form is the one cargo itself builds for a registry: `cargo package` normalises
# the manifest (inherited fields resolved, `path` deps rejected). `scripts/package-guest-sdk.sh`
# emits exactly that, and this file proves it is enough: it builds a minimal handler — cdylib,
# `extism-pdk`, the same shape `erplora g module` generates — for `wasm32-unknown-unknown`, in a
# directory OUTSIDE this repository, depending on nothing but the packaged SDK and crates.io.
#
# Control positive: the same handler pointed at a RAW copy of `crates/guest-sdk` must fail. If it
# ever stops failing, the premise changed and this test no longer tells the two apart.
#
# Run:  bash scripts/tests/guest-sdk-standalone.test.sh
# Needs cargo + the `wasm32-unknown-unknown` target (rust-toolchain.toml) and crates.io access.
# ─────────────────────────────────────────────────────────────────────────────
set -uo pipefail

repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
package_script="$repo_root/scripts/package-guest-sdk.sh"
test_workflow="$repo_root/.github/workflows/test-hub.yml"

pass=0
fail=0
ok()  { printf '  \033[32m✓\033[0m %s\n' "$1"; pass=$((pass + 1)); }
bad() { printf '  \033[31m✗\033[0m %s\n     %s\n' "$1" "$2"; fail=$((fail + 1)); }

# `[workspace.package] version` of the hub — the number a release stamps (publish-sdks.test.sh).
workspace_version=$(awk '
    $0 == "[workspace.package]" { inside = 1; next }
    /^\[/ { inside = 0 }
    inside && /^[[:space:]]*version[[:space:]]*=/ { gsub(/.*=[[:space:]]*"|".*/, ""); print; exit }
' "$repo_root/Cargo.toml")

# The handler lives outside the repo, where rust-toolchain.toml does not reach: pin the same
# channel explicitly so the wasm32 target it installs is the one used.
toolchain_channel=$(awk -F'"' '/^[[:space:]]*channel[[:space:]]*=/ { print $2; exit }' "$repo_root/rust-toolchain.toml")
export RUSTUP_TOOLCHAIN="${toolchain_channel:-stable}"
# Build cache only: where artefacts land does not change how the crates resolve.
export CARGO_TARGET_DIR="$repo_root/target/guest-sdk-standalone"

work=$(mktemp -d "${TMPDIR:-/tmp}/guest-sdk-standalone.XXXXXX")
work=$(CDPATH= cd -- "$work" && pwd)   # macOS's $TMPDIR ends in `/`: normalise the `//`
trap 'rm -rf "$work"' EXIT

echo "hub#2115 — erplora-guest-sdk compiles a handler outside ERPlora/hub"

case "$work/" in
    "$repo_root"/*) bad "scratch dir is outside the hub tree" "$work is inside $repo_root" ;;
    *) ok "scratch dir is outside the hub tree ($work)" ;;
esac

# A minimal handler, as a vendor would write it. $1 = dir, $2 = path to the SDK crate.
write_handler() {
    mkdir -p "$1/src"
    cat >"$1/Cargo.toml" <<EOF
[package]
name = "vendor-handler"
version = "0.1.0"
edition = "2021"

[lib]
crate-type = ["cdylib", "rlib"]

[features]
guest = ["dep:extism-pdk"]

[dependencies]
erplora-guest-sdk = { path = "$2" }
extism-pdk = { version = "1", optional = true }
serde_json = "1"

[workspace]
EOF
    cat >"$1/src/lib.rs" <<'EOF'
use erplora_guest_sdk::{money, Input, Output};

pub fn quote(input: Input) -> Output {
    let price = money::from_json(&input.value()["price"], 0);
    Output::new().with_result(serde_json::json!({ "price": price }))
}

#[cfg(feature = "guest")]
#[extism_pdk::plugin_fn]
pub fn quote_price(
    input: extism_pdk::Json<Input>,
) -> extism_pdk::FnResult<extism_pdk::Json<Output>> {
    Ok(extism_pdk::Json(erplora_guest_sdk::run(input.into_inner(), quote)))
}
EOF
}

# ── 1. The packaging script emits a self-contained crate ─────────────────────
sdk_dir=""
if [ ! -x "$package_script" ]; then
    bad "scripts/package-guest-sdk.sh exists and is executable" "missing: $package_script"
else
    if sdk_dir=$("$package_script" "$work/sdk" 2>"$work/package.log"); then
        ok "package-guest-sdk.sh emitted $sdk_dir"
    else
        bad "package-guest-sdk.sh succeeds" "$(tail -5 "$work/package.log")"
        sdk_dir=""
    fi
fi

if [ -n "$sdk_dir" ] && [ -f "$sdk_dir/Cargo.toml" ]; then
    case "$sdk_dir/" in
        "$work"/*) ok "the packaged crate lands in the requested directory" ;;
        *) bad "the packaged crate lands in the requested directory" "got $sdk_dir" ;;
    esac
    if grep -qE 'workspace[[:space:]]*=[[:space:]]*true|\.workspace[[:space:]]*=' "$sdk_dir/Cargo.toml"; then
        bad "the packaged manifest inherits nothing from the hub workspace" \
            "$(grep -nE 'workspace' "$sdk_dir/Cargo.toml")"
    else
        ok "the packaged manifest inherits nothing from the hub workspace"
    fi
    packaged_version=$(awk '
        $0 == "[package]" { inside = 1; next }
        /^\[/ { inside = 0 }
        inside && /^[[:space:]]*version[[:space:]]*=/ { gsub(/.*=[[:space:]]*"|".*/, ""); print; exit }
    ' "$sdk_dir/Cargo.toml")
    if [ -n "$workspace_version" ] && [ "$packaged_version" = "$workspace_version" ]; then
        ok "packaged version $packaged_version matches the hub version"
    else
        bad "packaged version matches the hub version" \
            "packaged '$packaged_version' vs workspace '$workspace_version'"
    fi
else
    [ -n "$sdk_dir" ] && bad "the packaged crate has a Cargo.toml" "none under '$sdk_dir'"
fi

# ── 2. A handler builds to wasm against it, outside the tree ─────────────────
if [ -n "$sdk_dir" ] && [ -f "$sdk_dir/Cargo.toml" ]; then
    write_handler "$work/handler" "$sdk_dir"
    if cargo build --quiet --release --target wasm32-unknown-unknown --features guest \
        --manifest-path "$work/handler/Cargo.toml" >"$work/build.log" 2>&1; then
        wasm="$CARGO_TARGET_DIR/wasm32-unknown-unknown/release/vendor_handler.wasm"
        if [ -s "$wasm" ]; then
            ok "a vendor handler builds to wasm32 against the packaged SDK"
        else
            bad "the build produced vendor_handler.wasm" "no file at $wasm"
        fi
    else
        bad "a vendor handler builds to wasm32 against the packaged SDK" "$(tail -8 "$work/build.log")"
    fi
fi

# ── 3. Control positive: the raw crate directory does NOT build on its own ───
cp -R "$repo_root/crates/guest-sdk" "$work/raw-guest-sdk"
write_handler "$work/raw-handler" "$work/raw-guest-sdk"
if cargo metadata --format-version 1 --no-deps --manifest-path "$work/raw-handler/Cargo.toml" \
    >/dev/null 2>"$work/raw.log"; then
    bad "control: a raw copy of crates/guest-sdk fails outside the hub" \
        "it resolved — the source manifest no longer inherits from the workspace; revisit this test"
elif grep -q 'workspace root' "$work/raw.log"; then
    ok "control: a raw copy of crates/guest-sdk fails outside the hub (no workspace root)"
else
    bad "control: the raw copy fails for the workspace-root reason" "$(tail -4 "$work/raw.log")"
fi

# ── 4. This contract runs somewhere ──────────────────────────────────────────
if grep -qE '^[[:space:]]*run:[[:space:]]*bash scripts/tests/guest-sdk-standalone\.test\.sh' "$test_workflow"; then
    ok "test-hub.yml runs this contract"
else
    bad "test-hub.yml runs this contract" "no step invokes it — a guard nobody runs is a belief (hub#1240)"
fi

printf '\n%d passed, %d failed\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
