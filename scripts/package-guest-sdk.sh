#!/usr/bin/env bash
# Emits `erplora-guest-sdk` as a SELF-CONTAINED crate source, buildable with no ERPlora repo next
# to it — ERPlora/hub#2115.
#
# `crates/guest-sdk/Cargo.toml` inherits `version`, `edition`, `license` and `[lints]` from the hub
# workspace, so a plain copy of the directory does not build anywhere else. `cargo package` is the
# step that turns it into what a registry receives: the manifest normalised (inherited fields
# resolved, `path` deps refused). This script runs it and unpacks the result.
#
# Usage:  scripts/package-guest-sdk.sh <out-dir>
# Prints the path of the unpacked crate (`<out-dir>/erplora-guest-sdk-<version>`) on stdout.
#
# It does NOT publish anything: the `publish-guest-sdk` job of build-hub.yml uploads the same
# crate to crates.io on every `v*` tag (hub#2119).
set -euo pipefail

if [ "$#" -ne 1 ] || [ -z "$1" ]; then
    echo "usage: $0 <out-dir>" >&2
    exit 2
fi

repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
mkdir -p "$1"
out_dir=$(CDPATH= cd -- "$1" && pwd)
package_target="$out_dir/.cargo-package"

# `--no-verify`: the build of the packaged crate is its consumer's job (see
# scripts/tests/guest-sdk-standalone.test.sh), not a second compile here.
# `--allow-dirty`: packaging a work in progress is legitimate; what ships is decided by the tag.
cargo package --quiet --no-verify --allow-dirty \
    --manifest-path "$repo_root/Cargo.toml" \
    --package erplora-guest-sdk \
    --target-dir "$package_target" >&2

crate_file=""
for candidate in "$package_target"/package/erplora-guest-sdk-*.crate; do
    [ -f "$candidate" ] && crate_file=$candidate
done
if [ -z "$crate_file" ]; then
    echo "package-guest-sdk: cargo package produced no .crate under $package_target/package" >&2
    exit 1
fi

crate_name=$(basename "$crate_file" .crate)
rm -rf "${out_dir:?}/$crate_name"
tar -xzf "$crate_file" -C "$out_dir"
rm -rf "$package_target"

printf '%s\n' "$out_dir/$crate_name"
