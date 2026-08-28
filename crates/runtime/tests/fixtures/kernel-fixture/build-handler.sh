#!/usr/bin/env bash
# Rebuilds the kernel-fixture Tier 2 guest and refreshes its build stamp (ERPlora/hub#1238).
#
# The `.wasm` is COMMITTED on purpose: `contracts/kernel/guest.snapshot` freezes the Input/Output
# field names, a published `.wasm` is never recompiled, and the only proof the host still speaks
# that shape is a binary that was compiled against it. `kernel_conformance_guest_wasm.rs` refuses a
# binary whose stamp does not match the committed `handler/` sources, so run this after any edit
# there and commit both files.
#
#   crates/runtime/tests/fixtures/kernel-fixture/build-handler.sh
#
# Requires: `rustup target add wasm32-unknown-unknown`.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
target_dir="${CARGO_TARGET_DIR:-${here}/handler/target}"

rustup target list --installed | grep -qx wasm32-unknown-unknown || {
  echo "missing target: rustup target add wasm32-unknown-unknown" >&2
  exit 1
}

CARGO_TARGET_DIR="${target_dir}" cargo build \
  --release --target wasm32-unknown-unknown --features guest \
  --manifest-path "${here}/handler/Cargo.toml"

cp "${target_dir}/wasm32-unknown-unknown/release/kernel_fixture_handler.wasm" \
   "${here}/1.1.0/handler.wasm"
# Cargo writes it, the stamp deliberately ignores it (module-toolkit#31), and it is not committed.
rm -f "${here}/handler/Cargo.lock"

python3 - "${here}" <<'PY'
import hashlib, json, os, sys

fixture = sys.argv[1]
handler = os.path.join(fixture, "handler")
IGNORED_DIRS = {"target", "node_modules", "dist"}

sources = []
for root, dirs, names in os.walk(handler):
    dirs[:] = [d for d in dirs if not d.startswith(".") and d not in IGNORED_DIRS]
    sources += [
        os.path.join(root, n)
        for n in names
        if not n.startswith(".") and n != "Cargo.lock"
    ]

# Same recipe as the toolkit's `hashHandlerSources`: relative path + NUL + bytes + NUL, sorted.
digest = hashlib.sha256()
for path in sorted(sources):
    digest.update(os.path.relpath(path, handler).encode())
    digest.update(b"\0")
    digest.update(open(path, "rb").read())
    digest.update(b"\0")

wasm = open(os.path.join(fixture, "1.1.0", "handler.wasm"), "rb").read()
stamp = {
    "file": "handler.wasm",
    "target": "wasm32-unknown-unknown",
    "features": ["guest"],
    "sources_sha256": digest.hexdigest(),
    "wasm_sha256": hashlib.sha256(wasm).hexdigest(),
    "bytes": len(wasm),
}
with open(os.path.join(fixture, "1.1.0", "handler.build.json"), "w") as out:
    out.write(json.dumps(stamp, indent=2) + "\n")
print(json.dumps(stamp, indent=2))
PY
