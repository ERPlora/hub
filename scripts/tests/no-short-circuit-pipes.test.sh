#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Contract test for `scripts/ci/no-short-circuit-pipes.sh` — the guard that no
# shell script of this repo feeds a pipe into a reader that SHORT-CIRCUITS
# (hub#1534).
#
# The defect, in one line: `producer | grep -q PATTERN` under `set -o pipefail`
# is a check that lies in the WORST direction. `grep -q` exits at the FIRST match
# and closes the pipe; the producer takes `EPIPE`, dies with 141
# ("printf: write error: Broken pipe"), and `pipefail` hands the pipeline the
# PRODUCER's status — so a MATCH is reported as a failure. `if ! … ; then` takes
# the error branch precisely when the pattern WAS there.
#
# It is a race — whoever finishes first wins — which is why it is not
# deterministic: green on macOS and on an idle runner, red on a loaded Linux one.
# That is the expensive part. On 2026-09-04 it failed the PR of hub#1530 claiming
# the Playwright bench did not pin `HUB_CLOUD_API_URL` and would therefore call
# PRODUCTION from the runner — a line that had been there since July. A watchman
# that shouts when everything is fine teaches everyone to answer "flaky again,
# re-run it", and that is the answer it will get on the day it shouts for real.
#
# hub#1471 already hit it, wrote the warning into `test-web-workflow.test.sh` and
# fixed only the block it was writing that day. Sixty-three occurrences stayed
# alive across the tree, `.githooks/pre-push` included. A rule that lives in a
# comment gets applied to the next line somebody happens to be editing, so
# hub#1534 replaces the comment with a guard.
#
# What this file pins:
#   · the MECHANISM is real — not assumed: the piped form is asked for a pattern
#     that IS present and answers "absent"; the here-string answers "present";
#   · the guard CATCHES the positive — every flag shape used in this repo
#     (`-q`, `-qE`, `-qF`, `-qx`, `-Fxq`, `-q --`, `-m 1`), the long spellings
#     (`--quiet`, `--silent`, `--max-count=N`) and the pipeline split over two
#     lines, each with its own fixture, because a guard whose regex silently
#     stops matching is the same lie one level up (hub#1327, hub#1359);
#   · it does NOT fire on the fix (`grep -q P <<<"$b"`), on prose that merely
#     TALKS about the pattern, on `||` (the OR operator is not a pipe — and the
#     pre-push gate would abort that push), or on the line tagged `sigpipe-demo`;
#   · DISCOVERY is the whole repo, hook included — not a hand-written list;
#   · THIS repo is clean — the regression test for the sixty-three of hub#1534;
#   · the WIRING exists: a workflow runs this battery and the pre-push gate runs
#     the scanner. A battery nobody invokes leaves no red anywhere (hub#1392).
#
# Run:  bash scripts/tests/no-short-circuit-pipes.test.sh
#
# Dependency-free on purpose (bash + grep + awk): it runs as a workflow step on
# `ci-runner-1` as well as on GitHub's image. And it obeys its own rule — every
# check below reads with a here-string, never with a pipe.
# ─────────────────────────────────────────────────────────────────────────────
set -uo pipefail

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repo_root=$(CDPATH= cd -- "$script_dir/../.." && pwd)
scanner="$repo_root/scripts/ci/no-short-circuit-pipes.sh"
workflow="$repo_root/.github/workflows/actionlint.yml"
hook="$repo_root/.githooks/pre-push"

tmp_dir=$(mktemp -d "${TMPDIR:-/tmp}/erplora-short-circuit-test.XXXXXX")
trap 'rm -rf "$tmp_dir"' EXIT HUP INT TERM

pass=0
fail=0
ok()  { printf '  \033[32m✓\033[0m %s\n' "$1"; pass=$((pass + 1)); }
bad() { printf '  \033[31m✗\033[0m %s\n     %s\n' "$1" "$2"; fail=$((fail + 1)); }
flat() { tr '\n' '|' <<<"$1"; }

# ── 1. The mechanism, proven — not assumed ──────────────────────────────────
# The match must be on the FIRST line and the filler AFTER it: `grep` works
# line-wise, so a single huge line with the pattern at the start would force it
# to read the whole thing and there would be no early exit to race with. 200 KB
# is comfortably past the 64 KB pipe buffer, so the producer cannot finish in one
# write and the race is decided the same way on every platform.
sigpipe_block="NEEDLE_PRESENT
$(head -c 200000 /dev/zero | tr '\0' 'x')"
piped_verdict=present;      ! printf '%s' "$sigpipe_block" | grep -q 'NEEDLE_PRESENT' && piped_verdict=absent # sigpipe-demo
herestring_verdict=present; ! grep -q 'NEEDLE_PRESENT' <<<"$sigpipe_block" && herestring_verdict=absent

if [ "$piped_verdict" != absent ]; then
    # NOT a pass: this platform did not reproduce the race, so everything below
    # is unproven here and only Linux would catch a reintroduction.
    bad "el patrón \`printf … | grep -q\` se rompe con un bloque mayor que el buffer del pipe" \
        "esta plataforma NO reprodujo el SIGPIPE (el productor ganó la carrera): el guard queda sin demostrar aquí — reprodúcelo en Linux antes de fiarte de su verde"
elif [ "$herestring_verdict" != present ]; then
    bad "el here-string sobrevive donde la tubería muere" \
        "\`grep -q … <<<\"\$bloque\"\` también dijo «ausente» sobre un bloque que SÍ contiene el patrón: el arreglo de hub#1534 no vale en esta plataforma"
else
    ok "el patrón \`printf … | grep -q\` miente bajo pipefail y el here-string no (hub#1534)"
fi

if [ ! -x "$scanner" ]; then
    printf '\033[31m✗\033[0m no such scanner (or not executable): %s\n' "$scanner" >&2
    printf '\n%d passed, %d failed\n' "$pass" "$((fail + 1))"
    exit 1
fi

# ── 2. Fixtures ─────────────────────────────────────────────────────────────
# The offending lines are BUILT, never written literally, so this file stays
# clean under its own guard without needing an opt-out on every fixture.
GREP=grep
fixture() { # $1 = dir, $2 = basename; body on stdin
    mkdir -p "$tmp_dir/$1"
    cat > "$tmp_dir/$1/$2"
}
dirty() { # $1 = the grep flags → one offending line
    printf "printf '%%s' \"\$block\" | %s %s 'NEEDLE'\n" "$GREP" "$1"
}

# ── 3. Positive control: every flag shape this repo uses is caught ──────────
# One fixture per shape. A single `-q` case would pass while `-Fxq` (used in
# `module-hub-batteries.test.sh`) or `-q --` (used in `clippy-lints.test.sh`)
# walked straight through the regex. The long spellings (`--quiet`, `--silent`,
# `--max-count=N`) are the same short-circuit under another name: a guard that
# only knows `-q` is bypassed by whoever writes it out in full.
i=0
for flags in "-q" "-qE" "-qF" "-qx" "-qi" "-qxF" "-Fxq" "-qvE" "-q --" "-m 1" "-m1" \
             "--quiet" "--silent" "--max-count=1" "--max-count 1"; do
    i=$((i + 1))
    fixture "pos$i" dirty.sh <<FIXTURE
#!/usr/bin/env bash
set -uo pipefail
block=NEEDLE
$(dirty "$flags")
FIXTURE
    out=$("$scanner" --root "$tmp_dir/pos$i" 2>&1)
    code=$?
    if [ "$code" -eq 0 ]; then
        bad "el guard caza \`grep $flags\` detrás de una tubería" \
            "salió 0 sobre un fichero que SÍ tiene el patrón — el regex no cubre esta forma y una reintroducción con \`$flags\` pasaría entera"
    elif ! grep -q 'dirty.sh' <<<"$out"; then
        bad "el guard nombra el fichero al cazar \`grep $flags\`" \
            "salida sin \`dirty.sh\`: out=$(flat "$out")"
    elif ! grep -qE 'dirty\.sh:4' <<<"$out"; then
        bad "el guard nombra la LÍNEA al cazar \`grep $flags\`" \
            "se esperaba \`dirty.sh:4\` (la línea ofensora): out=$(flat "$out")"
    else
        ok "caza \`grep $flags\` detrás de una tubería, con fichero y línea"
    fi
done

# bash allows the newline right after `|` — blank lines and comments included — so a
# pipeline split over two lines is the same pipe. The offending line to name is the
# READER's, which is where the fix goes.
fixture pos-eol dirty.sh <<FIXTURE
#!/usr/bin/env bash
set -uo pipefail
block=NEEDLE
printf '%s' "\$block" |

    # the reader, two lines below the pipe
    $GREP -q 'NEEDLE'
FIXTURE
out=$("$scanner" --root "$tmp_dir/pos-eol" 2>&1)
code=$?
if [ "$code" -eq 0 ]; then
    bad "el guard caza la tubería partida en dos líneas (\`|\` al final, \`grep -q\` en la siguiente)" \
        "salió 0: bash acepta el salto de línea tras \`|\` y el scanner mira línea a línea"
elif ! grep -qE 'dirty\.sh:7' <<<"$out"; then
    bad "el guard nombra la línea del LECTOR en la tubería partida" \
        "se esperaba \`dirty.sh:7\`: out=$(flat "$out")"
else
    ok "caza la tubería partida en dos líneas y nombra la línea del lector"
fi

# A `||` earlier on the line is not a pipe and must not hide the real one after it.
fixture pos-after-or dirty.sh <<FIXTURE
#!/usr/bin/env bash
set -uo pipefail
block=NEEDLE
[ -z "\$block" ] || $GREP -q 'NEEDLE' <<<"\$block"; $(dirty "-q")
FIXTURE
out=$("$scanner" --root "$tmp_dir/pos-after-or" 2>&1)
code=$?
if [ "$code" -eq 0 ] || ! grep -qE 'dirty\.sh:4' <<<"$out"; then
    bad "el guard sigue mirando la línea después de un \`||\` legítimo" \
        "un \`|| grep -q … <<<\` antes en la misma línea tapó la tubería real: exit=$code out=$(flat "$out")"
else
    ok "un \`||\` antes en la línea no tapa la tubería real que viene después"
fi

# ── 4. Negative control: the FIX, prose about the pattern, and the opt-out ──
# A guard that also fires on the fix is a guard nobody can satisfy; one that
# fires on a comment explaining the trap punishes writing the explanation down.
fixture neg clean.sh <<FIXTURE
#!/usr/bin/env bash
set -uo pipefail
block=NEEDLE
$GREP -q 'NEEDLE' <<<"\$block"
# Never \`printf '%s' "\$block" | $GREP -q NEEDLE\`: the pipeline lies under pipefail.
echo "el patrón \\\`printf … | $GREP -q\\\` miente bajo pipefail"
[ -n "\$block" ] || $GREP -q 'NEEDLE' <<<"\$block"
[ -n "\$block" ] ||
    $GREP -q 'NEEDLE' <<<"\$block"
$(dirty "-q") # sigpipe-demo
FIXTURE
out=$("$scanner" --root "$tmp_dir/neg" 2>&1)
code=$?
if [ "$code" -ne 0 ]; then
    bad "el guard NO fira sobre el arreglo, la prosa, un \`||\` ni la línea marcada \`sigpipe-demo\`" \
        "exit=$code out=$(flat "$out")"
else
    ok "no fira sobre el here-string, la prosa entre backticks, un \`||\` (entero o partido) ni \`sigpipe-demo\`"
fi

# ── 5. Discovery is the whole repo, hook included ───────────────────────────
# Scoping this to `scripts/**` would leave `.githooks/pre-push` — the only
# pre-merge proof of the hub, and where four of the sixty-three lived — outside
# the very check it needs most.
listing=$("$scanner" --root "$repo_root" --list 2>/dev/null)
missing=""
for want in .githooks/pre-push scripts/ci/no-short-circuit-pipes.sh \
            scripts/tests/no-short-circuit-pipes.test.sh scripts/prepush-gate.test.sh; do
    grep -qxF "$want" <<<"$listing" || missing="$missing $want"
done
[ -z "$missing" ] \
    && ok "discovery: el hook y los scripts están en el conjunto barrido" \
    || bad "discovery: el hook y los scripts están en el conjunto barrido" "no listados:$missing"

listed=$(grep -c . <<<"$listing" || true)
[ "$listed" -ge 30 ] \
    && ok "discovery: el conjunto es el repo entero ($listed scripts), no una lista a mano" \
    || bad "discovery: el conjunto es el repo entero, no una lista a mano" "solo $listed ficheros"

# ── 6. THIS repo is clean — the regression test of hub#1534 ─────────────────
out=$("$scanner" --root "$repo_root" 2>&1)
code=$?
[ "$code" -eq 0 ] \
    && ok "ningún script del repo canaliza hacia un lector que corta (hub#1534)" \
    || bad "ningún script del repo canaliza hacia un lector que corta (hub#1534)" \
           "exit=$code — usa \`grep -q PATRÓN <<<\"\$bloque\"\`: $(flat "$out")"

# ── 7. Wiring: something actually RUNS both halves ──────────────────────────
# `scripts-tests-wiring.test.sh` already refuses a contract test no workflow
# executes; this pins the OTHER half — the scanner itself in the pre-push gate,
# which is what turns the guard red before the push instead of 40 min later.
if [ -f "$workflow" ] && grep -qF 'no-short-circuit-pipes.test.sh' "$workflow"; then
    ok "un workflow ejecuta esta batería (actionlint.yml)"
else
    bad "un workflow ejecuta esta batería" \
        "\`no-short-circuit-pipes.test.sh\` no aparece en $workflow: un test que nadie invoca no deja rojo en ninguna parte (hub#1392)"
fi

hook_code=$(grep -v '^[[:space:]]*#' "$hook" 2>/dev/null || true)
if grep -qF 'no-short-circuit-pipes.sh' <<<"$hook_code"; then
    ok "el gate pre-push ejecuta el scanner"
else
    bad "el gate pre-push ejecuta el scanner" \
        "\`.githooks/pre-push\` no lo invoca fuera de un comentario: el rojo llegaría 40 min más tarde, en Actions"
fi

printf '\n%d passed, %d failed\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
