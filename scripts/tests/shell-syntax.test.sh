#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Contract test for `scripts/ci/shell-syntax.sh` — the guard that every shell
# script of this repo still PARSES under the oldest bash we support (hub#1468).
#
# Why a guard and not a one-off fix: the two scripts that broke were green in CI
# and red on the machine that runs them. GitHub's runners are Ubuntu with bash 5;
# the fleet and the pre-push gate live on macOS, whose `/bin/bash` is 3.2.57 and
# is what `#!/usr/bin/env bash` resolves to whenever Homebrew's bash is not first
# on PATH. So a syntax bash 3.2 rejects reaches `develop` with every check green
# and only explodes locally, in a message that talks about `;;` instead of about
# the feature under test — `module-hub-batteries` looked broken to any worker.
#
# The construct that did it is the classic bash 3.2 bug: a `case` inside a
# command substitution `$( … )`. 3.2 scans for the closing paren without
# understanding `case`, so the first arm's `)` ends the substitution and the
# parser dies at the following `;;`. The portable fix is the POSIX parenthesised
# pattern — `(*.sh)` instead of `*.sh)` — which 3.2, 4.x and 5.x all accept.
#
# The contract this file pins:
#   · the checker DISCOVERS every shell script (`*.sh` anywhere + anything with a
#     sh/bash shebang, `.githooks/pre-push` included) — a discoverer that quietly
#     stops discovering is the same lie one level up (hub#1327, hub#1359);
#   · it REJECTS a script that does not parse — proven twice: with an ordinary
#     syntax error (portable, works on any bash) and with the hub#1468 construct
#     (needs a bash < 4, which is exactly where the guard has to bite);
#   · it ACCEPTS the parenthesised form;
#   · `--require-legacy` refuses to pass off a bash 5 parse as the 3.2 contract;
#   · THIS repo is clean — the regression test for the two scripts of hub#1468;
#   · the wiring exists: `test-hub.yml` runs this battery and the pre-push gate
#     runs the checker. A battery nobody invokes leaves no red anywhere (hub#1392).
#
# Run:  bash scripts/tests/shell-syntax.test.sh
#
# Dependency-free on purpose (bash + find + grep): it runs as a step of
# `test-hub.yml`, on `ci-runner-1` as well as on GitHub's image. And it obeys its
# own rule — no bare `case` inside a `$( … )` anywhere below, fixtures included.
# ─────────────────────────────────────────────────────────────────────────────
set -uo pipefail

repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
checker="$repo_root/scripts/ci/shell-syntax.sh"
workflow="$repo_root/.github/workflows/test-hub.yml"
hook="$repo_root/.githooks/pre-push"

tmp_dir=$(mktemp -d "${TMPDIR:-/tmp}/erplora-shell-syntax-test.XXXXXX")
trap 'rm -rf "$tmp_dir"' EXIT HUP INT TERM

pass=0
fail=0

ok()  { printf '  \033[32m✓\033[0m %s\n' "$1"; pass=$((pass + 1)); }
bad() { printf '  \033[31m✗\033[0m %s\n     %s\n' "$1" "$2"; fail=$((fail + 1)); }
flat() { printf '%s' "$1" | tr '\n' '|'; }

if [ ! -f "$checker" ]; then
    printf '\033[31m✗\033[0m no such checker: %s\n' "$checker" >&2
    exit 1
fi

# A tree with a single script in it, so every case below is hermetic. Body on
# stdin, and NOT via `$( … )` on purpose: these fixtures contain the very `case`
# a 3.2 parser chokes on, and this file has to parse under 3.2 too.
fixture() { # $1 = dir name, $2 = script basename
    mkdir -p "$tmp_dir/$1"
    cat > "$tmp_dir/$1/$2"
}

# The oldest bash on this machine, asked to the checker itself so the test and
# the guard can never disagree about which interpreter is in play.
header=$("$checker" --root "$repo_root" --list 2>/dev/null | grep '^shell-syntax:')
legacy=$(printf '%s\n' "$header" | sed -n 's/.*legacy=\([a-z]*\).*/\1/p')
interp=$(printf '%s\n' "$header" | sed -n 's/.*interpreter=\([^ ]*\).*/\1/p')
modern=$(command -v bash)

# ── 1. Discovery: every shell script of the repo is in the scanned set ───────
#    Scoping this to `scripts/**/*.sh` would leave the pre-push hook — the only
#    pre-merge proof of the hub — outside the very check it needs most.
listing=$("$checker" --root "$repo_root" --list 2>/dev/null | grep -v '^shell-syntax:')
missing=""
for want in .githooks/pre-push scripts/prepush-gate.test.sh scripts/ci/module-hub-batteries.sh \
            scripts/tests/shell-syntax.test.sh scripts/ci/shell-syntax.sh; do
    printf '%s\n' "$listing" | grep -qx "$want" || missing="$missing $want"
done
[ -z "$missing" ] \
    && ok "discovery: the hook and the scripts are all in the scanned set" \
    || bad "discovery: the hook and the scripts are all in the scanned set" "not listed:$missing"

count=$(printf '%s\n' "$listing" | grep -c . || true)
[ "$count" -ge 30 ] \
    && ok "discovery: the set is the whole repo ($count scripts), not a hand-written list" \
    || bad "discovery: the set is the whole repo, not a hand-written list" "only $count files listed"

# ── 2. Positive control, portable: an ordinary syntax error must be caught ───
#    This one needs no old bash, so it proves on EVERY machine that the checker
#    is not vacuous — a green from a checker that never fails is worth nothing.
fixture broken bad.sh <<'FIXTURE'
#!/usr/bin/env bash
if [ -n "$1" ]; then
    echo unterminated
FIXTURE
out=$("$checker" --root "$tmp_dir/broken" 2>&1)
code=$?
[ "$code" -ne 0 ] && printf '%s' "$out" | grep -q 'bad.sh' \
    && ok "a script with a plain syntax error is rejected, and named" \
    || bad "a script with a plain syntax error is rejected, and named" "exit=$code out=$(flat "$out")"

# ── 3. A clean tree passes — the shape the hub#1468 fix uses ────────────────
fixture clean good.sh <<'FIXTURE'
#!/usr/bin/env bash
x=$(
    case "a" in
        (a) echo one ;;
        (*) echo other ;;
    esac
)
echo "$x"
FIXTURE
out=$("$checker" --root "$tmp_dir/clean" 2>&1)
code=$?
[ "$code" -eq 0 ] \
    && ok "the parenthesised form passes" \
    || bad "the parenthesised form passes" "exit=$code out=$(flat "$out")"

# ── 4. THE positive of hub#1468: `case` inside `$( … )` ─────────────────────
#    Both shapes the repo had: bare, and inside a heredoc fed to a substitution.
#    bash >= 4 parses both happily, so this assertion only means something with
#    a legacy interpreter — which is precisely the machine the guard protects.
fixture regression regressed.sh <<'FIXTURE'
#!/usr/bin/env bash
x=$(
    case "a" in
        a) echo one ;;
        *) echo other ;;
    esac
)
echo "$x"
FIXTURE
fixture heredoc regressed-heredoc.sh <<'FIXTURE'
#!/usr/bin/env bash
gh=$(cat <<'IN'
case "$1 $2" in
    "repo view") exit 1 ;;
esac
IN
)
printf '%s\n' "$gh"
FIXTURE
if [ "$legacy" = yes ]; then
    out=$("$checker" --root "$tmp_dir/regression" 2>&1)
    code=$?
    [ "$code" -ne 0 ] && printf '%s' "$out" | grep -q 'regressed.sh' \
        && ok "reintroducing a bare \`case\` inside \$( … ) turns the guard red ($interp)" \
        || bad "reintroducing a bare \`case\` inside \$( … ) turns the guard red ($interp)" \
               "exit=$code out=$(flat "$out")"

    out=$("$checker" --root "$tmp_dir/heredoc" 2>&1)
    code=$?
    [ "$code" -ne 0 ] \
        && ok "the heredoc shape of the same bug is caught too ($interp)" \
        || bad "the heredoc shape of the same bug is caught too ($interp)" "exit=$code out=$(flat "$out")"
else
    # Not a skip that hides: this machine has no bash < 4, so it CANNOT host this
    # leg. Said out loud, and `--require-legacy` below refuses to call it green.
    printf '  \033[33m—\033[0m bash < 4 absent here (%s): the 3.2 leg runs on the macOS gate\n' "$interp"
fi

# ── 5. `--require-legacy` never passes a modern parse off as the 3.2 contract ─
out=$("$checker" --root "$tmp_dir/clean" --require-legacy --bash "$modern" 2>&1)
code=$?
[ "$code" -ne 0 ] \
    && ok "--require-legacy refuses a bash >= 4 interpreter" \
    || bad "--require-legacy refuses a bash >= 4 interpreter" "exit=$code with $modern"

# ── 6. THE regression test of hub#1468: this repo parses, today ─────────────
out=$("$checker" --root "$repo_root" 2>&1)
code=$?
[ "$code" -eq 0 ] \
    && ok "every shell script of the repo parses under $interp" \
    || bad "every shell script of the repo parses under $interp" "$(flat "$out")"

# ── 7. The wiring, or the battery leaves no red anywhere (hub#1392) ─────────
grep -q 'scripts/tests/shell-syntax.test.sh' "$workflow" \
    && ok "test-hub.yml runs this battery" \
    || bad "test-hub.yml runs this battery" "no mention in $workflow"

grep -q 'shell-syntax.sh' "$hook" \
    && ok "the pre-push gate runs the checker (macOS: the bash 3.2 leg)" \
    || bad "the pre-push gate runs the checker" "no mention in $hook"

printf '\n'
if [ "$fail" -gt 0 ]; then
    printf '\033[31mFAIL\033[0m: %d of %d shell-syntax contract cases\n' "$fail" "$((pass + fail))" >&2
    exit 1
fi
printf '\033[32mPASS\033[0m: %d shell-syntax contract cases\n' "$pass"
