#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Contract test for the shell's formatting guard (hub#2156).
#
# Why: `apps/web` had no formatter config at all, so whoever ran prettier got its
# defaults (double quotes) and six new files of hub#2146 landed with a style the
# other ~490 files of the shell do not use. Nothing in the repo noticed; the only
# guard was the reviewer's eye.
#
# The guard is a BASELINE, not a sweep: measured on 2026-09-26, 331 of the 543
# `.ts`/`.vue` files under `apps/web/src` differ from ANY prettier config (the
# shell was never formatted by a tool). Reformatting them all would be a
# 331-file diff colliding with every open PR, so they are listed in
# `apps/web/.prettierignore` and everything else — every NEW file included — is
# checked. The list only shrinks: format a legacy file, drop its line.
#
# What this pins:
#   · the config exists and says single quotes (the shell's convention);
#   · `format:check` is wired into `pnpm verify` (which `test-web.yml` runs);
#   · the tree passes the check today;
#   · POSITIVE CONTROL: a new double-quoted file makes the check fail — a guard
#     that cannot go red is not a guard;
#   · the seven double-quoted files of the issue are checked, not ignored.
#
# Run:  bash scripts/tests/web-format.test.sh   (needs `pnpm install` done)
# ─────────────────────────────────────────────────────────────────────────────
set -uo pipefail

repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
web="$repo_root/apps/web"
config="$web/.prettierrc.json"
ignore="$web/.prettierignore"
probe="$web/src/__format_probe_hub2156__.ts"

pass=0
fail=0

ok()  { printf '  \033[32m✓\033[0m %s\n' "$1"; pass=$((pass + 1)); }
bad() { printf '  \033[31m✗\033[0m %s\n     %s\n' "$1" "$2"; fail=$((fail + 1)); }

cleanup() { rm -f "$probe"; }
trap cleanup EXIT

format_check() { (cd "$web" && pnpm run --silent format:check >/dev/null 2>&1); }

echo "web-format (hub#2156)"

# 1. Config in the repo, single quotes.
if [ -f "$config" ] && python3 -c 'import json,sys; sys.exit(0 if json.load(open(sys.argv[1])).get("singleQuote") is True else 1)' "$config"; then
    ok "apps/web/.prettierrc.json exists with singleQuote: true"
else
    bad "apps/web/.prettierrc.json with singleQuote: true" "missing, unreadable or singleQuote is not true"
fi

# 2. `format:check` exists and is part of the web `verify` script.
scripts=$(python3 -c 'import json,sys; s=json.load(open(sys.argv[1])).get("scripts",{}); print(s.get("format:check","")); print(s.get("verify",""))' "$web/package.json")
check_script=$(printf '%s\n' "$scripts" | sed -n 1p)
verify_script=$(printf '%s\n' "$scripts" | sed -n 2p)
case "$check_script" in
    *"prettier --check"*) ok "format:check runs prettier --check" ;;
    *) bad "format:check runs prettier --check" "got: '${check_script}'" ;;
esac
case "$verify_script" in
    *"format:check"*) ok "pnpm verify runs format:check" ;;
    *) bad "pnpm verify runs format:check" "got: '${verify_script}'" ;;
esac

# 3. The seven files of the issue are checked (not hidden in the baseline).
for f in \
    src/components/BootUnreachable.vue \
    src/components/BootUnreachable.test.ts \
    src/lib/boot-screen.ts \
    src/lib/boot-screen.hub2143.test.ts \
    src/lib/boot-unreachable.hub2143.test.ts \
    src/main-waits-for-the-hub.hub2143.test.ts \
    src/lib/icons.ts; do
    if [ -f "$ignore" ] && grep -qxF "$f" "$ignore"; then
        bad "$f is checked" "it is listed in .prettierignore"
    else
        ok "$f is checked"
    fi
done

# 4. The tree passes today.
if format_check; then
    ok "format:check passes on the tree"
else
    bad "format:check passes on the tree" "run: pnpm -F @erplora/web format:check"
fi

# 5. Positive control: a new double-quoted file must turn the check red, and
#    red BECAUSE of that file (prettier names it) — a missing script or a crash
#    also exits non-zero and would pass this assertion vacuously.
printf 'import { ref } from "vue";\n\nexport const probe = ref(0);\n' >"$probe"
probe_out=$(cd "$web" && pnpm run --silent format:check 2>&1)
probe_rc=$?
if [ "$probe_rc" -ne 0 ] && printf '%s\n' "$probe_out" | grep -qF "$(basename "$probe")"; then
    ok "a new double-quoted file fails format:check"
else
    bad "a new double-quoted file fails format:check" "exit ${probe_rc}; output did not name $(basename "$probe")"
fi
cleanup

printf '\n%d passed, %d failed\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
