#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Tests for the Windows packaging contract of the app:
#   .github/workflows/tauri-release.yml  ←→  scripts/pack-msix.ps1  ←→  the repo
#
# Run:  scripts/pack-msix.test.sh
#
# Why a shell test for a PowerShell script: the MSIX leg only ever runs on a
# Windows runner, behind the `vars.MSIX_IDENTITY_NAME` gate, which is still
# empty. That gate is why hub#577 went unnoticed for months — the packer wrote
# `erplora-bridge.msix` while the workflow uploaded `erplora-app.msix` with
# `if-no-files-found: error`, so the step could never have worked. Nothing
# executed it, so nothing said so.
#
# These tests do NOT run `winapp pack`. They check the things that made that
# bug possible and that are perfectly checkable off Windows: that the names,
# paths and tokens the workflow, the packer and the manifest exchange all agree
# with each other and with the files actually in the repo.
# ─────────────────────────────────────────────────────────────────────────────
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PS1="$ROOT/scripts/pack-msix.ps1"
WORKFLOW="$ROOT/.github/workflows/tauri-release.yml"
TAURI_CONF="$ROOT/apps/tauri/src-tauri/tauri.conf.json"
CARGO_TOML="$ROOT/apps/tauri/src-tauri/Cargo.toml"

pass=0
fail=0
ok()  { printf '  \033[32m✓\033[0m %s\n' "$1"; pass=$((pass + 1)); }
bad() { printf '  \033[31m✗\033[0m %s\n     %s\n' "$1" "$2"; fail=$((fail + 1)); }

# ── Readers ──────────────────────────────────────────────────────────────────

# A scalar field of the $p preset hashtable, e.g. `OutName = "erplora-app.msix"`.
ps_field() {
    sed -n "s/^[[:space:]]*$1[[:space:]]*=[[:space:]]*\"\([^\"]*\)\".*/\1/p" "$PS1" | head -1
}

# The quoted entries of `ExeCandidates = @( ... )`, repo-relative.
exe_candidates() {
    sed -n '/ExeCandidates[[:space:]]*=[[:space:]]*@(/,/^[[:space:]]*)/p' "$PS1" \
        | grep -o '"[^"]*"' | tr -d '"' | sed 's|\$repoRoot/||'
}

# The asset file names the packer copies into the staged Assets/ directory.
staged_assets() {
    sed -n 's/^foreach (\$i in \(.*\)) {.*/\1/p' "$PS1" | grep -o '"[^"]*"' | tr -d '"'
}

# The __MSIX_*__ tokens the packer substitutes in the manifest.
replaced_tokens() {
    grep -o 'Replace("__MSIX_[A-Z_]*__"' "$PS1" | sed 's/Replace("//;s/"//' | sort -u
}

# The __MSIX_*__ tokens the manifest actually declares.
manifest_tokens() {
    grep -o '__MSIX_[A-Z_]*__' "$1" | sort -u
}

# `path:` of the workflow step that uploads the MSIX artifact.
msix_upload_path() {
    grep -A3 'name: app-msix' "$WORKFLOW" \
        | sed -n 's/^[[:space:]]*path:[[:space:]]*//p' | head -1
}

json_field() { python3 -c "import json,sys;print(json.load(open(sys.argv[1])).get(sys.argv[2],''))" "$1" "$2"; }

manifest_path="$ROOT/$(ps_field Manifest | sed 's|\$repoRoot/||')"
assets_dir="$ROOT/$(ps_field AssetsDir | sed 's|\$repoRoot/||')"
exe_name="$(ps_field ExeName)"
out_name="$(ps_field OutName)"

echo "MSIX packaging contract"

# ── 1. hub#577: the packer writes exactly the file the workflow uploads ───────
# The original defect in one line. `if-no-files-found: error` means any drift
# here fails the release on the first tag, not quietly.
upload_path="$(msix_upload_path)"
[ -n "$out_name" ] && [ "$upload_path" = "dist-msix/$out_name" ] \
    && ok "the workflow uploads the file the packer writes ($out_name)" \
    || bad "the workflow uploads the file the packer writes" \
           "packer OutName='$out_name' but the workflow uploads '$upload_path'"

# ── 2. hub#577: a single flavour, and the workflow calls it without one ───────
# The packer used to be `-Flavor bridge`-defaulted, so calling it with no
# flavour silently packaged the Bridge. With the Bridge retired there is one
# artefact to build; a reintroduced flavour parameter must not be defaulted.
# Matched on the variable, not the word: the tombstone comment that records the
# defect names `-Flavor` on purpose and is worth keeping.
! grep -q '\$Flavor' "$PS1" \
    && ok "the packer has no \$Flavor parameter to fall through (Bridge is gone)" \
    || bad "the packer has no \$Flavor parameter to fall through" \
           "\$Flavor is back in pack-msix.ps1 — a defaulted flavour is what hub#577 was"

# ── 3. hub#577 §1: the exe is found whatever Tauri decides to call it ─────────
# `productName` is "ERPlora" but the cargo bin is `erplora-tauri`; Tauri renames
# the binary after building. That rename has never been observed on a Windows
# runner here, so the packer must locate BOTH names — it stages the file as
# `ExeName` either way, so being right does not depend on knowing the answer.
product_name="$(json_field "$TAURI_CONF" productName)"
cargo_bin="$(sed -n 's/^name = "\(.*\)"/\1/p' "$CARGO_TOML" | head -1)"
candidates="$(exe_candidates)"
missing=""
for want in "$product_name.exe" "$cargo_bin.exe"; do
    grep -qF "/$want" <<<"$candidates" || missing="$missing $want"
done
[ -z "$missing" ] \
    && ok "the exe candidates cover both the productName and the cargo bin name" \
    || bad "the exe candidates cover both the productName and the cargo bin name" \
           "never looked for:$missing — candidates are:$(echo " $candidates" | tr '\n' ' ')"

# ── 4. Both target dirs: `tauri build` may run from the workspace root or from
#      apps/tauri/src-tauri, and they do not share a target/ directory. ───────
for dir in "target/release" "apps/tauri/src-tauri/target/release"; do
    grep -q "^$dir/" <<<"$candidates" \
        && ok "the exe is looked for in $dir/" \
        || bad "the exe is looked for in $dir/" "no candidate under $dir/"
done

# ── 5. The manifest launches the file the packer actually stages ─────────────
# The exe is staged under `ExeName`, and MSIX refuses to install if
# Application/@Executable names a file that is not in the package.
declared_exe="$(grep -o 'Executable="[^"]*"' "$manifest_path" | head -1 | sed 's/Executable="//;s/"//')"
[ -n "$exe_name" ] && [ "$declared_exe" = "$exe_name" ] \
    && ok "the manifest launches the staged exe ($exe_name)" \
    || bad "the manifest launches the staged exe" \
           "manifest Executable='$declared_exe' but the packer stages '$exe_name'"

# ── 6. Every asset the packer copies exists, at the path it copies it from ───
for a in $(staged_assets); do
    [ -f "$assets_dir/$a" ] \
        && ok "asset present: $a" \
        || bad "asset present: $a" "not found at $assets_dir/$a"
done

# ── 7. Tokens: the packer and the manifest agree, in both directions ─────────
# A token in the manifest that the packer does not replace ships a literal
# `__MSIX_…__` into the Store submission; the reverse is a silent no-op.
diff_out="$(diff <(replaced_tokens) <(manifest_tokens "$manifest_path") 2>&1)"
[ -z "$diff_out" ] \
    && ok "the packer replaces exactly the tokens the manifest declares" \
    || bad "the packer replaces exactly the tokens the manifest declares" \
           "$(echo "$diff_out" | tr '\n' ' ')"

# ── 8. hub#465: no JS toolchain while there is no frontend to build ──────────
# `tauri-action` only builds a frontend when tauri.conf.json has a
# `beforeBuildCommand`. Since ADR-0154 it has none — `frontendDist` points at
# the committed static `shell-dist/` — so setting up pnpm/Node and resolving the
# lockfile in every build job buys nothing, in the most expensive workflow we
# have. The two halves are asserted together on purpose: if a
# `beforeBuildCommand` ever comes back, this test demands the setup come back
# with it instead of leaving a build that fails on the first tag.
has_before_build="$(python3 -c "import json;print('yes' if 'beforeBuildCommand' in json.load(open('$TAURI_CONF')).get('build',{}) else 'no')")"
js_steps="$(grep -n 'pnpm/action-setup\|actions/setup-node\|pnpm install --frozen-lockfile' "$WORKFLOW" || true)"

if [ "$has_before_build" = no ]; then
    [ -z "$js_steps" ] \
        && ok "no beforeBuildCommand ⇒ the release workflow sets up no JS toolchain" \
        || bad "no beforeBuildCommand ⇒ the release workflow sets up no JS toolchain" \
               "nothing builds a frontend, yet these steps remain: $(echo "$js_steps" | tr '\n' ' ')"
else
    [ -n "$js_steps" ] \
        && ok "beforeBuildCommand present ⇒ the release workflow sets up the JS toolchain" \
        || bad "beforeBuildCommand present ⇒ the release workflow sets up the JS toolchain" \
               "tauri.conf.json builds a frontend but no pnpm/Node setup remains in the workflow"
fi

# ── 9. hub#465: the Tauri CLI does not come from the JS toolchain either ─────
# Removing pnpm/Node is only safe because nothing resolves the CLI through
# npm: the matrix job gets it from `tauri-action`, and build-android from
# `cargo install tauri-cli`.
! grep -q '@tauri-apps/cli' "$ROOT/package.json" && [ ! -f "$ROOT/apps/tauri/package.json" ] \
    && ok "the Tauri CLI is not a JS dependency (no apps/tauri/package.json, no root dep)" \
    || bad "the Tauri CLI is not a JS dependency" \
           "a package.json now provides @tauri-apps/cli — the JS setup steps would be needed again"

echo
printf 'passed %d, failed %d\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
