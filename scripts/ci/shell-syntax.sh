#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Parse EVERY shell script of the repo with the OLDEST bash on this machine.
#
# 🔴 The bash floor of this repo is **3.2** — the one macOS ships (3.2.57, frozen
# in 2007 because bash went GPLv3). That is not nostalgia: `#!/usr/bin/env bash`
# resolves to `/bin/bash` on any macOS box where Homebrew's bash is not first on
# PATH — a fresh machine, a GUI git client, launchd, a subprocess with a sanitised
# PATH — and macOS is where the fleet and the pre-push gate run. The alternative,
# pinning `#!/opt/homebrew/bin/bash`, breaks on Linux CI and on Intel Macs
# (`/usr/local`), and a re-exec preamble in every script is more code than the
# rule. It costs nothing: measured on hub#1468, the repo used zero bash-4+
# features (no `declare -A`, no `mapfile`, no `${x^^}`, no `;;&`).
#
# What it catches, and why nothing else did (hub#1468): GitHub's runners are
# Ubuntu with bash 5, so a syntax only 3.2 rejects is GREEN in CI and RED on the
# machine that runs the script. Two scripts had shipped that way — the classic
# 3.2 bug of a `case` inside a command substitution `$( … )`: 3.2 hunts for the
# closing paren without understanding `case`, so the first arm's `)` ends the
# substitution and the parser dies at the following `;;`. The portable fix is the
# POSIX parenthesised pattern, `(*.sh)` instead of `*.sh)`.
#
# `bash -n` is a PARSE check, not an execution: it cannot see a bash-4-only
# builtin that parses fine and fails at runtime (`declare -A`). It is the cheap
# 99 % — the 1 % is why the floor is written down above instead of only enforced.
#
# Usage:
#   scripts/ci/shell-syntax.sh [--root DIR] [--bash PATH] [--require-legacy] [--list]
#
#   --root DIR         tree to scan (default: this repo)
#   --bash PATH        force the interpreter instead of picking the oldest
#   --require-legacy   fail unless the interpreter is bash < 4, so a machine that
#                      lost its 3.2 cannot quietly downgrade the gate to a bash 5
#                      parse and still call it green
#   --list             print the discovered scripts and exit
#
# Exit: 0 clean · 1 a script does not parse · 2 usage or environment problem.
#
# Contract: scripts/tests/shell-syntax.test.sh
# ─────────────────────────────────────────────────────────────────────────────
set -uo pipefail

self_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
root=$(CDPATH= cd -- "$self_dir/../.." && pwd)
forced_bash=""
require_legacy=0
list_only=0

die() { printf 'shell-syntax: %s\n' "$1" >&2; exit 2; }

while [ $# -gt 0 ]; do
    case "$1" in
        (--root)
            [ $# -ge 2 ] || die "--root needs a directory"
            root=$2; shift 2 ;;
        (--bash)
            [ $# -ge 2 ] || die "--bash needs a path"
            forced_bash=$2; shift 2 ;;
        (--require-legacy) require_legacy=1; shift ;;
        (--list)           list_only=1; shift ;;
        (-h | --help)
            sed -n '2,40p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        (*) die "unknown argument: $1" ;;
    esac
done

[ -d "$root" ] || die "no such directory: $root"
root=$(CDPATH= cd -- "$root" && pwd)

# ── The interpreter: the OLDEST bash we can find ────────────────────────────
# Not `bash` from PATH: on the fleet's macOS boxes that is Homebrew's 5.x, which
# is precisely the interpreter that cannot see this class of bug.
bash_version_of() { # $1 = candidate → "<major> <minor>" on stdout, empty if unusable
    "$1" -c 'printf "%s %s\n" "${BASH_VERSINFO[0]}" "${BASH_VERSINFO[1]}"' 2>/dev/null
}

interpreter=""
interpreter_rank=""
interpreter_version=""
if [ -n "$forced_bash" ]; then
    [ -x "$forced_bash" ] || die "not an executable: $forced_bash"
    v=$(bash_version_of "$forced_bash")
    [ -n "$v" ] || die "not a bash: $forced_bash"
    interpreter=$forced_bash
    interpreter_rank=$(( ${v%% *} * 1000 + ${v##* } ))
    interpreter_version=${v%% *}.${v##* }
else
    for candidate in /bin/bash "$(command -v bash 2>/dev/null || true)" \
                     /usr/bin/bash /usr/local/bin/bash /opt/homebrew/bin/bash; do
        [ -n "$candidate" ] && [ -x "$candidate" ] || continue
        v=$(bash_version_of "$candidate")
        [ -n "$v" ] || continue
        rank=$(( ${v%% *} * 1000 + ${v##* } ))
        if [ -z "$interpreter" ] || [ "$rank" -lt "$interpreter_rank" ]; then
            interpreter=$candidate
            interpreter_rank=$rank
            interpreter_version=${v%% *}.${v##* }
        fi
    done
fi
[ -n "$interpreter" ] || die "no usable bash found"

legacy=no
[ "$interpreter_rank" -lt 4000 ] && legacy=yes

# ── Discovery: a file is a shell script by extension OR by shebang ──────────
# By shebang too, or `.githooks/pre-push` — the only pre-merge proof of the hub —
# would sit outside the very check it needs most, and so would every hook added
# later. What is pruned is what nobody here wrote: vendored deps, build output,
# caches. A discoverer that quietly stops discovering is the same lie one level
# up (hub#1327, hub#1359), so the contract test pins the size of this set.
shebang_command() { # $1 = file → the interpreter word of its shebang, if any
    sed -n '1s/^#![[:space:]]*//p' "$1" 2>/dev/null |
        awk 'NR == 1 {
            cmd = $1
            n = split(cmd, parts, "/")
            cmd = parts[n]
            if (cmd == "env" && NF > 1) cmd = $2
            print cmd
        }'
}

scripts=""
while IFS= read -r file; do
    rel=${file#"$root"/}
    keep=no
    if [ "${rel%.sh}" != "$rel" ]; then
        keep=yes
    else
        cmd=$(shebang_command "$file")
        if [ "$cmd" = bash ] || [ "$cmd" = sh ]; then keep=yes; fi
    fi
    [ "$keep" = yes ] || continue
    scripts="$scripts$rel
"
done <<EOF
$(find "$root" \
    \( -type d \( -name .git -o -name node_modules -o -name target -o -name dist \
                  -o -name venv -o -name __pycache__ -o -name .venv \) \) -prune -o \
    -type f -print 2>/dev/null | LC_ALL=C sort)
EOF

count=$(printf '%s' "$scripts" | grep -c . || true)

printf 'shell-syntax: interpreter=%s version=%s legacy=%s files=%s\n' \
    "$interpreter" "$interpreter_version" "$legacy" "$count"

if [ "$list_only" -eq 1 ]; then
    printf '%s' "$scripts"
    exit 0
fi

[ "$count" -gt 0 ] || die "no shell script found under $root — discovery is broken, not the tree"

if [ "$require_legacy" -eq 1 ] && [ "$legacy" != yes ]; then
    die "--require-legacy: $interpreter is $interpreter_version, and only bash < 4 can prove the 3.2 floor"
fi

# ── The check ───────────────────────────────────────────────────────────────
failed=0
while IFS= read -r rel; do
    [ -n "$rel" ] || continue
    out=$("$interpreter" -n "$root/$rel" 2>&1) && continue
    failed=$((failed + 1))
    printf '  \033[31m✗\033[0m %s\n' "$rel" >&2
    printf '%s\n' "$out" | sed 's/^/      /' >&2
done <<EOF
$scripts
EOF

if [ "$failed" -gt 0 ]; then
    printf '\033[31mFAIL\033[0m: %d of %d scripts do not parse with %s (bash %s)\n' \
        "$failed" "$count" "$interpreter" "$interpreter_version" >&2
    printf '       the usual cause is a bare \`case\` inside a command substitution: use (pattern) arms.\n' >&2
    exit 1
fi
printf '\033[32mOK\033[0m: %d scripts parse with %s (bash %s)\n' "$count" "$interpreter" "$interpreter_version"
