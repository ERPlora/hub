#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Tests for .githooks/pre-push — the LOCAL test gate that replaces the
# "Hub tests (Rust · Postgres)" workflow on pull requests.
#
# Run:  scripts/prepush-gate.test.sh
#
# The hook is driven through injection points so these tests never compile Rust,
# never touch Docker and never call GitHub:
#   HUB_GATE_TEST_CMD    the suite to run       (default: cargo test --workspace …)
#   HUB_GATE_STATUS_CMD  how to publish the commit status  (default: gh api …)
#   HUB_GATE_STATE_DIR   where the green marks and the lock live
# ─────────────────────────────────────────────────────────────────────────────
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOOK="$ROOT/.githooks/pre-push"
ZERO=0000000000000000000000000000000000000000
pass=0
fail=0

ok()   { printf '  \033[32m✓\033[0m %s\n' "$1"; pass=$((pass + 1)); }
bad()  { printf '  \033[31m✗\033[0m %s\n     %s\n' "$1" "$2"; fail=$((fail + 1)); }

# A throwaway git repo with one commit, so the hook has a real tree to hash.
# The .gitignore is COMMITTED and covers every artifact the tests drop inside
# the repo: since hub#855 the hook refuses to run when the working tree does
# not match the pushed tree, and untracked non-ignored files count as a
# mismatch (cargo compiles what is on disk, not what is committed).
make_repo() {
    local dir
    dir=$(mktemp -d)
    git -C "$dir" init -q
    git -C "$dir" config user.email gate@test
    git -C "$dir" config user.name gate
    echo one > "$dir/file"
    printf '%s\n' .out .state RAN RUNS STATUS STATUSES TRACE ENV POSTED POSTARGS OWNER ghbin nogh nowhere > "$dir/.gitignore"
    git -C "$dir" add file .gitignore
    git -C "$dir" commit -qm one
    echo "$dir"
}

# Run the hook inside $repo with the given stdin, capturing exit code + output.
run_hook() {
    local repo=$1 stdin=$2
    shift 2
    # Desde el 29/08 el gate materializa el catálogo de módulos POR DEFECTO (hub#1353). Estos
    # bancos son repos de mentira sin `scripts/materialize-published-modules.sh`, y salvo el caso
    # que prueba justamente ese defecto, ninguno va de módulos: se apaga para no medir otra cosa.
    case " $* " in
        *HUB_GATE_WITH_MODULES=*|*HUB_GATE_MATERIALIZE_CMD=*) ;;
        *) set -- "$@" HUB_GATE_WITH_MODULES=0 ;;
    esac
    # Desde hub#1466 el DEFECTO del hook es el gate rápido (la suite pesada vive en Actions).
    # Los casos de este fichero anteriores a ese cambio prueban el gate COMPLETO —suite, caché
    # del verde, atestación—, así que se les pone `full` explícito: es lo que de verdad ejercitan.
    # Quien quiera probar el modo rápido, o el DEFECTO, nombra HUB_GATE_DEPTH o HUB_GATE_FAST_CMD
    # y queda exento (mismo patrón que HUB_GATE_WITH_MODULES, arriba).
    case " $* " in
        *HUB_GATE_DEPTH=*|*HUB_GATE_FAST_CMD=*) ;;
        *) set -- "$@" HUB_GATE_DEPTH=full ;;
    esac
    ( cd "$repo" && printf '%s\n' "$stdin" | env "$@" bash "$HOOK" ) >"$repo/.out" 2>&1
    echo $?
}

echo "pre-push local gate"

# ── 1. Disarmed is the default: it must never block anyone ────────────────────
repo=$(make_repo)
sha=$(git -C "$repo" rev-parse HEAD)
code=$(run_hook "$repo" "refs/heads/x $sha refs/heads/x $ZERO" \
    HUB_GATE_STATE_DIR="$repo/.state" \
    HUB_GATE_TEST_CMD="touch $repo/RAN; true")
[ "$code" = 0 ] && [ ! -f "$repo/RAN" ] \
    && ok "disarmed: lets the push through without running the suite" \
    || bad "disarmed: lets the push through without running the suite" "exit=$code ran=$([ -f "$repo/RAN" ] && echo yes || echo no)"

# ── 2. Armed + branch deletion only: nothing to test ──────────────────────────
repo=$(make_repo)
git -C "$repo" config --bool hooks.hubPrepushGate true
code=$(run_hook "$repo" "refs/heads/x $ZERO refs/heads/x $ZERO" \
    HUB_GATE_STATE_DIR="$repo/.state" \
    HUB_GATE_TEST_CMD="touch $repo/RAN; true")
[ "$code" = 0 ] && [ ! -f "$repo/RAN" ] \
    && ok "armed: a branch deletion skips the suite" \
    || bad "armed: a branch deletion skips the suite" "exit=$code ran=$([ -f "$repo/RAN" ] && echo yes || echo no)"

# ── 3. Armed + explicit bypass ────────────────────────────────────────────────
repo=$(make_repo)
git -C "$repo" config --bool hooks.hubPrepushGate true
sha=$(git -C "$repo" rev-parse HEAD)
code=$(run_hook "$repo" "refs/heads/x $sha refs/heads/x $ZERO" \
    HUB_GATE_STATE_DIR="$repo/.state" SKIP_HUB_TESTS=1 \
    HUB_GATE_TEST_CMD="touch $repo/RAN; true")
[ "$code" = 0 ] && [ ! -f "$repo/RAN" ] \
    && ok "armed: SKIP_HUB_TESTS=1 bypasses the gate" \
    || bad "armed: SKIP_HUB_TESTS=1 bypasses the gate" "exit=$code ran=$([ -f "$repo/RAN" ] && echo yes || echo no)"

# ── 4. Armed + red suite: the push must ABORT ─────────────────────────────────
repo=$(make_repo)
git -C "$repo" config --bool hooks.hubPrepushGate true
sha=$(git -C "$repo" rev-parse HEAD)
code=$(run_hook "$repo" "refs/heads/x $sha refs/heads/x $ZERO" \
    HUB_GATE_STATE_DIR="$repo/.state" \
    HUB_GATE_STATUS_CMD="echo \$1 >> $repo/STATUS" \
    HUB_GATE_TEST_CMD="touch $repo/RAN; false")
# `code != 0` alone would also pass when the hook is missing entirely (127),
# so require proof that the suite actually ran and was judged red.
[ "$code" = 1 ] && [ -f "$repo/RAN" ] && [ ! -f "$repo/STATUS" ] \
    && ok "red suite: aborts the push and publishes no green status" \
    || bad "red suite: aborts the push and publishes no green status" "exit=$code ran=$([ -f "$repo/RAN" ] && echo yes || echo no) status=$(cat "$repo/STATUS" 2>/dev/null)"

# ── 5. Armed + green suite: push proceeds and the status names the pushed sha ──
repo=$(make_repo)
git -C "$repo" config --bool hooks.hubPrepushGate true
sha=$(git -C "$repo" rev-parse HEAD)
code=$(run_hook "$repo" "refs/heads/x $sha refs/heads/x $ZERO" \
    HUB_GATE_STATE_DIR="$repo/.state" \
    HUB_GATE_STATUS_CMD="echo \$1 > $repo/STATUS" \
    HUB_GATE_TEST_CMD="true")
sleep 1   # the status is published in the background, after the push lands
[ "$code" = 0 ] && [ "$(cat "$repo/STATUS" 2>/dev/null)" = "$sha" ] \
    && ok "green suite: push proceeds and the status carries the pushed sha" \
    || bad "green suite: push proceeds and the status carries the pushed sha" "exit=$code status=$(cat "$repo/STATUS" 2>/dev/null) want=$sha"

# ── 5bis. PROFUNDIDAD del gate (hub#1466): rápido en local, pesado en la nube ──
#    Medido el 2026-09-03 en este workspace: `cargo check` 84 s en frío y 3,6 s en caliente,
#    `fmt` 2,8 s, `clippy` 20 s → ~27 s el gate rápido en el caso que importa (el arreglo tras
#    una revisión), frente a los ~20 min de la suite. La suite pesada pasa a Actions, donde
#    corren 4 a la vez en vez de una cada 20 min con el lock de la máquina.
#
#    ⚠️ La regla que estos tests fijan: el modo rápido NO atestigua. La atestación es lo que
#    `merge-pr.sh` acepta como «la suite corrió sobre este sha»; firmarla tras un `cargo check`
#    sería responder que sí a una pregunta que no se probó. Sin sello, autoriza el check de CI.
repo=$(make_repo)
git -C "$repo" config --bool hooks.hubPrepushGate true
sha=$(git -C "$repo" rev-parse HEAD)
code=$(run_hook "$repo" "refs/heads/x $sha refs/heads/x $ZERO" \
    HUB_GATE_STATE_DIR="$repo/.state" \
    HUB_GATE_STATUS_CMD="echo \$1 > $repo/STATUS" \
    HUB_GATE_DEPTH=fast \
    HUB_GATE_FAST_CMD="echo fast >> $repo/FAST; true" \
    HUB_GATE_TEST_CMD="echo suite >> $repo/SUITE; true")
sleep 1
[ "$code" = 0 ] && [ -s "$repo/FAST" ] \
    && ok "depth=fast: corre el comando RÁPIDO" \
    || bad "depth=fast: corre el comando RÁPIDO" "exit=$code fast=$(cat "$repo/FAST" 2>/dev/null)"
[ ! -s "$repo/SUITE" ] \
    && ok "depth=fast: y NO corre la suite pesada" \
    || bad "depth=fast: y NO corre la suite pesada" "la suite corrió: $(cat "$repo/SUITE")"
[ ! -s "$repo/STATUS" ] \
    && ok "depth=fast: NO atestigua (sin sello, autoriza el check de CI)" \
    || bad "depth=fast: NO atestigua" "publicó: $(cat "$repo/STATUS" 2>/dev/null)"

# Rojo en el rápido = push abortado. Sin esto el modo rápido no protege nada.
repo=$(make_repo)
git -C "$repo" config --bool hooks.hubPrepushGate true
sha=$(git -C "$repo" rev-parse HEAD)
code=$(run_hook "$repo" "refs/heads/x $sha refs/heads/x $ZERO" \
    HUB_GATE_STATE_DIR="$repo/.state" \
    HUB_GATE_STATUS_CMD="echo \$1 > $repo/STATUS" \
    HUB_GATE_DEPTH=fast \
    HUB_GATE_FAST_CMD="false" \
    HUB_GATE_TEST_CMD="echo suite >> $repo/SUITE; true")
[ "$code" != 0 ] \
    && ok "depth=fast ROJO: el push ABORTA (una rama que no compila no sube)" \
    || bad "depth=fast ROJO: el push ABORTA" "exit=$code"
[ ! -s "$repo/STATUS" ] \
    && ok "y un rápido rojo tampoco atestigua" \
    || bad "y un rápido rojo tampoco atestigua" "publicó: $(cat "$repo/STATUS" 2>/dev/null)"

# CONTROL de la bifurcación: en `full` manda todo lo de siempre — suite y sello.
repo=$(make_repo)
git -C "$repo" config --bool hooks.hubPrepushGate true
sha=$(git -C "$repo" rev-parse HEAD)
code=$(run_hook "$repo" "refs/heads/x $sha refs/heads/x $ZERO" \
    HUB_GATE_STATE_DIR="$repo/.state" \
    HUB_GATE_STATUS_CMD="echo \$1 > $repo/STATUS" \
    HUB_GATE_DEPTH=full \
    HUB_GATE_FAST_CMD="echo fast >> $repo/FAST; true" \
    HUB_GATE_TEST_CMD="echo suite >> $repo/SUITE; true")
sleep 1
[ "$code" = 0 ] && [ -s "$repo/SUITE" ] && [ ! -s "$repo/FAST" ] \
    && ok "depth=full (control): corre la SUITE y no el rápido" \
    || bad "depth=full (control): corre la SUITE y no el rápido" "exit=$code suite=$(cat "$repo/SUITE" 2>/dev/null) fast=$(cat "$repo/FAST" 2>/dev/null)"
[ "$(cat "$repo/STATUS" 2>/dev/null)" = "$sha" ] \
    && ok "depth=full (control): SÍ atestigua sobre el sha empujado" \
    || bad "depth=full (control): SÍ atestigua" "status=$(cat "$repo/STATUS" 2>/dev/null) want=$sha"

# El DEFECTO es rápido: es lo que decide qué corre la flota sin pasar variables.
repo=$(make_repo)
git -C "$repo" config --bool hooks.hubPrepushGate true
sha=$(git -C "$repo" rev-parse HEAD)
code=$(run_hook "$repo" "refs/heads/x $sha refs/heads/x $ZERO" \
    HUB_GATE_STATE_DIR="$repo/.state" \
    HUB_GATE_STATUS_CMD="true" \
    HUB_GATE_FAST_CMD="echo fast >> $repo/FAST; true" \
    HUB_GATE_TEST_CMD="echo suite >> $repo/SUITE; true")
[ "$code" = 0 ] && [ -s "$repo/FAST" ] && [ ! -s "$repo/SUITE" ] \
    && ok "sin variable, el DEFECTO es rápido (la suite pesada vive en Actions)" \
    || bad "sin variable, el DEFECTO es rápido" "exit=$code fast=$(cat "$repo/FAST" 2>/dev/null) suite=$(cat "$repo/SUITE" 2>/dev/null)"

# Un valor que no existe no puede degradar la protección en silencio.
repo=$(make_repo)
git -C "$repo" config --bool hooks.hubPrepushGate true
sha=$(git -C "$repo" rev-parse HEAD)
code=$(run_hook "$repo" "refs/heads/x $sha refs/heads/x $ZERO" \
    HUB_GATE_STATE_DIR="$repo/.state" HUB_GATE_STATUS_CMD="true" \
    HUB_GATE_DEPTH=loquesea \
    HUB_GATE_FAST_CMD="true" HUB_GATE_TEST_CMD="true")
[ "$code" != 0 ] \
    && ok "un HUB_GATE_DEPTH desconocido FALLA en vez de elegir por su cuenta" \
    || bad "un HUB_GATE_DEPTH desconocido falla" "exit=$code"

# ── 5ter. El comando rápido por defecto calca la CI: clippy SIN -D warnings (hub#1472) ──
#    Cazado por la sonda de hub#1466 nada más mergear: el hook se auto-instaló y TODO push del
#    hub abortaba, también uno sano. `develop` arrastra 209 avisos de clippy (medido 03/09) y
#    `test-hub.yml` corre `cargo clippy --workspace --all-targets --no-deps --exclude …` SIN
#    `-D warnings`; el gate local era más estricto que la CI que autoriza el merge. Es una
#    aserción sobre el TEXTO del hook a propósito: el comando por defecto no se puede ejecutar
#    en estos bancos (no hay cargo), y lo que hay que fijar es la paridad de flags con la CI.
#    El día que la CI se ponga estricta, se cambian los dos a la vez y este test con ellos.
# The ASSIGNMENT line, never a comment: the first draft grabbed the comment that explains this
# very rule (it mentions `-D warnings`) and failed against the fixed hook.
fast_default="$(awk '/HUB_GATE_DEPTH:-fast}" = fast/{f=1} f && !/^ *#/ && /fast_cmd=.*cargo clippy/{print; exit}' "$HOOK")"
if [ -z "$fast_default" ]; then
    bad "hub#1472: el modo rápido tiene un clippy por defecto" "no se encontró la línea de clippy en el bloque rápido"
else
    case "$fast_default" in
        *"-D warnings"*) bad "hub#1472: el clippy del modo rápido NO lleva -D warnings" "lleva -D warnings: con los 209 avisos de develop aborta cualquier push, también uno sano (la CI no es estricta)" ;;
        *) ok "hub#1472: el clippy del modo rápido NO lleva -D warnings (paridad con test-hub.yml)" ;;
    esac
    case "$fast_default" in
        *"--no-deps"*) ok "hub#1472: y lleva --no-deps, como la CI" ;;
        *) bad "hub#1472: y lleva --no-deps, como la CI" "sin --no-deps clippy también analiza las dependencias: más lento y con avisos que no son nuestros" ;;
    esac
fi
# ── 5quater. …y SIN `cargo fmt --check` (hub#1474): la CI no exige fmt y develop no está formateado ──
#    Segunda mordida de la misma sonda, con el clippy ya en paridad: `cargo fmt --all --check`
#    sale con exit 1 y 364 diffs sobre develop (medido 03/09), y ni test-hub.yml ni actionlint
#    tienen paso de fmt. Regla: el gate rápido solo exige lo que la CI exige. Se mira el bloque
#    ENTERO del comando por defecto (todas las asignaciones `fast_cmd=`), no una línea.
fast_block="$(awk '/HUB_GATE_DEPTH:-fast}" = fast/{f=1} f && !/^ *#/ && /fast_cmd=/{print} f && /^    fi$/{exit}' "$HOOK")"
if [ -z "$fast_block" ]; then
    bad "hub#1474: el bloque del comando rápido por defecto existe" "no se encontraron asignaciones fast_cmd= tras el arranque del modo rápido"
else
    case "$fast_block" in
        *"cargo fmt"*) bad "hub#1474: el modo rápido NO invoca cargo fmt" "invoca cargo fmt: develop tiene 364 ficheros sin formatear y la CI no exige fmt → todo push aborta" ;;
        *) ok "hub#1474: el modo rápido NO invoca cargo fmt (la CI tampoco)" ;;
    esac
    case "$fast_block" in
        *"cargo check"*) ok "hub#1474: y sí invoca cargo check (control)" ;;
        *) bad "hub#1474: y sí invoca cargo check (control)" "sin cargo check el modo rápido no protege nada" ;;
    esac
fi

# ── 6. Same tree twice: the second push must NOT recompile ────────────────────
#    This is what keeps the fleet's 42 pushes/day from becoming 42 full suites.
repo=$(make_repo)
git -C "$repo" config --bool hooks.hubPrepushGate true
sha=$(git -C "$repo" rev-parse HEAD)
for _ in 1 2; do
    code=$(run_hook "$repo" "refs/heads/x $sha refs/heads/x $ZERO" \
        HUB_GATE_STATE_DIR="$repo/.state" \
        HUB_GATE_STATUS_CMD="true" \
        HUB_GATE_TEST_CMD="echo run >> $repo/RUNS; true")
done
runs=$(wc -l < "$repo/RUNS" 2>/dev/null | tr -d ' ')
[ "$code" = 0 ] && [ "$runs" = 1 ] \
    && ok "unchanged tree: the suite runs once, the second push reuses the green" \
    || bad "unchanged tree: the suite runs once, the second push reuses the green" "exit=$code runs=$runs want=1"

# ── 7. A changed tree must NOT reuse the previous green ───────────────────────
echo two > "$repo/file"
git -C "$repo" commit -qam two
sha2=$(git -C "$repo" rev-parse HEAD)
code=$(run_hook "$repo" "refs/heads/x $sha2 refs/heads/x $ZERO" \
    HUB_GATE_STATE_DIR="$repo/.state" \
    HUB_GATE_STATUS_CMD="true" \
    HUB_GATE_TEST_CMD="echo run >> $repo/RUNS; true")
runs=$(wc -l < "$repo/RUNS" 2>/dev/null | tr -d ' ')
[ "$code" = 0 ] && [ "$runs" = 2 ] \
    && ok "changed tree: the green does not carry over" \
    || bad "changed tree: the green does not carry over" "exit=$code runs=$runs want=2"

# ── 8. The lock serialises concurrent pushes (19 worktrees share this hook) ────
#    Modeled as the real fleet works: two SEPARATE worktrees (each clean at its
#    own HEAD — since hub#855 the gate refuses a tree that mutates under it),
#    sharing ONE state dir the way the worktrees share .git/hub-gate.
repoA=$(make_repo)
repoB=$(make_repo)
git -C "$repoA" config --bool hooks.hubPrepushGate true
git -C "$repoB" config --bool hooks.hubPrepushGate true
echo other > "$repoB/file"; git -C "$repoB" commit -qam other   # distinct trees, no cache short-circuit
shaA=$(git -C "$repoA" rev-parse HEAD)
shaB=$(git -C "$repoB" rev-parse HEAD)
state=$(mktemp -d)
# Each run appends on entry and on exit; interleaved marks mean they overlapped.
slow_a="echo enter >> $state/TRACE; sleep 2; echo leave >> $state/TRACE; true"
run_hook "$repoA" "refs/heads/a $shaA refs/heads/a $ZERO" \
    HUB_GATE_STATE_DIR="$state" HUB_GATE_STATUS_CMD="true" \
    HUB_GATE_TEST_CMD="$slow_a" >/dev/null &
first=$!
sleep 0.3
run_hook "$repoB" "refs/heads/b $shaB refs/heads/b $ZERO" \
    HUB_GATE_STATE_DIR="$state" HUB_GATE_STATUS_CMD="true" \
    HUB_GATE_TEST_CMD="$slow_a" >/dev/null &
second=$!
wait $first $second
[ "$(tr '\n' ' ' < "$state/TRACE")" = "enter leave enter leave " ] \
    && ok "lock: two concurrent pushes run their suites one at a time" \
    || bad "lock: two concurrent pushes run their suites one at a time" "trace=$(tr '\n' ' ' < "$state/TRACE")"

# A monorepo layout: hub/ with modules-workspace/ as its sibling.
# `cd && pwd -P` so the expected path is symlink-resolved too: on macOS mktemp hands
# back /var/folders/… while the hook reports the real /private/var/folders/….
make_monorepo() {
    local base
    base=$(cd "$(mktemp -d)" && pwd -P)
    mkdir -p "$base/modules-workspace/modules" "$base/hub"
    git -C "$base/hub" init -q
    git -C "$base/hub" config user.email gate@test
    git -C "$base/hub" config user.name gate
    git -C "$base/hub" config --bool hooks.hubPrepushGate true
    echo one > "$base/hub/file"
    printf '%s\n' .out .state RAN RUNS STATUS TRACE ENV > "$base/hub/.gitignore"
    git -C "$base/hub" add file .gitignore
    git -C "$base/hub" commit -qm one
    echo "$base"
}

# A stand-in for scripts/materialize-published-modules.sh: it records the
# arguments the hook passed and answers with the directory it was told to fill.
# The real script has its own suite (scripts/materialize-published-modules.test.sh);
# what is under test HERE is the hook's half of the contract — which directory it
# asks for, what it does with the answer, and what it does with a refusal.
write_fake_materializer() {      # $1 = path of the fake  $2 = where to record the args
    cat > "$1" <<FAKE
#!/usr/bin/env bash
printf '%s\n' "\$*" > "$2"
dest=""
while [ \$# -gt 0 ]; do
    case "\$1" in --dest) dest="\$2"; shift 2 ;; *) shift ;; esac
done
mkdir -p "\$dest"
printf '%s\n' "\$dest"
FAKE
    chmod +x "$1"
}

# ── 9. Por defecto los e2e de módulos SÍ corren (Ioan, 2026-08-29) ───────────
#    La nota anterior decía «120 failures / 25 targets sobre un develop limpio, correrlos por
#    defecto bloquearía cada push». Describía el estado ANTES de hub#1153, cuando el catálogo se
#    leía de `modules-workspace` (la rifa de ramas). Desde que se materializa el catálogo
#    PUBLICADO, pasan: medido el 29/08 sobre `origin/develop` limpio — 30 binarios, 1 365 tests,
#    **0 fallos, 5m07s**, con 187 tests que solo pasan con módulos delante y 0 ignorados
#    (hub#1353). Y ahora es obligatorio: `test-hub-modules.yml` ya no corre en las PRs, así que si
#    el gate se los saltara no los correría NADIE — que es como una PR del kernel rompe un módulo
#    en producción.
base=$(make_monorepo)
sha=$(git -C "$base/hub" rev-parse HEAD)
code=$(run_hook "$base/hub" "refs/heads/x $sha refs/heads/x $ZERO" \
    HUB_GATE_STATE_DIR="$base/.state" HUB_GATE_STATUS_CMD="true" \
    HUB_GATE_MATERIALIZE_CMD="mkdir -p $base/.state/modules-main; echo $base/.state/modules-main #" \
    HUB_GATE_TEST_CMD="echo \"dir=\${ERPLORA_MODULES_DIR:-} skip=\${ERPLORA_E2E_ALLOW_SKIP:-}\" > $base/ENV; true")
got=$(cat "$base/ENV" 2>/dev/null)
case "$got" in
    "dir=$base/.state/modules-main skip="*|"dir="*"/modules-main skip=") ok "default: los e2e de modulos CORREN (catalogo materializado, sin ALLOW_SKIP)" ;;
    *) bad "default: los e2e de modulos CORREN (catalogo materializado, sin ALLOW_SKIP)" "exit=$code got='$got'" ;;
esac

# ── 10. Opt-in measures the PUBLISHED catalogue, NEVER modules-workspace ─────
#    Regression test for ERPlora/hub#1153. The hook used to export
#    `ERPLORA_MODULES_DIR=<monorepo>/modules-workspace/modules`, whose content is
#    whatever branch the last agent left each module on (9 of 27 were off `main`
#    on 2026-08-28). A gate that measures against that is a raffle, and it fails
#    in both directions: a module BEHIND reds a push that did not cause it, a
#    module AHEAD greens a contract that already moved (hub#540).
#
#    The contract now: the catalogue is MATERIALISED from each module's
#    `origin/main` into $STATE_DIR/modules-main, and modules-workspace may only
#    ever be handed over as an ID SOURCE (`--ids-from`), never as the answer.
base=$(make_monorepo)
write_fake_materializer "$base/fake-materialize" "$base/ARGS"
sha=$(git -C "$base/hub" rev-parse HEAD)
code=$(run_hook "$base/hub" "refs/heads/x $sha refs/heads/x $ZERO" \
    HUB_GATE_STATE_DIR="$base/.state" HUB_GATE_STATUS_CMD="true" \
    HUB_GATE_WITH_MODULES=1 \
    HUB_GATE_MATERIALIZE_CMD="bash $base/fake-materialize" \
    HUB_GATE_TEST_CMD="echo \"dir=\${ERPLORA_MODULES_DIR:-} skip=\${ERPLORA_E2E_ALLOW_SKIP:-}\" > $base/ENV; true")
got=$(cat "$base/ENV" 2>/dev/null)
args=$(cat "$base/ARGS" 2>/dev/null)
errs=""
[ "$code" = 0 ] || errs="$errs exit=$code"
[ "$got" = "dir=$base/.state/modules-main skip=" ] || errs="$errs got='$got'"
case "$got" in *modules-workspace*) errs="$errs THE-SUITE-WAS-POINTED-AT-THE-PARKED-CHECKOUT" ;; esac
case "$args" in *"--ids-from $base/modules-workspace/modules"*) ;; *) errs="$errs workspace-was-not-offered-as-an-id-source(args='$args')" ;; esac
[ -z "$errs" ] \
    && ok "opt-in: the suite measures the published catalogue, never modules-workspace (hub#1153)" \
    || bad "opt-in: the suite measures the published catalogue, never modules-workspace (hub#1153)" "$errs"

# ── 10b. An explicit ERPLORA_MODULES_DIR still wins ──────────────────────────
#    Documented escape hatch: pointing the gate at a tree you are debugging is
#    legitimate, and it must not trigger a materialisation on top of it.
base=$(make_monorepo)
sha=$(git -C "$base/hub" rev-parse HEAD)
code=$(run_hook "$base/hub" "refs/heads/x $sha refs/heads/x $ZERO" \
    HUB_GATE_STATE_DIR="$base/.state" HUB_GATE_STATUS_CMD="true" \
    HUB_GATE_WITH_MODULES=1 ERPLORA_MODULES_DIR="$base/hand-picked" \
    HUB_GATE_MATERIALIZE_CMD="touch $base/MATERIALIZED; echo $base/.state/modules-main" \
    HUB_GATE_TEST_CMD="echo \"dir=\${ERPLORA_MODULES_DIR:-}\" > $base/ENV; true")
got=$(cat "$base/ENV" 2>/dev/null)
errs=""
[ "$code" = 0 ] || errs="$errs exit=$code"
[ "$got" = "dir=$base/hand-picked" ] || errs="$errs got='$got'"
[ -f "$base/MATERIALIZED" ] && errs="$errs materialised-on-top-of-an-explicit-dir"
[ -z "$errs" ] \
    && ok "opt-in: an explicit ERPLORA_MODULES_DIR wins and nothing is materialised" \
    || bad "opt-in: an explicit ERPLORA_MODULES_DIR wins and nothing is materialised" "$errs"

# ── 11. A catalogue that cannot be materialised ABORTS the push ──────────────
#    The old hook warned and set ERPLORA_E2E_ALLOW_SKIP=1, so `HUB_GATE_WITH_MODULES=1`
#    could run the suite with the module e2e silently skipped — a green that
#    proved nothing, which is the exact hole hub#1153 is about. Opting in is a
#    request for the published catalogue; not getting it is a failure, not a
#    downgrade. The floor (>=25 manifests) is enforced inside the materialiser
#    and reaches the gate as a non-zero exit.
base=$(make_monorepo)
sha=$(git -C "$base/hub" rev-parse HEAD)
code=$(run_hook "$base/hub" "refs/heads/x $sha refs/heads/x $ZERO" \
    HUB_GATE_STATE_DIR="$base/.state" HUB_GATE_STATUS_CMD="true" \
    HUB_GATE_WITH_MODULES=1 \
    HUB_GATE_MATERIALIZE_CMD="echo 'only 3 module(s) with module.json — the floor is 25' >&2; exit 1" \
    HUB_GATE_TEST_CMD="touch $base/RAN; true")
errs=""
[ "$code" = 0 ] && errs="$errs push-was-let-through"
[ -f "$base/RAN" ] && errs="$errs suite-ran-without-the-published-catalogue"
grep -q "the floor is 25" "$base/hub/.out" 2>/dev/null || errs="$errs the-materialiser-error-was-swallowed"
grep -qi "HUB_GATE_WITH_MODULES" "$base/hub/.out" 2>/dev/null || errs="$errs no-hint-about-how-to-opt-out"
[ -z "$errs" ] \
    && ok "opt-in: a catalogue that cannot be materialised aborts the push, never a silent skip" \
    || bad "opt-in: a catalogue that cannot be materialised aborts the push, never a silent skip" "$errs out=$(tr '\n' ' ' < "$base/hub/.out" | tail -c 300)"

# ── 11b. A checkout with no materialiser fails LOUDLY, it does not degrade ───
#    An old checkout (or a botched install) is exactly when a silent fallback to
#    modules-workspace would come back.
base=$(make_monorepo)
sha=$(git -C "$base/hub" rev-parse HEAD)
code=$(run_hook "$base/hub" "refs/heads/x $sha refs/heads/x $ZERO" \
    HUB_GATE_STATE_DIR="$base/.state" HUB_GATE_STATUS_CMD="true" \
    HUB_GATE_WITH_MODULES=1 \
    HUB_GATE_TEST_CMD="touch $base/RAN; true")
errs=""
[ "$code" = 0 ] && errs="$errs push-was-let-through"
[ -f "$base/RAN" ] && errs="$errs suite-ran-anyway"
grep -q "materialize-published-modules.sh" "$base/hub/.out" 2>/dev/null || errs="$errs error-does-not-name-the-missing-script"
[ -z "$errs" ] \
    && ok "opt-in: a checkout without the materialiser aborts instead of falling back" \
    || bad "opt-in: a checkout without the materialiser aborts instead of falling back" "$errs out=$(tr '\n' ' ' < "$base/hub/.out" | tail -c 300)"

# ── 12. `blueprints/` is NOT a dependency of the gate any more ────────────────
#    It used to be: `sector_packs_pg_e2e` read its sector seeds out of that sibling
#    repo, those two tests have no opt-in, and from a worktree outside the monorepo
#    the relative path missed and the gate died with "no se pudo leer …/seed.sql" —
#    a red that had nothing to do with the push, on EVERY gated push of a fleet that
#    works out of /private/tmp. The hook grew a `resolve_blueprints_dir` for it.
#
#    hub#1050 moved the seeds into this repo, so the hook resolves nothing and this
#    asserts the contract that replaced it: a bare checkout, no sibling repo of any
#    kind on disk, and the gate still runs the suite and lets the push through.
repo=$(make_repo)
git -C "$repo" config --bool hooks.hubPrepushGate true
sha=$(git -C "$repo" rev-parse HEAD)
code=$(run_hook "$repo" "refs/heads/x $sha refs/heads/x $ZERO" \
    HUB_GATE_STATE_DIR="$repo/.state" HUB_GATE_STATUS_CMD="true" HOME="$repo/nowhere" \
    HUB_GATE_TEST_CMD="true")
[ "$code" = 0 ] \
    && ok "no sibling repos on disk: the gate still runs" \
    || bad "no sibling repos on disk: the gate still runs" "exit=$code"

# ─────────────────────────────────────────────────────────────────────────────
# 13–17 — the attestation must never fail SILENTLY (hub#739)
#
# Everything above drives the publish step through HUB_GATE_STATUS_CMD, which is
# precisely the path that never broke. The one that did is the DEFAULT: plain
# `gh`. When the active account cannot see the repo, the suite ran green, the
# status was never posted, and the hook said nothing — so what the human meets
# later is a PR with NO CHECKS, indistinguishable from "Actions is down". The
# natural reaction to that is to force the merge, which is the exact thing the
# CI-silence guard exists to prevent (it is how saas#1184 got in unverified).
#
# These tests point PATH at a fake `gh` so the real default path runs without
# ever calling GitHub.
# ─────────────────────────────────────────────────────────────────────────────

# Write a fake `gh` and echo the directory to prepend to PATH.
#
# 🔴 Every `case` arm in the bodies below is PARENTHESISED — `("repo view")`, not
# `"repo view")`. The bodies arrive through a heredoc fed to a command substitution,
# and bash 3.2 (what macOS ships, and what `env bash` resolves to when Homebrew's is
# not first on PATH) scans `$( … )` for its closing paren without understanding
# `case`: the first bare arm ends the substitution and the parser dies at the next
# `;;`. This file — the battery of the ONLY pre-merge proof of the hub — could not
# be parsed at all on the machine the gate runs on, and CI never saw it because the
# runners are Ubuntu with bash 5 (hub#1468). Guard: `scripts/ci/shell-syntax.sh`.
make_gh() {
    local dir=$1/ghbin
    mkdir -p "$dir"
    { echo '#!/usr/bin/env bash'; cat; } > "$dir/gh"
    chmod +x "$dir/gh"
    echo "$dir"
}

# A PATH with every tool the hook needs EXCEPT gh, so "gh is not installed" is a
# real absence and not a stub pretending to be one.
make_path_without_gh() {
    local dir=$1/nogh b p
    mkdir -p "$dir"
    for b in git bash sh mkdir rmdir sleep cat rm ln env printf echo sed grep tr wc uname dirname basename docker cargo; do
        p=$(command -v "$b" 2>/dev/null) && ln -sf "$p" "$dir/$b"
    done
    echo "$dir"
}

# ── 13. The account cannot see the repo → say so, do not exit 0 in silence ────
repo=$(make_repo)
git -C "$repo" config --bool hooks.hubPrepushGate true
sha=$(git -C "$repo" rev-parse HEAD)
ghdir=$(make_gh "$repo" <<'GH'
case "$1 $2" in
    ("repo view")
        echo 'gh: HTTP 404: Not Found (https://api.github.com/repos/ERPlora/hub)' >&2
        exit 1 ;;
    ("auth status")
        echo 'github.com'                                              >&2
        echo '  ✓ Logged in to github.com account other-company (keyring)' >&2
        exit 0 ;;
esac
exit 0
GH
)
code=$(run_hook "$repo" "refs/heads/x $sha refs/heads/x $ZERO" \
    HUB_GATE_STATE_DIR="$repo/.state" PATH="$ghdir:$PATH" \
    HUB_GATE_TEST_CMD="true")
sleep 1
out=$(cat "$repo/.out" 2>/dev/null)
errs=""
[ "$code" = 0 ]                                  || errs="$errs exit=$code(want 0)"
grep -qi 'could not be published' <<<"$out"      || errs="$errs no-verdict"
grep -q 'HTTP 404' <<<"$out"                     || errs="$errs no-gh-error"
grep -q 'other-company' <<<"$out"                || errs="$errs no-account"
grep -q 'local-gate/hub-tests' <<<"$out"         || errs="$errs no-context"
grep -qi 'without checks\|no checks' <<<"$out"   || errs="$errs no-symptom"
[ -z "$errs" ] \
    && ok "unpublishable status: the hook names the account and gh's error" \
    || bad "unpublishable status: the hook names the account and gh's error" "$errs"

# ── 14. …and the push still goes through: the suite WAS green ─────────────────
#    Aborting here would punish a green tree for a credential problem, and Ioan
#    switches the account by hand. The hook reports; it does not block.
[ "$code" = 0 ] && grep -qi 'green' <<<"$out" \
    && ok "unpublishable status: the push is not blocked, the green is stated" \
    || bad "unpublishable status: the push is not blocked, the green is stated" "exit=$code"

# ── 15. The failure is also left on disk, because it is printed asynchronously ─
#    The publish step outlives the hook, so its shout can land after the shell
#    prompt is back. A log makes it recoverable instead of merely scrolled past.
log="$repo/.state/publish-status.log"
[ -s "$log" ] && grep -q 'HTTP 404' "$log" \
    && ok "unpublishable status: the reason is recorded in publish-status.log" \
    || bad "unpublishable status: the reason is recorded in publish-status.log" "log=$(head -3 "$log" 2>/dev/null)"

# ── 16. `gh` not installed at all is the same silent hole ─────────────────────
repo=$(make_repo)
git -C "$repo" config --bool hooks.hubPrepushGate true
sha=$(git -C "$repo" rev-parse HEAD)
noghdir=$(make_path_without_gh "$repo")
code=$(run_hook "$repo" "refs/heads/x $sha refs/heads/x $ZERO" \
    HUB_GATE_STATE_DIR="$repo/.state" PATH="$noghdir" \
    HUB_GATE_TEST_CMD="true")
sleep 1
out=$(cat "$repo/.out" 2>/dev/null)
errs=""
[ "$code" = 0 ]                             || errs="$errs exit=$code(want 0)"
grep -qi 'could not be published' <<<"$out" || errs="$errs no-verdict"
grep -qi "gh.*not\( on\)\? \(installed\|on PATH\)\|not on PATH" <<<"$out" || errs="$errs no-reason"
[ -z "$errs" ] \
    && ok "no gh on PATH: the hook says the attestation is missing" \
    || bad "no gh on PATH: the hook says the attestation is missing" "$errs"

# ── 17. The POST itself failing must shout too, not just the repo lookup ──────
#    This is the half that runs in the background, after the commit lands.
repo=$(make_repo)
git -C "$repo" config --bool hooks.hubPrepushGate true
sha=$(git -C "$repo" rev-parse HEAD)
ghdir=$(make_gh "$repo" <<'GH'
case "$1 $2" in
    ("repo view") echo 'ERPlora/hub'; exit 0 ;;
    ("auth status")
        echo '  ✓ Logged in to github.com account other-company (keyring)' >&2
        exit 0 ;;
esac
# `gh api …` — the push landed (the ref reads back), writing the status does not.
for a in "$@"; do [ "$a" = "-X" ] && { echo 'gh: HTTP 403: Resource not accessible by integration' >&2; exit 1; }; done
for a in "$@"; do case "$a" in (repos/*/git/ref/*) echo "$FAKE_REF_SHA"; exit 0 ;; esac; done
exit 0
GH
)
code=$(run_hook "$repo" "refs/heads/x $sha refs/heads/x $ZERO" \
    HUB_GATE_STATE_DIR="$repo/.state" PATH="$ghdir:$PATH" FAKE_REF_SHA="$sha" \
    HUB_GATE_TEST_CMD="true")
sleep 2
log="$repo/.state/publish-status.log"
errs=""
[ "$code" = 0 ]                             || errs="$errs exit=$code(want 0)"
grep -qi 'could not be published' "$log" 2>/dev/null || errs="$errs no-verdict"
grep -q 'HTTP 403' "$log" 2>/dev/null       || errs="$errs no-gh-error"
grep -q 'other-company' "$log" 2>/dev/null  || errs="$errs no-account"
[ -z "$errs" ] \
    && ok "the status POST failing is reported, not swallowed" \
    || bad "the status POST failing is reported, not swallowed" "$errs log=$(head -3 "$log" 2>/dev/null)"

# ── 18. The happy default path still publishes — and says it did ──────────────
#    The regression guard for 14–18: making failure loud must not make success
#    stop working, and this is the only test that drives `gh` all the way.
repo=$(make_repo)
git -C "$repo" config --bool hooks.hubPrepushGate true
sha=$(git -C "$repo" rev-parse HEAD)
ghdir=$(make_gh "$repo" <<GH
case "\$1 \$2" in
    ("repo view") echo 'ERPlora/hub'; exit 0 ;;
    ("auth status") exit 0 ;;
esac
for a in "\$@"; do [ "\$a" = "-X" ] && { echo posted > "$repo/POSTED"; exit 0; }; done
for a in "\$@"; do case "\$a" in (repos/*/git/ref/*) echo "$sha"; exit 0 ;; esac; done
exit 0
GH
)
code=$(run_hook "$repo" "refs/heads/x $sha refs/heads/x $ZERO" \
    HUB_GATE_STATE_DIR="$repo/.state" PATH="$ghdir:$PATH" \
    HUB_GATE_TEST_CMD="true")
sleep 2
out=$(cat "$repo/.out" 2>/dev/null)
errs=""
[ "$code" = 0 ]                    || errs="$errs exit=$code(want 0)"
[ -f "$repo/POSTED" ]              || errs="$errs not-posted"
grep -qi 'could not be published' <<<"$out" && errs="$errs false-alarm"
[ -z "$errs" ] \
    && ok "green + a working gh: the status is posted and nothing cries wolf" \
    || bad "green + a working gh: the status is posted and nothing cries wolf" "$errs"

# ─────────────────────────────────────────────────────────────────────────────
# 19–21 — the INSTALLED copy must not drift silently from the versioned hook
# (hub#746)
#
# On the real machine `core.hooksPath` points OUTSIDE the repo
# (~/.erplora/hooks/hub), so the copy that decides a push is not the file the
# repo versions — and nothing syncs them. The hook therefore checks itself on
# every run against the checkout's `.githooks/pre-push`, and the attestation
# carries the hash of the copy that actually ran.
# ─────────────────────────────────────────────────────────────────────────────

# ── 19. Running copy differs from the versioned hook → loud drift warning ─────
#    The fixture commits a MODIFIED `.githooks/pre-push`, while the copy that
#    runs is the real one — exactly the installed-copy-is-stale shape.
repo=$(make_repo)
git -C "$repo" config --bool hooks.hubPrepushGate true
mkdir -p "$repo/.githooks"
cp "$HOOK" "$repo/.githooks/pre-push"
echo "# drifted by one line" >> "$repo/.githooks/pre-push"
git -C "$repo" add .githooks/pre-push
git -C "$repo" commit -qm hook
sha=$(git -C "$repo" rev-parse HEAD)
code=$(run_hook "$repo" "refs/heads/x $sha refs/heads/x $ZERO" \
    HUB_GATE_WITH_MODULES=0 HUB_GATE_STATE_DIR="$repo/.state" HUB_GATE_STATUS_CMD="true" \
    HUB_GATE_TEST_CMD="true")
out=$(cat "$repo/.out" 2>/dev/null)
errs=""
[ "$code" = 0 ]                                || errs="$errs exit=$code(want 0: drift warns, it does not block)"
grep -qi 'out of sync' <<<"$out"               || errs="$errs no-drift-warning"
grep -q 'install-hooks.sh' <<<"$out"           || errs="$errs no-resync-command"
[ -z "$errs" ] \
    && ok "drifted installed copy: the hook says so and names the resync command" \
    || bad "drifted installed copy: the hook says so and names the resync command" "$errs"

# ── 20. Running copy identical to the versioned hook → silence ────────────────
repo=$(make_repo)
git -C "$repo" config --bool hooks.hubPrepushGate true
mkdir -p "$repo/.githooks"
cp "$HOOK" "$repo/.githooks/pre-push"
git -C "$repo" add .githooks/pre-push
git -C "$repo" commit -qm hook
sha=$(git -C "$repo" rev-parse HEAD)
code=$(run_hook "$repo" "refs/heads/x $sha refs/heads/x $ZERO" \
    HUB_GATE_WITH_MODULES=0 HUB_GATE_STATE_DIR="$repo/.state" HUB_GATE_STATUS_CMD="true" \
    HUB_GATE_TEST_CMD="true")
out=$(cat "$repo/.out" 2>/dev/null)
errs=""
[ "$code" = 0 ]                       || errs="$errs exit=$code(want 0)"
grep -qi 'out of sync' <<<"$out"      && errs="$errs false-drift-alarm"
[ -z "$errs" ] \
    && ok "in-sync copies: no drift warning" \
    || bad "in-sync copies: no drift warning" "$errs"

# ── 21. The attestation names the hook that ran (hash in the description) ─────
#    Option 4 of hub#746: a stale gate's green becomes DISTINGUISHABLE on the
#    PR, because the status says which hook produced it.
repo=$(make_repo)
git -C "$repo" config --bool hooks.hubPrepushGate true
sha=$(git -C "$repo" rev-parse HEAD)
ghdir=$(make_gh "$repo" <<GH
case "\$1 \$2" in
    ("repo view") echo 'ERPlora/hub'; exit 0 ;;
    ("auth status") exit 0 ;;
esac
for a in "\$@"; do [ "\$a" = "-X" ] && { printf '%s\n' "\$@" > "$repo/POSTARGS"; exit 0; }; done
for a in "\$@"; do case "\$a" in (repos/*/git/ref/*) echo "$sha"; exit 0 ;; esac; done
exit 0
GH
)
code=$(run_hook "$repo" "refs/heads/x $sha refs/heads/x $ZERO" \
    HUB_GATE_STATE_DIR="$repo/.state" PATH="$ghdir:$PATH" \
    HUB_GATE_TEST_CMD="true")
sleep 2
errs=""
[ "$code" = 0 ]                                              || errs="$errs exit=$code(want 0)"
grep -qE 'hook [0-9a-f]{12}' "$repo/POSTARGS" 2>/dev/null    || errs="$errs no-hook-hash-in-description args=$(tr '\n' ' ' < "$repo/POSTARGS" 2>/dev/null)"
[ -z "$errs" ] \
    && ok "the posted status says which hook attested (12-hex hash)" \
    || bad "the posted status says which hook attested (12-hex hash)" "$errs"

# ─────────────────────────────────────────────────────────────────────────────
# 22–25 — the lock must know its OWNER, and detect that the owner died
# (hub#575)
#
# A push killed mid-suite (turn timeout, Ctrl-C, SIGKILL on the process tree)
# used to leave the bare `mkdir` lock behind: every later push then waited up
# to an hour for a dead owner, with a message claiming a suite was running.
# And breaking it by hand is dangerous in the other direction — the day it was
# tried, a LIVE suite was running and the manual removal started a second one
# in parallel (the exact condition the lock exists to prevent, hub#526).
# ─────────────────────────────────────────────────────────────────────────────

# ── 22. Holding the lock writes an owner file; releasing cleans it all up ─────
repo=$(make_repo)
git -C "$repo" config --bool hooks.hubPrepushGate true
sha=$(git -C "$repo" rev-parse HEAD)
code=$(run_hook "$repo" "refs/heads/x $sha refs/heads/x $ZERO" \
    HUB_GATE_WITH_MODULES=0 HUB_GATE_STATE_DIR="$repo/.state" HUB_GATE_STATUS_CMD="true" \
    HUB_GATE_TEST_CMD="cat $repo/.state/lock/owner > $repo/OWNER 2>/dev/null; true")
errs=""
[ "$code" = 0 ]                                  || errs="$errs exit=$code(want 0)"
grep -q '^pid=[0-9]' "$repo/OWNER" 2>/dev/null   || errs="$errs no-pid owner='$(cat "$repo/OWNER" 2>/dev/null)'"
grep -q '^since=[0-9]' "$repo/OWNER" 2>/dev/null || errs="$errs no-since"
[ ! -d "$repo/.state/lock" ]                     || errs="$errs lock-left-behind"
[ -z "$errs" ] \
    && ok "the lock carries pid + since while held, and is removed on exit" \
    || bad "the lock carries pid + since while held, and is removed on exit" "$errs"

# ── 23. Orphan lock (owner is dead): break it, say whose it was, run the suite ─
repo=$(make_repo)
git -C "$repo" config --bool hooks.hubPrepushGate true
sha=$(git -C "$repo" rev-parse HEAD)
( exit 0 ) & dead_pid=$!
wait "$dead_pid" 2>/dev/null
mkdir -p "$repo/.state/lock"
printf 'pid=%s\nsince=%s\n' "$dead_pid" "$(date +%s)" > "$repo/.state/lock/owner"
code=$(run_hook "$repo" "refs/heads/x $sha refs/heads/x $ZERO" \
    HUB_GATE_WITH_MODULES=0 HUB_GATE_STATE_DIR="$repo/.state" HUB_GATE_STATUS_CMD="true" \
    HUB_GATE_LOCK_WAIT=20 \
    HUB_GATE_TEST_CMD="touch $repo/RAN; true")
out=$(cat "$repo/.out" 2>/dev/null)
errs=""
[ "$code" = 0 ]                        || errs="$errs exit=$code(want 0)"
[ -f "$repo/RAN" ]                     || errs="$errs suite-never-ran"
grep -qi 'orphan' <<<"$out"            || errs="$errs no-orphan-message"
grep -q "$dead_pid" <<<"$out"          || errs="$errs dead-pid-not-named"
[ ! -d "$repo/.state/lock" ]           || errs="$errs lock-left-behind"
[ -z "$errs" ] \
    && ok "orphan lock: broken automatically, naming the dead owner's PID" \
    || bad "orphan lock: broken automatically, naming the dead owner's PID" "$errs out='$out'"

# ── 24. LIVE owner: wait (never break), name who is holding, time out clearly ──
#    Conservative by contract: breaking a live lock starts two suites in
#    parallel, which is the hub#526 failure the lock exists to prevent.
repo=$(make_repo)
git -C "$repo" config --bool hooks.hubPrepushGate true
sha=$(git -C "$repo" rev-parse HEAD)
mkdir -p "$repo/.state/lock"
printf 'pid=%s\nsince=%s\n' "$$" "$(date +%s)" > "$repo/.state/lock/owner"
code=$(run_hook "$repo" "refs/heads/x $sha refs/heads/x $ZERO" \
    HUB_GATE_WITH_MODULES=0 HUB_GATE_STATE_DIR="$repo/.state" HUB_GATE_STATUS_CMD="true" \
    HUB_GATE_LOCK_WAIT=4 \
    HUB_GATE_TEST_CMD="touch $repo/RAN; true")
out=$(cat "$repo/.out" 2>/dev/null)
errs=""
[ "$code" = 1 ]                        || errs="$errs exit=$code(want 1)"
[ ! -f "$repo/RAN" ]                   || errs="$errs suite-ran-past-a-live-lock"
[ -d "$repo/.state/lock" ]             || errs="$errs live-lock-was-broken"
grep -q "$$" <<<"$out"                 || errs="$errs owner-pid-not-named"
grep -q "rm -rf" <<<"$out"             || errs="$errs no-manual-removal-command"
[ -z "$errs" ] \
    && ok "live owner: waits without breaking, names the PID, and times out with the exact command" \
    || bad "live owner: waits without breaking, names the PID, and times out with the exact command" "$errs out='$out'"

# ── 25. Lock WITHOUT an owner file: when in doubt, wait — never break ─────────
#    A pre-hub#575 lock, or an owner file whose write is still in flight,
#    is indistinguishable from a live suite. The conservative direction is
#    to wait for the timeout, exactly as before.
repo=$(make_repo)
git -C "$repo" config --bool hooks.hubPrepushGate true
sha=$(git -C "$repo" rev-parse HEAD)
mkdir -p "$repo/.state/lock"
code=$(run_hook "$repo" "refs/heads/x $sha refs/heads/x $ZERO" \
    HUB_GATE_WITH_MODULES=0 HUB_GATE_STATE_DIR="$repo/.state" HUB_GATE_STATUS_CMD="true" \
    HUB_GATE_LOCK_WAIT=4 \
    HUB_GATE_TEST_CMD="touch $repo/RAN; true")
errs=""
[ "$code" = 1 ]                || errs="$errs exit=$code(want 1)"
[ ! -f "$repo/RAN" ]           || errs="$errs suite-ran"
[ -d "$repo/.state/lock" ]     || errs="$errs ownerless-lock-was-broken"
[ -z "$errs" ] \
    && ok "ownerless lock: waits conservatively instead of breaking it" \
    || bad "ownerless lock: waits conservatively instead of breaking it" "$errs"

# ─────────────────────────────────────────────────────────────────────────────
# 26–28 — the SSH keepalive lives in the REPO, and the lock wait must never
# outlast what the connection tolerates (hub#788)
#
# `git push` opens the SSH transport BEFORE this hook runs. A lock wait of
# 3600s against an idle connection gets closed by GitHub, and the push dies in
# silence having run zero tests. The keepalive used to live only in one
# machine's .git/config; the hook now guarantees it, and keeps the inequality
# keepalive margin (Interval × CountMax) > max lock wait — by capping the
# wait, never by trusting the connection.
# ─────────────────────────────────────────────────────────────────────────────

# ── 26. A repo without keepalive: the hook installs it for the NEXT pushes ────
repo=$(make_repo)
git -C "$repo" config --bool hooks.hubPrepushGate true
sha=$(git -C "$repo" rev-parse HEAD)
code=$(run_hook "$repo" "refs/heads/x $sha refs/heads/x $ZERO" \
    HUB_GATE_WITH_MODULES=0 HUB_GATE_STATE_DIR="$repo/.state" HUB_GATE_STATUS_CMD="true" \
    HUB_GATE_TEST_CMD="true")
sshcmd=$(git -C "$repo" config core.sshCommand 2>/dev/null)
errs=""
[ "$code" = 0 ]                                 || errs="$errs exit=$code(want 0)"
grep -q 'ServerAliveInterval' <<<"$sshcmd"      || errs="$errs keepalive-not-installed sshCommand='$sshcmd'"
[ -z "$errs" ] \
    && ok "no keepalive configured: the hook arms core.sshCommand itself" \
    || bad "no keepalive configured: the hook arms core.sshCommand itself" "$errs"

# ── 27. UNPROTECTED connection: fail fast on lock contention, never wait 1h ───
#    The keepalive the hook just installed does not protect THIS push — its
#    connection was opened before. Waiting the full HUB_GATE_LOCK_WAIT on it
#    reproduces the silent death; the hook must cap the wait and say why.
repo=$(make_repo)
git -C "$repo" config --bool hooks.hubPrepushGate true
sha=$(git -C "$repo" rev-parse HEAD)
mkdir -p "$repo/.state/lock"
printf 'pid=%s\nsince=%s\n' "$$" "$(date +%s)" > "$repo/.state/lock/owner"
start=$SECONDS
code=$(run_hook "$repo" "refs/heads/x $sha refs/heads/x $ZERO" \
    HUB_GATE_WITH_MODULES=0 HUB_GATE_STATE_DIR="$repo/.state" HUB_GATE_STATUS_CMD="true" \
    HUB_GATE_LOCK_WAIT=3600 HUB_GATE_UNPROTECTED_LOCK_WAIT=2 \
    HUB_GATE_TEST_CMD="touch $repo/RAN; true")
took=$((SECONDS - start))
out=$(cat "$repo/.out" 2>/dev/null)
errs=""
[ "$code" = 1 ]                       || errs="$errs exit=$code(want 1)"
[ "$took" -lt 60 ]                    || errs="$errs took=${took}s(want fast fail)"
[ ! -f "$repo/RAN" ]                  || errs="$errs suite-ran"
grep -qi 'keepalive' <<<"$out"        || errs="$errs no-keepalive-explanation"
[ -z "$errs" ] \
    && ok "unprotected connection + lock contention: capped wait, fast clear failure" \
    || bad "unprotected connection + lock contention: capped wait, fast clear failure" "$errs out='$out'"

# ── 28. PROTECTED connection: the wait is clamped BELOW the keepalive margin ──
#    The inequality margin > wait must hold even if someone raises
#    HUB_GATE_LOCK_WAIT: the hook clamps the wait to the margin, it never
#    trusts the connection past what the keepalive guarantees.
repo=$(make_repo)
git -C "$repo" config --bool hooks.hubPrepushGate true
git -C "$repo" config core.sshCommand "ssh -o ServerAliveInterval=1 -o ServerAliveCountMax=4"
sha=$(git -C "$repo" rev-parse HEAD)
mkdir -p "$repo/.state/lock"
printf 'pid=%s\nsince=%s\n' "$$" "$(date +%s)" > "$repo/.state/lock/owner"
start=$SECONDS
code=$(run_hook "$repo" "refs/heads/x $sha refs/heads/x $ZERO" \
    HUB_GATE_WITH_MODULES=0 HUB_GATE_STATE_DIR="$repo/.state" HUB_GATE_STATUS_CMD="true" \
    HUB_GATE_LOCK_WAIT=3600 \
    HUB_GATE_TEST_CMD="touch $repo/RAN; true")
took=$((SECONDS - start))
out=$(cat "$repo/.out" 2>/dev/null)
errs=""
[ "$code" = 1 ]                       || errs="$errs exit=$code(want 1)"
[ "$took" -lt 60 ]                    || errs="$errs took=${took}s(want clamped to ~2s margin/2)"
[ ! -f "$repo/RAN" ]                  || errs="$errs suite-ran"
grep -qi 'clamp' <<<"$out"            || errs="$errs no-clamp-message"
[ -z "$errs" ] \
    && ok "wait ≥ keepalive margin: clamped below it, with a message naming both" \
    || bad "wait ≥ keepalive margin: clamped below it, with a message naming both" "$errs out='$out'"

# ─────────────────────────────────────────────────────────────────────────────
# 29–32 — the gate must TEST the tree it ATTESTS (hub#855, P0)
#
# The suite runs on the WORKING TREE; the cache key and the attestation name
# the PUSHED sha. When they differ — pushing another branch from the same
# worktree, pushing a tag from an unrelated checkout, or a dirty tree — the
# gate used to sign green a tree it never executed, and (worse) record that
# lie as a `.green` cache entry for everyone else. Since hub#854 removed Rust
# from CI, this gate is the ONLY Rust verification there is.
#
# The comparison is TREES, not shas: a reworded/rebased commit with identical
# content is still fine. A tree already proven green needs no working tree at
# all (test 33): the attestation is about content, and that content ran.
# ─────────────────────────────────────────────────────────────────────────────

# ── 29. Pushing a sha whose tree is NOT the working tree → refuse ─────────────
repo=$(make_repo)
git -C "$repo" config --bool hooks.hubPrepushGate true
old_sha=$(git -C "$repo" rev-parse HEAD)
echo two > "$repo/file"
git -C "$repo" commit -qam two   # HEAD moves on; we push the OLD sha
code=$(run_hook "$repo" "refs/heads/old $old_sha refs/heads/old $ZERO" \
    HUB_GATE_STATE_DIR="$repo/.state" \
    HUB_GATE_STATUS_CMD="echo \$1 >> $repo/STATUS" \
    HUB_GATE_TEST_CMD="touch $repo/RAN; true")
out=$(cat "$repo/.out" 2>/dev/null)
errs=""
[ "$code" = 1 ]                                   || errs="$errs exit=$code(want 1)"
[ ! -f "$repo/RAN" ]                              || errs="$errs suite-ran-on-wrong-tree"
[ ! -f "$repo/STATUS" ]                           || errs="$errs status-published"
ls "$repo/.state"/*.green >/dev/null 2>&1         && errs="$errs green-recorded"
grep -qi 'working tree' <<<"$out"                 || errs="$errs no-explanation"
[ -z "$errs" ] \
    && ok "pushed sha != working tree: refused, nothing tested, nothing attested" \
    || bad "pushed sha != working tree: refused, nothing tested, nothing attested" "$errs out='$out'"

# ── 30. Dirty working tree → refuse (the suite would test the dirt) ───────────
repo=$(make_repo)
git -C "$repo" config --bool hooks.hubPrepushGate true
sha=$(git -C "$repo" rev-parse HEAD)
echo dirty >> "$repo/file"
code=$(run_hook "$repo" "refs/heads/x $sha refs/heads/x $ZERO" \
    HUB_GATE_STATE_DIR="$repo/.state" \
    HUB_GATE_STATUS_CMD="echo \$1 >> $repo/STATUS" \
    HUB_GATE_TEST_CMD="touch $repo/RAN; true")
out=$(cat "$repo/.out" 2>/dev/null)
errs=""
[ "$code" = 1 ]                            || errs="$errs exit=$code(want 1)"
[ ! -f "$repo/RAN" ]                       || errs="$errs suite-ran"
[ ! -f "$repo/STATUS" ]                    || errs="$errs status-published"
ls "$repo/.state"/*.green >/dev/null 2>&1  && errs="$errs green-recorded"
[ -z "$errs" ] \
    && ok "dirty working tree: refused — a green here would sign untested content" \
    || bad "dirty working tree: refused — a green here would sign untested content" "$errs out='$out'"

# ── 31. Pushing a TAG from a checkout that moved on → refuse ──────────────────
#    The worst of the three shapes (hub#855's third door): a tag is pushed
#    from WHATEVER checkout is current, and nobody switches branches to tag.
repo=$(make_repo)
git -C "$repo" config --bool hooks.hubPrepushGate true
old_sha=$(git -C "$repo" rev-parse HEAD)
git -C "$repo" tag v9.9.9 "$old_sha"
echo two > "$repo/file"
git -C "$repo" commit -qam two
code=$(run_hook "$repo" "refs/tags/v9.9.9 $old_sha refs/tags/v9.9.9 $ZERO" \
    HUB_GATE_STATE_DIR="$repo/.state" \
    HUB_GATE_STATUS_CMD="echo \$1 >> $repo/STATUS" \
    HUB_GATE_TEST_CMD="touch $repo/RAN; true")
errs=""
[ "$code" = 1 ]                            || errs="$errs exit=$code(want 1)"
[ ! -f "$repo/RAN" ]                       || errs="$errs suite-ran"
ls "$repo/.state"/*.green >/dev/null 2>&1  && errs="$errs green-recorded"
[ -z "$errs" ] \
    && ok "tag pushed from a moved-on checkout: refused instead of caching a lie" \
    || bad "tag pushed from a moved-on checkout: refused instead of caching a lie" "$errs"

# ── 32. A tree ALREADY proven green needs no working tree: cache-hit passes ───
#    Deliberate: the attestation is about content. Once the pushed tree really
#    ran (recorded by a matching run), pushing that same sha again — or a tag
#    on it — from any checkout state is truthful and instant.
repo=$(make_repo)
git -C "$repo" config --bool hooks.hubPrepushGate true
sha=$(git -C "$repo" rev-parse HEAD)
code=$(run_hook "$repo" "refs/heads/x $sha refs/heads/x $ZERO" \
    HUB_GATE_WITH_MODULES=0 HUB_GATE_STATE_DIR="$repo/.state" HUB_GATE_STATUS_CMD="true" \
    HUB_GATE_TEST_CMD="echo run >> $repo/RUNS; true")
echo two > "$repo/file"
git -C "$repo" commit -qam two   # the checkout moves on; the green stays valid
code=$(run_hook "$repo" "refs/heads/x $sha refs/heads/x $ZERO" \
    HUB_GATE_WITH_MODULES=0 HUB_GATE_STATE_DIR="$repo/.state" HUB_GATE_STATUS_CMD="true" \
    HUB_GATE_TEST_CMD="echo run >> $repo/RUNS; true")
runs=$(wc -l < "$repo/RUNS" 2>/dev/null | tr -d ' ')
errs=""
[ "$code" = 0 ]      || errs="$errs exit=$code(want 0)"
[ "$runs" = 1 ]      || errs="$errs runs=$runs(want 1)"
[ -z "$errs" ] \
    && ok "already-green tree: passes from any checkout without rerunning" \
    || bad "already-green tree: passes from any checkout without rerunning" "$errs"

# ─────────────────────────────────────────────────────────────────────────────
# 33–35 — the attestation is the CONSEQUENCE of the push landing (hub#574)
#
# A pre-push hook cannot know whether the transfer will succeed — it runs
# before it. The publish step therefore verifies, from the background, that
# the REMOTE REF really advanced to (or past) the pushed sha before posting
# the status. "The commit exists on origin" is NOT enough: the same sha can be
# there from an earlier push to a throwaway ref while THIS push died (SIGPIPE,
# exit 141, closed SSH). And the terminal message must attest the TEST, not
# claim the push — workers read "→ pushing" while the branch never arrived.
#
# Poll injection (so these tests take milliseconds, not 120s):
#   HUB_GATE_PUSH_POLL_TRIES · HUB_GATE_PUSH_POLL_DELAY
# ─────────────────────────────────────────────────────────────────────────────

# ── 33. The push DIES: ref never advances → NO status, and the log says so ────
repo=$(make_repo)
git -C "$repo" config --bool hooks.hubPrepushGate true
sha=$(git -C "$repo" rev-parse HEAD)
ghdir=$(make_gh "$repo" <<'GH'
case "$1 $2" in
    ("repo view") echo 'ERPlora/hub'; exit 0 ;;
    ("auth status") exit 0 ;;
esac
for a in "$@"; do [ "$a" = "-X" ] && { echo posted > "$REPO_DIR/POSTED"; exit 0; }; done
for a in "$@"; do case "$a" in (repos/*/git/ref/*) echo 'gh: HTTP 404: Not Found' >&2; exit 1 ;; esac; done
exit 0
GH
)
code=$(run_hook "$repo" "refs/heads/x $sha refs/heads/x $ZERO" \
    HUB_GATE_STATE_DIR="$repo/.state" PATH="$ghdir:$PATH" REPO_DIR="$repo" \
    HUB_GATE_PUSH_POLL_TRIES=2 HUB_GATE_PUSH_POLL_DELAY=0 \
    HUB_GATE_TEST_CMD="true")
sleep 2
out=$(cat "$repo/.out" 2>/dev/null)
log="$repo/.state/publish-status.log"
errs=""
[ "$code" = 0 ]                                  || errs="$errs exit=$code(want 0: the gate cannot know yet)"
[ ! -f "$repo/POSTED" ]                          || errs="$errs status-posted-for-a-dead-push"
grep -qi 'did not land' "$log" 2>/dev/null       || errs="$errs log-does-not-say-it log=$(head -8 "$log" 2>/dev/null | tr '\n' ' ')"
grep -qi 'retry' "$log" 2>/dev/null              || errs="$errs no-retry-instruction"
[ -z "$errs" ] \
    && ok "dead push: no orphan status, and the log says the push did not land + retry" \
    || bad "dead push: no orphan status, and the log says the push did not land + retry" "$errs"

# ── 34. The ref advanced to the sha → the status posts, and the terminal is honest ─
#    The green message must attest the TEST and defer the push/attestation
#    claim to the verification — not announce "pushing" as a fact.
repo=$(make_repo)
git -C "$repo" config --bool hooks.hubPrepushGate true
sha=$(git -C "$repo" rev-parse HEAD)
ghdir=$(make_gh "$repo" <<GH
case "\$1 \$2" in
    ("repo view") echo 'ERPlora/hub'; exit 0 ;;
    ("auth status") exit 0 ;;
esac
for a in "\$@"; do [ "\$a" = "-X" ] && { echo posted > "$repo/POSTED"; exit 0; }; done
for a in "\$@"; do case "\$a" in (repos/*/git/ref/*) echo "$sha"; exit 0 ;; esac; done
exit 0
GH
)
code=$(run_hook "$repo" "refs/heads/x $sha refs/heads/x $ZERO" \
    HUB_GATE_STATE_DIR="$repo/.state" PATH="$ghdir:$PATH" \
    HUB_GATE_PUSH_POLL_TRIES=2 HUB_GATE_PUSH_POLL_DELAY=0 \
    HUB_GATE_TEST_CMD="true")
sleep 2
out=$(cat "$repo/.out" 2>/dev/null)
errs=""
[ "$code" = 0 ]                                || errs="$errs exit=$code(want 0)"
[ -f "$repo/POSTED" ]                          || errs="$errs not-posted"
grep -qi 'verified on origin' <<<"$out"        || errs="$errs message-does-not-defer-to-verification"
grep -qiE 'green → pushing|green -> pushing' <<<"$out" && errs="$errs still-claims-pushing"
[ -z "$errs" ] \
    && ok "landed push: status posted, and the terminal attests the test, not the push" \
    || bad "landed push: status posted, and the terminal attests the test, not the push" "$errs out='$out'"

# ── 35. The ref already moved PAST the sha (another worker pushed on top) ─────
#    Landing is "the ref contains the pushed sha", not "the ref equals it":
#    a fleet mate merging on top seconds later must not turn a real landing
#    into a false 'did not land'.
repo=$(make_repo)
git -C "$repo" config --bool hooks.hubPrepushGate true
sha=$(git -C "$repo" rev-parse HEAD)
other=1111111111111111111111111111111111111111
ghdir=$(make_gh "$repo" <<GH
case "\$1 \$2" in
    ("repo view") echo 'ERPlora/hub'; exit 0 ;;
    ("auth status") exit 0 ;;
esac
for a in "\$@"; do [ "\$a" = "-X" ] && { echo posted > "$repo/POSTED"; exit 0; }; done
for a in "\$@"; do case "\$a" in (repos/*/git/ref/*) echo "$other"; exit 0 ;; esac; done
for a in "\$@"; do case "\$a" in (repos/*/compare/*) echo "ahead"; exit 0 ;; esac; done
exit 0
GH
)
code=$(run_hook "$repo" "refs/heads/x $sha refs/heads/x $ZERO" \
    HUB_GATE_STATE_DIR="$repo/.state" PATH="$ghdir:$PATH" \
    HUB_GATE_PUSH_POLL_TRIES=2 HUB_GATE_PUSH_POLL_DELAY=0 \
    HUB_GATE_TEST_CMD="true")
sleep 2
errs=""
[ "$code" = 0 ]           || errs="$errs exit=$code(want 0)"
[ -f "$repo/POSTED" ]     || errs="$errs not-posted log=$(head -8 "$repo/.state/publish-status.log" 2>/dev/null | tr '\n' ' ')"
[ -z "$errs" ] \
    && ok "ref moved past the sha: still counts as landed (ancestor check), status posts" \
    || bad "ref moved past the sha: still counts as landed (ancestor check), status posts" "$errs"


# ─────────────────────────────────────────────────────────────────────────────
# 36–44 — SCOPE (hub#1207): the gate runs the packages the diff touches
#
# `cargo test --workspace` here duplicates, minute for minute, the suite
# `test-hub.yml` already runs on every `pull_request` over the org's own
# runners (unbilled minutes). The expensive copy is the one holding a
# machine-wide lock, so it — and only it — is the fleet's ceiling: ~8-10
# issues/day no matter how many workers push.
#
# So the local gate stops being a second full suite and becomes a fast
# smoke over what CHANGED. The lock STAYS (hub#526: two suites in parallel
# melt the machine); what shrinks is how long it is held.
#
# The property under test is the one that makes this safe to ship: the scope
# derived from a diff CONTAINS the touched package (and its dependents) and
# is NOT "everything" — plus the attestation naming exactly what ran, because
# a status that still says `--workspace` after a scoped run is a test that
# does not prove what it claims.
# ─────────────────────────────────────────────────────────────────────────────

# A toy cargo workspace: toy-a ← toy-b (dependent), toy-c standalone, plus a
# non-Rust file. Real `cargo metadata` runs against it — no network, no build.
# `origin/develop` is planted so the hook can resolve a base for a new branch,
# which is how the fleet always pushes.
make_cargo_repo() {
    local dir
    dir=$(mktemp -d)
    git -C "$dir" init -q
    git -C "$dir" config user.email gate@test
    git -C "$dir" config user.name gate
    printf '%s\n' .out .state RAN SCOPE POSTARGS POSTED ghbin target installed > "$dir/.gitignore"
    cat > "$dir/Cargo.toml" <<'TOML'
[workspace]
resolver = "2"
members = ["crates/a", "crates/b", "crates/c"]
TOML
    mkdir -p "$dir/crates/a/src" "$dir/crates/b/src" "$dir/crates/c/src" "$dir/web"
    mkdir -p "$dir/scripts/ci"
    cp "$ROOT/scripts/ci/test-scope.py" "$dir/scripts/ci/test-scope.py"
    cat > "$dir/crates/a/Cargo.toml" <<'TOML'
[package]
name = "toy-a"
version = "0.1.0"
edition = "2021"
TOML
    cat > "$dir/crates/b/Cargo.toml" <<'TOML'
[package]
name = "toy-b"
version = "0.1.0"
edition = "2021"

[dependencies]
toy-a = { path = "../a" }
TOML
    cat > "$dir/crates/c/Cargo.toml" <<'TOML'
[package]
name = "toy-c"
version = "0.1.0"
edition = "2021"
TOML
    for c in a b c; do echo "pub fn f() {}" > "$dir/crates/$c/src/lib.rs"; done
    echo "export const x = 1" > "$dir/web/app.ts"
    ( cd "$dir" && cargo metadata --no-deps --format-version 1 >/dev/null 2>&1 )
    git -C "$dir" add -A
    git -C "$dir" commit -qm base
    git -C "$dir" update-ref refs/remotes/origin/develop HEAD
    echo "$dir"
}

# Commit a change to $2 inside $1 and echo the new sha.
touch_and_commit() {
    local dir=$1 path=$2
    mkdir -p "$dir/$(dirname "$path")"
    echo "// changed $(date +%s%N)" >> "$dir/$path"
    git -C "$dir" add -A
    git -C "$dir" commit -qm "touch $path"
    git -C "$dir" rev-parse HEAD
}

# Run the hook over a new branch (remote sha ZERO — the fleet's shape) and
# capture the scope the hook resolved, via the injected test command.
run_scoped() {
    local repo=$1 sha=$2
    shift 2
    rm -f "$repo/SCOPE"
    # Estos casos fijan el resolutor de hub#1207, que hoy solo se usa con la politica `scoped`:
    # el DEFECTO desde el 29/08 es `workspace` (la nube ya no corre la suite en las PRs).
    run_hook "$repo" "refs/heads/x $sha refs/heads/x $ZERO" \
        HUB_GATE_SCOPE_POLICY=scoped \
        HUB_GATE_WITH_MODULES=0 HUB_GATE_STATE_DIR="$repo/.state" HUB_GATE_STATUS_CMD="true" \
        HUB_GATE_TEST_CMD='printf "%s|%s\n" "$HUB_GATE_SCOPE_MODE" "$HUB_GATE_SCOPE_PACKAGES" > '"$repo/SCOPE" \
        "$@"
}

# ── 36. A diff touching one leaf crate scopes to that crate ───────────────────
repo=$(make_cargo_repo)
git -C "$repo" config --bool hooks.hubPrepushGate true
sha=$(touch_and_commit "$repo" crates/c/src/lib.rs)
code=$(run_scoped "$repo" "$sha")
scope=$(cat "$repo/SCOPE" 2>/dev/null)
errs=""
[ "$code" = 0 ]                          || errs="$errs exit=$code(want 0) out=$(tr '\n' ' ' < "$repo/.out" | tail -c 400)"
grep -q '^packages|' <<<"$scope"         || errs="$errs mode-is-not-packages"
grep -q 'toy-c' <<<"$scope"              || errs="$errs missing-touched-package"
grep -q 'toy-a' <<<"$scope"              && errs="$errs scoped-run-includes-untouched-toy-a"
grep -q 'toy-b' <<<"$scope"              && errs="$errs scoped-run-includes-untouched-toy-b"
[ -z "$errs" ] \
    && ok "scope: a diff in one leaf crate runs that crate, not the workspace" \
    || bad "scope: a diff in one leaf crate runs that crate, not the workspace" "$errs scope='$scope'"

# ── 37. Dependents come along: touching a library tests whoever uses it ───────
#    Skipping them is how a scoped gate turns into a rubber stamp — toy-b
#    constructs toy-a's API and breaks without a single line of its own changing.
repo=$(make_cargo_repo)
git -C "$repo" config --bool hooks.hubPrepushGate true
sha=$(touch_and_commit "$repo" crates/a/src/lib.rs)
code=$(run_scoped "$repo" "$sha")
scope=$(cat "$repo/SCOPE" 2>/dev/null)
errs=""
[ "$code" = 0 ]                      || errs="$errs exit=$code(want 0)"
grep -q 'toy-a' <<<"$scope"          || errs="$errs missing-touched-package"
grep -q 'toy-b' <<<"$scope"          || errs="$errs missing-DEPENDENT-toy-b"
grep -q 'toy-c' <<<"$scope"          && errs="$errs unrelated-toy-c-included"
[ -z "$errs" ] \
    && ok "scope: a touched library drags its dependents in (toy-a → toy-b)" \
    || bad "scope: a touched library drags its dependents in (toy-a → toy-b)" "$errs scope='$scope'"

# ── 38. Transversal files fall back to the whole workspace, and say so ────────
#    Cargo.lock / the workspace manifest can change what EVERY crate compiles.
#    Pretending a scope exists there would be the dishonest half of this change.
for transversal in Cargo.lock Cargo.toml; do
    repo=$(make_cargo_repo)
    git -C "$repo" config --bool hooks.hubPrepushGate true
    sha=$(touch_and_commit "$repo" "$transversal")
    code=$(run_scoped "$repo" "$sha")
    scope=$(cat "$repo/SCOPE" 2>/dev/null)
    errs=""
    [ "$code" = 0 ]                   || errs="$errs exit=$code(want 0)"
    grep -q '^workspace|' <<<"$scope" || errs="$errs mode-is-not-workspace"
    [ -z "$errs" ] \
        && ok "scope: a diff touching $transversal falls back to the full workspace" \
        || bad "scope: a diff touching $transversal falls back to the full workspace" "$errs scope='$scope'"
done

# ── 39. A diff with no Rust in it runs no Rust at all ─────────────────────────
#    And it must not take the lock either: a web-only push waiting behind a
#    Rust suite is pure queue for nothing.
repo=$(make_cargo_repo)
git -C "$repo" config --bool hooks.hubPrepushGate true
sha=$(touch_and_commit "$repo" web/app.ts)
code=$(run_scoped "$repo" "$sha")
out=$(cat "$repo/.out" 2>/dev/null)
errs=""
[ "$code" = 0 ]                     || errs="$errs exit=$code(want 0)"
[ ! -f "$repo/SCOPE" ]              || errs="$errs suite-ran-for-a-web-only-diff scope=$(cat "$repo/SCOPE")"
[ ! -d "$repo/.state/lock" ]        || errs="$errs lock-left-behind"
grep -qi 'no rust' <<<"$out"        || errs="$errs does-not-say-why-it-skipped"
[ -z "$errs" ] \
    && ok "scope: a non-Rust diff runs no Rust suite and says why" \
    || bad "scope: a non-Rust diff runs no Rust suite and says why" "$errs out=$(tr '\n' ' ' <<<"$out" | tail -c 300)"

# ── 40. The attestation NAMES what ran — a scoped run is not `--workspace` ────
#    hub#1207's hard requirement: `merge-pr.sh` reads `local-gate/hub-tests` as
#    proof the workspace suite ran. A scoped run publishing THAT context would
#    let a partial run stand in for the full one. It gets its own context, so
#    merge-pr.sh sees the full-suite one as absent and falls through to the
#    Actions check — which really did run everything.
repo=$(make_cargo_repo)
git -C "$repo" config --bool hooks.hubPrepushGate true
sha=$(touch_and_commit "$repo" crates/c/src/lib.rs)
ghdir=$(make_gh "$repo" <<GH
case "\$1 \$2" in
    ("repo view") echo 'ERPlora/hub'; exit 0 ;;
    ("auth status") exit 0 ;;
esac
for a in "\$@"; do [ "\$a" = "-X" ] && { printf '%s\n' "\$@" > "$repo/POSTARGS"; exit 0; }; done
for a in "\$@"; do case "\$a" in (repos/*/git/ref/*) echo "$sha"; exit 0 ;; esac; done
exit 0
GH
)
code=$(run_hook "$repo" "refs/heads/x $sha refs/heads/x $ZERO" \
    HUB_GATE_SCOPE_POLICY=scoped HUB_GATE_STATE_DIR="$repo/.state" PATH="$ghdir:$PATH" \
    HUB_GATE_PUSH_POLL_TRIES=2 HUB_GATE_PUSH_POLL_DELAY=0 \
    HUB_GATE_TEST_CMD="true")
sleep 2
args=$(tr '\n' ' ' < "$repo/POSTARGS" 2>/dev/null)
errs=""
[ "$code" = 0 ]                                    || errs="$errs exit=$code(want 0)"
[ -f "$repo/POSTARGS" ]                            || errs="$errs nothing-posted"
grep -q 'context=local-gate/hub-tests-scoped' <<<"$args" || errs="$errs scoped-run-did-not-use-its-own-context"
grep -q 'context=local-gate/hub-tests ' <<<"$args " && errs="$errs scoped-run-claimed-the-full-suite-context"
grep -q -- '--workspace' <<<"$args"                && errs="$errs description-claims-workspace"
grep -q 'toy-c' <<<"$args"                         || errs="$errs description-does-not-name-the-packages"
[ -z "$errs" ] \
    && ok "attestation: a scoped run posts its OWN context and names the packages" \
    || bad "attestation: a scoped run posts its OWN context and names the packages" "$errs args='$args'"

# ── 40b. hub#1451: `scoped` es el DEFECTO fuera de develop/main ──────────────
#
#    Hasta aquí el defecto era `workspace` (29/08, pm#197/hub#1346): Actions dejó de correr la
#    suite en las PRs y `merge-pr.sh` solo aceptaba `local-gate/hub-tests`, así que una pasada
#    acotada dejaba la PR sin poder mergearse. Eso lo cierra pm#230 —el script acepta también
#    `local-gate/hub-tests-scoped`— y con ello el defecto puede volver a ser el alcance.
#
#    La regla es la REF EMPUJADA, no el diff:
#      · una rama de PR  → `scoped`   (el diff decide qué paquetes corren)
#      · develop / main  → `workspace` (post-merge: es el árbol que de verdad se despliega)
#      · un tag, o una ref que no se pudo leer → `workspace` (conservador: una release no se acota)
#    `HUB_GATE_SCOPE_POLICY` sigue forzando los dos modos, que es el escape para depurar.
#
#    Lo que NO cambia y estos casos vigilan: un diff transversal se ensancha igual (el resolutor
#    manda sobre la política), el sello sigue diciendo la verdad de lo que corrió, y un rojo sigue
#    abortando el push.

# Igual que `run_scoped` pero SIN fijar la política: mide el DEFECTO, que es lo que hub#1451
# cambia. La ref empujada es un parámetro porque es justo lo que decide el modo.
run_default_ref() {
    local repo=$1 sha=$2 ref=$3
    shift 3
    rm -f "$repo/SCOPE"
    run_hook "$repo" "$ref $sha $ref $ZERO" \
        HUB_GATE_WITH_MODULES=0 HUB_GATE_STATE_DIR="$repo/.state" HUB_GATE_STATUS_CMD="true" \
        HUB_GATE_TEST_CMD='printf "%s|%s\n" "$HUB_GATE_SCOPE_MODE" "$HUB_GATE_SCOPE_PACKAGES" > '"$repo/SCOPE" \
        "$@"
}

# 40b.1 — una rama de PR corre POR ALCANCE sin que nadie pida nada.
repo=$(make_cargo_repo)
git -C "$repo" config --bool hooks.hubPrepushGate true
sha=$(touch_and_commit "$repo" crates/c/src/lib.rs)
code=$(run_default_ref "$repo" "$sha" refs/heads/fix/1451-algo)
scope=$(cat "$repo/SCOPE" 2>/dev/null)
errs=""
[ "$code" = 0 ]                  || errs="$errs exit=$code(want 0) out=$(tr '\n' ' ' < "$repo/.out" | tail -c 300)"
grep -q '^packages|' <<<"$scope" || errs="$errs default-on-a-PR-branch-is-NOT-scoped"
grep -q 'toy-c' <<<"$scope"      || errs="$errs missing-touched-package"
grep -q 'toy-a' <<<"$scope"      && errs="$errs pulled-in-untouched-toy-a"
[ -z "$errs" ] \
    && ok "hub#1451: por DEFECTO una rama de PR corre por ALCANCE, no el workspace" \
    || bad "hub#1451: por DEFECTO una rama de PR corre por ALCANCE, no el workspace" "$errs scope='$scope'"

# 40b.2 — develop y main NO se acotan: son el árbol que se despliega, y ahí la red completa es
#         el punto, no el coste.
for integration in develop main; do
    repo=$(make_cargo_repo)
    git -C "$repo" config --bool hooks.hubPrepushGate true
    sha=$(touch_and_commit "$repo" crates/c/src/lib.rs)
    code=$(run_default_ref "$repo" "$sha" "refs/heads/$integration")
    scope=$(cat "$repo/SCOPE" 2>/dev/null)
    errs=""
    [ "$code" = 0 ]                   || errs="$errs exit=$code(want 0)"
    grep -q '^workspace|' <<<"$scope" || errs="$errs push-to-$integration-got-scoped"
    [ -z "$errs" ] \
        && ok "hub#1451: un push a $integration corre el WORKSPACE aunque el diff sea de un crate" \
        || bad "hub#1451: un push a $integration corre el WORKSPACE aunque el diff sea de un crate" "$errs scope='$scope'"
done

# 40b.3 — un TAG tampoco. El hub solo se despliega con un tag `v1.1.N`: acotar ahí sería firmar
#         una release con una pasada parcial.
repo=$(make_cargo_repo)
git -C "$repo" config --bool hooks.hubPrepushGate true
sha=$(touch_and_commit "$repo" crates/c/src/lib.rs)
code=$(run_default_ref "$repo" "$sha" refs/tags/v1.1.99)
scope=$(cat "$repo/SCOPE" 2>/dev/null)
errs=""
[ "$code" = 0 ]                   || errs="$errs exit=$code(want 0)"
grep -q '^workspace|' <<<"$scope" || errs="$errs tag-push-got-scoped"
[ -z "$errs" ] \
    && ok "hub#1451: un push de TAG corre el workspace (una release no se acota)" \
    || bad "hub#1451: un push de TAG corre el workspace (una release no se acota)" "$errs scope='$scope'"

# 40b.4 — el escape sigue existiendo en LOS DOS sentidos.
repo=$(make_cargo_repo)
git -C "$repo" config --bool hooks.hubPrepushGate true
sha=$(touch_and_commit "$repo" crates/c/src/lib.rs)
code=$(run_default_ref "$repo" "$sha" refs/heads/fix/x HUB_GATE_SCOPE_POLICY=workspace)
scope=$(cat "$repo/SCOPE" 2>/dev/null)
errs=""
[ "$code" = 0 ]                   || errs="$errs exit=$code(want 0)"
grep -q '^workspace|' <<<"$scope" || errs="$errs env-workspace-did-not-override-the-default"
[ -z "$errs" ] \
    && ok "hub#1451: HUB_GATE_SCOPE_POLICY=workspace fuerza la suite entera en una rama de PR" \
    || bad "hub#1451: HUB_GATE_SCOPE_POLICY=workspace fuerza la suite entera en una rama de PR" "$errs scope='$scope'"

repo=$(make_cargo_repo)
git -C "$repo" config --bool hooks.hubPrepushGate true
sha=$(touch_and_commit "$repo" crates/c/src/lib.rs)
code=$(run_default_ref "$repo" "$sha" refs/heads/develop HUB_GATE_SCOPE_POLICY=scoped)
scope=$(cat "$repo/SCOPE" 2>/dev/null)
errs=""
[ "$code" = 0 ]                  || errs="$errs exit=$code(want 0)"
grep -q '^packages|' <<<"$scope" || errs="$errs env-scoped-did-not-override-on-develop"
[ -z "$errs" ] \
    && ok "hub#1451: HUB_GATE_SCOPE_POLICY=scoped fuerza el alcance incluso en develop" \
    || bad "hub#1451: HUB_GATE_SCOPE_POLICY=scoped fuerza el alcance incluso en develop" "$errs scope='$scope'"

# 40b.5 — EL control que sostiene todo lo demás: el resolutor manda sobre la política. Un diff que
#         toca `schemas/` —el contrato que leen los tests del runtime, o sea las baterías de
#         módulos— se ensancha al workspace ESTANDO en una rama de PR y en modo por defecto.
#         Sin esto, «scoped por defecto» sería una vía para colar un cambio de contrato sin que
#         nadie corriera lo que ese contrato gobierna.
repo=$(make_cargo_repo)
git -C "$repo" config --bool hooks.hubPrepushGate true
sha=$(touch_and_commit "$repo" schemas/module.schema.json)
code=$(run_default_ref "$repo" "$sha" refs/heads/fix/contrato)
scope=$(cat "$repo/SCOPE" 2>/dev/null)
errs=""
[ "$code" = 0 ]                   || errs="$errs exit=$code(want 0)"
grep -q '^workspace|' <<<"$scope" || errs="$errs schemas-diff-stayed-scoped"
[ -z "$errs" ] \
    && ok "hub#1451: tocar schemas/ ESCALA al workspace aun en una rama y en modo por defecto" \
    || bad "hub#1451: tocar schemas/ ESCALA al workspace aun en una rama y en modo por defecto" "$errs scope='$scope'"

# 40b.6 — y un ROJO sigue abortando el push. Un gate más rápido que deja pasar un rojo no es un
#         gate rápido: es ningún gate.
repo=$(make_cargo_repo)
git -C "$repo" config --bool hooks.hubPrepushGate true
sha=$(touch_and_commit "$repo" crates/c/src/lib.rs)
# `false`, no `exit 1`: el hook hace `eval "$test_cmd"`, así que un `exit` se lleva por delante
# al propio hook y el caso mediría otra cosa.
code=$(run_default_ref "$repo" "$sha" refs/heads/fix/rojo HUB_GATE_TEST_CMD="touch $repo/RAN; false")
out=$(cat "$repo/.out" 2>/dev/null)
errs=""
[ "$code" = 1 ]              || errs="$errs exit=$code(want 1)"
[ -f "$repo/RAN" ]           || errs="$errs the-suite-never-ran"
grep -qi 'ABORTED' <<<"$out" || errs="$errs does-not-say-the-push-was-aborted"
[ -z "$errs" ] \
    && ok "hub#1451: en modo por defecto un test ROJO sigue abortando el push" \
    || bad "hub#1451: en modo por defecto un test ROJO sigue abortando el push" "$errs out=$(tr '\n' ' ' <<<"$out" | tail -c 300)"

# 40b.7 — el sello dice la verdad de lo que corrió, en los dos lados del defecto: la rama publica
#         el contexto ACOTADO (el que `merge-pr.sh` acepta desde pm#230) y develop el COMPLETO.
for pair in "refs/heads/fix/sello|local-gate/hub-tests-scoped" "refs/heads/develop|local-gate/hub-tests"; do
    ref=${pair%%|*}; want=${pair##*|}
    repo=$(make_cargo_repo)
    git -C "$repo" config --bool hooks.hubPrepushGate true
    sha=$(touch_and_commit "$repo" crates/c/src/lib.rs)
    ghdir=$(make_gh "$repo" <<GH
case "\$1 \$2" in
    ("repo view") echo 'ERPlora/hub'; exit 0 ;;
    ("auth status") exit 0 ;;
esac
for a in "\$@"; do [ "\$a" = "-X" ] && { printf '%s\n' "\$@" > "$repo/POSTARGS"; exit 0; }; done
for a in "\$@"; do case "\$a" in (repos/*/git/ref/*) echo "$sha"; exit 0 ;; esac; done
exit 0
GH
)
    code=$(run_hook "$repo" "$ref $sha $ref $ZERO" \
        HUB_GATE_WITH_MODULES=0 HUB_GATE_STATE_DIR="$repo/.state" PATH="$ghdir:$PATH" \
        HUB_GATE_PUSH_POLL_TRIES=2 HUB_GATE_PUSH_POLL_DELAY=0 \
        HUB_GATE_TEST_CMD="true")
    sleep 2
    args=$(tr '\n' ' ' < "$repo/POSTARGS" 2>/dev/null)
    errs=""
    [ "$code" = 0 ]                          || errs="$errs exit=$code(want 0)"
    grep -q "context=$want" <<<"$args"       || errs="$errs did-not-post-$want"
    if [ "$want" = local-gate/hub-tests ]; then
        grep -q -- '--workspace' <<<"$args"  || errs="$errs full-run-does-not-claim-workspace"
    else
        grep -q -- '--workspace' <<<"$args"  && errs="$errs scoped-run-claims-workspace"
        grep -q 'context=local-gate/hub-tests ' <<<"$args " && errs="$errs scoped-run-claimed-the-full-context"
    fi
    [ -z "$errs" ] \
        && ok "hub#1451: el sello por defecto de $ref es $want" \
        || bad "hub#1451: el sello por defecto de $ref es $want" "$errs args='$args'"
done

# ── 41. A real full-workspace run keeps the full-suite context and wording ────
repo=$(make_cargo_repo)
git -C "$repo" config --bool hooks.hubPrepushGate true
sha=$(touch_and_commit "$repo" Cargo.lock)
ghdir=$(make_gh "$repo" <<GH
case "\$1 \$2" in
    ("repo view") echo 'ERPlora/hub'; exit 0 ;;
    ("auth status") exit 0 ;;
esac
for a in "\$@"; do [ "\$a" = "-X" ] && { printf '%s\n' "\$@" > "$repo/POSTARGS"; exit 0; }; done
for a in "\$@"; do case "\$a" in (repos/*/git/ref/*) echo "$sha"; exit 0 ;; esac; done
exit 0
GH
)
code=$(run_hook "$repo" "refs/heads/x $sha refs/heads/x $ZERO" \
    HUB_GATE_STATE_DIR="$repo/.state" PATH="$ghdir:$PATH" \
    HUB_GATE_PUSH_POLL_TRIES=2 HUB_GATE_PUSH_POLL_DELAY=0 \
    HUB_GATE_TEST_CMD="true")
sleep 2
args=$(tr '\n' ' ' < "$repo/POSTARGS" 2>/dev/null)
errs=""
[ "$code" = 0 ]                                     || errs="$errs exit=$code(want 0)"
grep -q 'context=local-gate/hub-tests ' <<<"$args " || errs="$errs full-run-lost-the-full-suite-context"
grep -q -- '--workspace' <<<"$args"                 || errs="$errs full-run-stopped-claiming-workspace"
[ -z "$errs" ] \
    && ok "attestation: a real workspace run keeps local-gate/hub-tests and its wording" \
    || bad "attestation: a real workspace run keeps local-gate/hub-tests and its wording" "$errs args='$args'"

# ── 42. The LOCK STAYS on a scoped run (hub#526 is not repealed) ──────────────
#    The win is holding it for minutes instead of forty. Two suites at once
#    still melt the machine, so a scoped run must serialize like any other.
repo=$(make_cargo_repo)
git -C "$repo" config --bool hooks.hubPrepushGate true
sha=$(touch_and_commit "$repo" crates/c/src/lib.rs)
code=$(run_hook "$repo" "refs/heads/x $sha refs/heads/x $ZERO" \
    HUB_GATE_WITH_MODULES=0 HUB_GATE_STATE_DIR="$repo/.state" HUB_GATE_STATUS_CMD="true" \
    HUB_GATE_TEST_CMD="[ -d '$repo/.state/lock' ] && touch $repo/RAN")
errs=""
[ "$code" = 0 ]           || errs="$errs exit=$code(want 0)"
[ -f "$repo/RAN" ]        || errs="$errs scoped-run-did-NOT-hold-the-lock"
[ ! -d "$repo/.state/lock" ] || errs="$errs lock-not-released"
[ -z "$errs" ] \
    && ok "lock: a scoped run still takes it, and releases it" \
    || bad "lock: a scoped run still takes it, and releases it" "$errs"

# ── 43. The green cache is keyed by SCOPE, not by tree alone ──────────────────
#    The same commit can be pushed against different bases — a rebase onto a
#    develop that moved, a re-push after the integration branch advanced — and
#    the WIDER diff resolves to a WIDER scope. Reusing the narrow green there
#    would mark packages green that nothing ever ran.
repo=$(make_cargo_repo)
git -C "$repo" config --bool hooks.hubPrepushGate true
first_commit=$(git -C "$repo" rev-parse HEAD)
touch_and_commit "$repo" crates/a/src/lib.rs >/dev/null
mid=$(git -C "$repo" rev-parse HEAD)
sha=$(touch_and_commit "$repo" crates/c/src/lib.rs)
# Base = the commit just before: only crates/c is new → the narrow scope.
git -C "$repo" update-ref refs/remotes/origin/develop "$mid"
run_scoped "$repo" "$sha" >/dev/null
first=$(cat "$repo/SCOPE" 2>/dev/null)
# Same sha, same tree, base rewound: crates/a is in the diff too → wider scope.
git -C "$repo" update-ref refs/remotes/origin/develop "$first_commit"
rm -f "$repo/SCOPE"
code=$(run_scoped "$repo" "$sha")
second=$(cat "$repo/SCOPE" 2>/dev/null)
errs=""
[ "$code" = 0 ]                    || errs="$errs exit=$code(want 0)"
grep -q 'toy-c' <<<"$first"        || errs="$errs first-run-scope-unexpected"
grep -q 'toy-a' <<<"$first"        && errs="$errs first-run-was-not-narrow"
[ -f "$repo/SCOPE" ]               || errs="$errs the-wider-scope-reused-the-narrow-cached-green"
# Widened means either toy-a joined the list or the diff now reaches every
# testable package, which this toy workspace does with two crates out of three.
case "$second" in
    workspace*|*toy-a*) ;;
    *) errs="$errs second-run-did-not-widen" ;;
esac
[ -z "$errs" ] \
    && ok "cache: a green recorded for one scope is not reused for a wider one" \
    || bad "cache: a green recorded for one scope is not reused for a wider one" "$errs first='$first' second='$second'"

# ── 44. The installed hook RESYNCS ITSELF (hub#746 → hub#1207) ────────────────
#    Warning about drift was not enough: the fleet ran a 13/08 copy for two
#    weeks, so a change to `.githooks/pre-push` changed nothing in practice.
#    When the diff being pushed does NOT touch the hook, the stale installed
#    copy is replaced by the repo's and re-executed — once (HUB_GATE_RESYNCED).
repo=$(make_cargo_repo)
git -C "$repo" config --bool hooks.hubPrepushGate true
mkdir -p "$repo/.githooks"
cp "$HOOK" "$repo/.githooks/pre-push"
git -C "$repo" add -A && git -C "$repo" commit -qm "vendor the hook"
git -C "$repo" update-ref refs/remotes/origin/develop HEAD
mkdir -p "$repo/installed"
cp "$HOOK" "$repo/installed/pre-push"
echo "# stale installed copy" >> "$repo/installed/pre-push"
chmod +x "$repo/installed/pre-push"
sha=$(touch_and_commit "$repo" crates/c/src/lib.rs)
( cd "$repo" && printf '%s\n' "refs/heads/x $sha refs/heads/x $ZERO" | env \
    HUB_GATE_WITH_MODULES=0 HUB_GATE_STATE_DIR="$repo/.state" HUB_GATE_STATUS_CMD="true" \
    HUB_GATE_DEPTH=full HUB_GATE_TEST_CMD="touch $repo/RAN" \
    bash "$repo/installed/pre-push" ) >"$repo/.out" 2>&1
code=$?
out=$(cat "$repo/.out" 2>/dev/null)
errs=""
[ "$code" = 0 ]                                              || errs="$errs exit=$code(want 0)"
cmp -s "$repo/installed/pre-push" "$repo/.githooks/pre-push" || errs="$errs installed-copy-was-NOT-resynced"
[ -f "$repo/RAN" ]                                           || errs="$errs suite-did-not-run-after-resync"
grep -qi 'resync' <<<"$out"                                  || errs="$errs silent-resync"
[ -z "$errs" ] \
    && ok "drift: a stale installed hook resyncs itself and re-runs the push" \
    || bad "drift: a stale installed hook resyncs itself and re-runs the push" "$errs out=$(tr '\n' ' ' <<<"$out" | tail -c 300)"

# ── 45. A branch that EDITS the hook is never auto-installed fleet-wide ───────
#    Self-healing must not turn "I am testing a change to the gate" into
#    "every worktree on this machine now runs my branch's gate".
repo=$(make_cargo_repo)
git -C "$repo" config --bool hooks.hubPrepushGate true
mkdir -p "$repo/.githooks"
cp "$HOOK" "$repo/.githooks/pre-push"
git -C "$repo" add -A && git -C "$repo" commit -qm "vendor the hook"
git -C "$repo" update-ref refs/remotes/origin/develop HEAD
mkdir -p "$repo/installed"
cp "$HOOK" "$repo/installed/pre-push"
chmod +x "$repo/installed/pre-push"
echo "# a change to the gate itself" >> "$repo/.githooks/pre-push"
git -C "$repo" add -A && git -C "$repo" commit -qm "edit the gate"
sha=$(git -C "$repo" rev-parse HEAD)
( cd "$repo" && printf '%s\n' "refs/heads/x $sha refs/heads/x $ZERO" | env \
    HUB_GATE_WITH_MODULES=0 HUB_GATE_STATE_DIR="$repo/.state" HUB_GATE_STATUS_CMD="true" \
    HUB_GATE_TEST_CMD="true" \
    bash "$repo/installed/pre-push" ) >"$repo/.out" 2>&1
code=$?
out=$(cat "$repo/.out" 2>/dev/null)
errs=""
[ "$code" = 0 ]                                               || errs="$errs exit=$code(want 0)"
cmp -s "$repo/installed/pre-push" "$repo/.githooks/pre-push"  && errs="$errs branch-hook-got-installed-machine-wide"
grep -qi 'out of sync' <<<"$out"                              || errs="$errs no-drift-warning"
[ -z "$errs" ] \
    && ok "drift: a branch editing the gate warns instead of installing itself" \
    || bad "drift: a branch editing the gate warns instead of installing itself" "$errs"

# ── 46. A worktree based on an OLDER develop must NOT downgrade the hook ──────
#    The branch does not touch the gate, but its CHECKOUT carries the older
#    committed copy. Installing that would revert the fleet's gate on day one
#    (every in-flight branch is based on a pre-upgrade develop) — and a copy
#    with no self-heal cannot resync itself back, so the downgrade would be
#    sticky until a human reruns install-hooks.sh. The canonical source is the
#    INTEGRATION ref's blob, never the checkout.
repo=$(make_cargo_repo)
git -C "$repo" config --bool hooks.hubPrepushGate true
mkdir -p "$repo/.githooks"
printf '%s\n' '#!/usr/bin/env bash' '# ancient gate: no self-heal here' 'exit 0' > "$repo/.githooks/pre-push"
chmod +x "$repo/.githooks/pre-push"
git -C "$repo" add -A && git -C "$repo" commit -qm "vendor the OLD hook"
old_base=$(git -C "$repo" rev-parse HEAD)
cp "$HOOK" "$repo/.githooks/pre-push"
git -C "$repo" add -A && git -C "$repo" commit -qm "upgrade the gate"
git -C "$repo" update-ref refs/remotes/origin/develop HEAD
git -C "$repo" checkout -q "$old_base"
git -C "$repo" checkout -qb feature
sha=$(touch_and_commit "$repo" crates/c/src/lib.rs)
mkdir -p "$repo/installed"
cp "$HOOK" "$repo/installed/pre-push"
chmod +x "$repo/installed/pre-push"
( cd "$repo" && printf '%s\n' "refs/heads/feature $sha refs/heads/feature $ZERO" | env \
    HUB_GATE_WITH_MODULES=0 HUB_GATE_STATE_DIR="$repo/.state" HUB_GATE_STATUS_CMD="true" \
    HUB_GATE_TEST_CMD="true" \
    bash "$repo/installed/pre-push" ) >"$repo/.out" 2>&1
code=$?
errs=""
[ "$code" = 0 ]                              || errs="$errs exit=$code(want 0)"
cmp -s "$repo/installed/pre-push" "$HOOK"    || errs="$errs installed-hook-DOWNGRADED-by-an-older-checkout"
[ -z "$errs" ] \
    && ok "drift: a worktree based on an older develop cannot downgrade the installed hook" \
    || bad "drift: a worktree based on an older develop cannot downgrade the installed hook" "$errs out=$(tr '\n' ' ' < "$repo/.out" | tail -c 300)"

# ── 47. An UNCOMMITTED edit to the gate is never installed machine-wide ───────
#    It is in no diff, so a diff-based guard cannot see it. The resync must
#    still fire (the installed copy IS stale) but from the integration ref's
#    committed blob — never from the file someone is editing right now.
repo=$(make_cargo_repo)
git -C "$repo" config --bool hooks.hubPrepushGate true
mkdir -p "$repo/.githooks"
cp "$HOOK" "$repo/.githooks/pre-push"
git -C "$repo" add -A && git -C "$repo" commit -qm "vendor the hook"
git -C "$repo" update-ref refs/remotes/origin/develop HEAD
mkdir -p "$repo/installed"
cp "$HOOK" "$repo/installed/pre-push"
echo "# stale installed copy" >> "$repo/installed/pre-push"
chmod +x "$repo/installed/pre-push"
sha=$(touch_and_commit "$repo" crates/c/src/lib.rs)
echo "# WIP uncommitted edit" >> "$repo/.githooks/pre-push"
( cd "$repo" && printf '%s\n' "refs/heads/x $sha refs/heads/x $ZERO" | env \
    HUB_GATE_WITH_MODULES=0 HUB_GATE_STATE_DIR="$repo/.state" HUB_GATE_STATUS_CMD="true" \
    HUB_GATE_DEPTH=full HUB_GATE_TEST_CMD="touch $repo/RAN" \
    bash "$repo/installed/pre-push" ) >"$repo/.out" 2>&1
code=$?
errs=""
# The push itself is REFUSED — the dirty .githooks/pre-push trips the hub#855
# clean-tree guard, which is the correct fail-closed answer for that worktree.
# The property under test is the machine-wide one: the WIP edit never becomes
# the installed hook.
[ "$code" = 0 ] && errs="$errs dirty-tree-push-was-not-refused"
grep -q 'WIP uncommitted edit' "$repo/installed/pre-push" && errs="$errs uncommitted-edit-installed-machine-wide"
cmp -s "$repo/installed/pre-push" "$HOOK"              || errs="$errs installed-copy-is-not-the-committed-blob"
[ -f "$repo/RAN" ]                                     && errs="$errs suite-ran-on-a-dirty-tree"
[ -z "$errs" ] \
    && ok "drift: an uncommitted edit to the gate is never installed — resync uses the committed blob" \
    || bad "drift: an uncommitted edit to the gate is never installed — resync uses the committed blob" "$errs out=$(tr '\n' ' ' < "$repo/.out" | tail -c 300)"

# ── 48. Never install a copy that cannot heal itself (stale-fetch downgrade) ──
#    If origin/develop itself is stale (a worktree that has not fetched since
#    before the self-heal shipped), its blob has no resync. Installing it would
#    strand the whole machine on a gate that can only warn — refuse instead.
repo=$(make_cargo_repo)
git -C "$repo" config --bool hooks.hubPrepushGate true
mkdir -p "$repo/.githooks"
printf '%s\n' '#!/usr/bin/env bash' '# ancient gate: no self-heal here' 'exit 0' > "$repo/.githooks/pre-push"
chmod +x "$repo/.githooks/pre-push"
git -C "$repo" add -A && git -C "$repo" commit -qm "vendor the OLD hook"
git -C "$repo" update-ref refs/remotes/origin/develop HEAD
sha=$(touch_and_commit "$repo" crates/c/src/lib.rs)
mkdir -p "$repo/installed"
cp "$HOOK" "$repo/installed/pre-push"
chmod +x "$repo/installed/pre-push"
( cd "$repo" && printf '%s\n' "refs/heads/x $sha refs/heads/x $ZERO" | env \
    HUB_GATE_WITH_MODULES=0 HUB_GATE_STATE_DIR="$repo/.state" HUB_GATE_STATUS_CMD="true" \
    HUB_GATE_DEPTH=full HUB_GATE_TEST_CMD="touch $repo/RAN" \
    bash "$repo/installed/pre-push" ) >"$repo/.out" 2>&1
code=$?
errs=""
[ "$code" = 0 ]                           || errs="$errs exit=$code(want 0)"
cmp -s "$repo/installed/pre-push" "$HOOK" || errs="$errs installed-hook-replaced-by-a-copy-with-no-self-heal"
[ -f "$repo/RAN" ]                        || errs="$errs suite-did-not-run"
[ -z "$errs" ] \
    && ok "drift: a canonical copy with no self-heal is refused (no sticky downgrade)" \
    || bad "drift: a canonical copy with no self-heal is refused (no sticky downgrade)" "$errs out=$(tr '\n' ' ' < "$repo/.out" | tail -c 300)"

# ── Web stage: `pnpm verify` + playwright corren AQUÍ, no en la nube ──────────
#    Decisión de Ioan (2026-08-29): `cargo test --workspace` + e2e + web + playwright
#    se ejecutan en LOCAL en cada PR y NO en Actions; si no pasan, la rama no se
#    empuja y por tanto no hay PR. Antes de esto el gate era solo Rust, así que un
#    cambio de `apps/web/**` salía sin que nadie lo probara.

# 1. Un diff SOLO de web: el alcance Rust es `none` y aun así el gate DEBE correr web.
repo=$(make_cargo_repo)
git -C "$repo" config --bool hooks.hubPrepushGate true
sha=$(touch_and_commit "$repo" apps/web/src/App.vue)
code=$(run_hook "$repo" "refs/heads/x $sha refs/heads/x $ZERO" \
    HUB_GATE_WITH_MODULES=0 HUB_GATE_STATE_DIR="$repo/.state" HUB_GATE_STATUS_CMD="true" \
    HUB_GATE_TEST_CMD="touch $repo/RAN; true" \
    HUB_GATE_WEB_CMD="touch $repo/WEBSTAGE; true")
errs=""
[ "$code" = 0 ]       || errs="$errs exit=$code(want 0)"
[ -f "$repo/WEBSTAGE" ]    || errs="$errs web-stage-did-not-run"
[ -z "$errs" ] \
    && ok "web: un diff solo de apps/web corre la etapa web aunque no haya Rust" \
    || bad "web: un diff solo de apps/web corre la etapa web aunque no haya Rust" "$errs out=$(tr '\n' ' ' < "$repo/.out" | tail -c 300)"

# 1b. …y con el comando web FIJADO no toca docker NI Postgres (hub#1368).
#     El banco de e2e (`hub_e2e_web`/`hub_e2e_assistant`) es dependencia del comando POR
#     DEFECTO —playwright contra el runtime—, no de quien trae el suyo. Prepararlo igualmente
#     exigía un `erplora-test-pg-5433` vivo: en la CI del propio gate el caso de arriba murió
#     con «no pude crear la base 'hub_e2e_web'» (76/77, run 33564975392) y en el Mac salía
#     verde SOLO porque el contenedor estaba ahí — el rojo dependía de la máquina, no del
#     código. Este control no: `docker` se stubbea y basta con que el hook lo LLAME para
#     ponerse rojo, haya contenedor o no. `DATABASE_URL=` vacío a propósito: heredada del
#     entorno, `ensure_postgres` volvería por la puerta de arriba y escondería la mitad del
#     defecto. El stub escribe FUERA del repo: dentro ensuciaría el árbol (guardia hub#855),
#     y el registro NO se puede llamar `DOCKER`: el disco del Mac es insensible a mayúsculas,
#     así que el stub se escribiría encima de sí mismo y el caso saldría rojo siempre.
repo=$(make_cargo_repo)
git -C "$repo" config --bool hooks.hubPrepushGate true
sha=$(touch_and_commit "$repo" apps/web/src/App.vue)
dockerbin="${repo}-nodocker"; mkdir -p "$dockerbin"
printf '#!/bin/sh\nprintf "%%s\\n" "$*" >> "%s/calls.log"\nexit 0\n' "$dockerbin" > "$dockerbin/docker"
chmod +x "$dockerbin/docker"
code=$(run_hook "$repo" "refs/heads/x $sha refs/heads/x $ZERO" \
    HUB_GATE_WITH_MODULES=0 HUB_GATE_STATE_DIR="$repo/.state" HUB_GATE_STATUS_CMD="true" \
    PATH="$dockerbin:$PATH" DATABASE_URL= \
    HUB_GATE_TEST_CMD="true" \
    HUB_GATE_WEB_CMD="touch $repo/WEBSTAGE; true")
errs=""
[ "$code" = 0 ]                 || errs="$errs exit=$code(want 0)"
[ -f "$repo/WEBSTAGE" ]         || errs="$errs web-stage-did-not-run"
[ ! -f "$dockerbin/calls.log" ] || errs="$errs toco-docker=$(tr '\n' '|' < "$dockerbin/calls.log" | tail -c 200)"
[ -z "$errs" ] \
    && ok "web: con el comando web fijado el gate no toca docker ni el banco de e2e" \
    || bad "web: con el comando web fijado el gate no toca docker ni el banco de e2e" "$errs out=$(tr '\n' ' ' < "$repo/.out" | tail -c 300)"

# 1c. hub#2259 / rv-2265 — la etapa web POR DEFECTO prueba la OutfitKit de producción, no el pin.
#     `test-web.yml` y el Dockerfile instalan `@erplora/outfitkit@latest`; el gate instalaba solo
#     el lockfile, así que tras cada release de OutfitKit (13 el 26/09) la guarda del banco
#     (`apps/web/tests/outfitkit-latest-guard.ts`) habría abortado TODO push web de la flota hasta
#     que cada rama subiera su pin — y todas chocarían en `pnpm-lock.yaml`. El gate hace lo mismo que
#     la CI y deja `package.json` + `pnpm-lock.yaml` como estaban, en verde Y en rojo: el árbol del
#     worker no se ensucia (la guardia hub#855 compara el árbol con lo empujado). `pnpm`/`cargo` son
#     stubs FUERA del repo; el de `pnpm add` escribe en los dos ficheros como el de verdad.
web_default_repo() {
    local repo
    repo=$(make_cargo_repo)
    git -C "$repo" config --bool hooks.hubPrepushGate true
    mkdir -p "$repo/apps/web"
    printf '{ "dependencies": { "@erplora/outfitkit": "^0.1.84" } }\n' > "$repo/apps/web/package.json"
    printf "'@erplora/outfitkit@0.1.84': {}\n" > "$repo/pnpm-lock.yaml"
    git -C "$repo" add apps/web/package.json pnpm-lock.yaml
    git -C "$repo" commit -qm pin
    echo "$repo"
}
web_default_stubs() {
    local bin=$1 e2e_rc=$2
    mkdir -p "$bin"
    cat > "$bin/pnpm" <<STUB
#!/bin/sh
printf '%s\n' "\$*" >> "$bin/calls.log"
case "\$*" in
    *"add @erplora/outfitkit@latest"*)
        echo latest >> apps/web/package.json; echo latest >> pnpm-lock.yaml ;;
    *test:e2e*)
        grep -q latest apps/web/package.json && echo "e2e-saw-latest" >> "$bin/calls.log"
        # "kill": the hook dies mid-playwright (Ctrl-C, the fleet's timeout) — our parent is it.
        [ "$e2e_rc" = kill ] && { kill -TERM "\$PPID"; sleep 1; exit 1; }
        exit $e2e_rc ;;
esac
exit 0
STUB
    # `cargo metadata` is the real one: the gate needs it to see that a web-only diff has no Rust
    # (the path that runs the web stage BEFORE the lock and its EXIT trap exist).
    printf '#!/bin/sh\n[ "$1" = metadata ] && exec "%s" "$@"\nexit 0\n' "$REAL_CARGO" > "$bin/cargo"
    chmod +x "$bin/pnpm" "$bin/cargo"
}
REAL_CARGO=$(command -v cargo)
# Two paths reach the web stage and each restores the pin through its own EXIT trap: a web-only
# diff (no Rust → web stage before the lock) and a diff that runs the Hub suite (web stage after
# the lock, whose trap replaces the early one).
for path in web-only suite; do
for e2e_rc in 0 1 kill; do
    repo=$(web_default_repo)
    sha=$(touch_and_commit "$repo" apps/web/src/App.vue)
    bin="${repo}-webbin"
    web_default_stubs "$bin" "$e2e_rc"
    scope_env=HUB_GATE_SCOPE_POLICY=scoped
    [ "$path" = suite ] && scope_env=HUB_GATE_SCOPE=workspace
    code=$(run_hook "$repo" "refs/heads/x $sha refs/heads/x $ZERO" \
        HUB_GATE_WITH_MODULES=0 HUB_GATE_STATE_DIR="$repo/.state" HUB_GATE_STATUS_CMD="true" \
        PATH="$bin:$PATH" DATABASE_URL=postgres://stub HUB_GATE_E2E_DB_CMD=true \
        HUB_GATE_TEST_CMD="true" "$scope_env")
    add_line=$(grep -m1 -n -- '--filter @erplora/web add @erplora/outfitkit@latest' "$bin/calls.log" 2>/dev/null | cut -d: -f1)
    install_line=$(grep -m1 -n -- 'install --frozen-lockfile' "$bin/calls.log" 2>/dev/null | cut -d: -f1)
    verify_line=$(grep -m1 -nx -- 'verify' "$bin/calls.log" 2>/dev/null | cut -d: -f1)
    e2e_line=$(grep -m1 -n -- 'test:e2e' "$bin/calls.log" 2>/dev/null | cut -d: -f1)
    errs=""
    if [ "$e2e_rc" = 0 ]; then
        [ "$code" = 0 ] || errs="$errs exit=$code(want 0)"
        label="web ($path): la etapa por defecto prueba OutfitKit @latest como la CI y deja el pin como estaba (hub#2259)"
    elif [ "$e2e_rc" = 1 ]; then
        [ "$code" != 0 ] || errs="$errs exit=0(want red)"
        label="web ($path): con playwright en rojo el pin de OutfitKit también se restaura (hub#2259)"
    else
        [ "$code" != 0 ] || errs="$errs exit=0(want killed)"
        label="web ($path): si matan el gate a mitad de playwright el pin de OutfitKit también se restaura (hub#2259)"
    fi
    if [ "$path" = web-only ]; then
        grep -q 'no Rust in this diff' "$repo/.out" || errs="$errs did-not-take-the-no-rust-path"
    else
        grep -q 'running the whole Hub suite' "$repo/.out" || errs="$errs did-not-take-the-suite-path"
    fi
    [ -n "$add_line" ] || errs="$errs no-outfitkit-latest-step"
    [ -n "$add_line" ] && [ -n "$install_line" ] && [ "$install_line" -lt "$add_line" ] \
        || errs="$errs latest-not-after-install"
    # Same order as test-web.yml: vue-tsc + vitest run on @latest too, not only playwright.
    [ -n "$add_line" ] && [ -n "$verify_line" ] && [ "$add_line" -lt "$verify_line" ] \
        || errs="$errs latest-not-before-verify"
    [ -n "$add_line" ] && [ -n "$e2e_line" ] && [ "$add_line" -lt "$e2e_line" ] \
        || errs="$errs latest-not-before-e2e"
    grep -q e2e-saw-latest "$bin/calls.log" 2>/dev/null || errs="$errs e2e-ran-on-the-pin"
    git -C "$repo" diff --quiet -- apps/web/package.json pnpm-lock.yaml \
        || errs="$errs pin-left-modified=$(git -C "$repo" diff --stat | tr '\n' ' ')"
    [ -z "$errs" ] \
        && ok "$label" \
        || bad "$label" "$errs calls=$(tr '\n' '|' < "$bin/calls.log" 2>/dev/null) out=$(tr '\n' ' ' < "$repo/.out" | tail -c 300)"
done
done
# A pin file that did not exist before the `add` does not exist after it either: the tree stays
# the pushed tree (hub#855), not one with an untracked lockfile the worker never wrote.
repo=$(web_default_repo)
git -C "$repo" rm -q pnpm-lock.yaml
git -C "$repo" commit -qm "no lockfile"
sha=$(touch_and_commit "$repo" apps/web/src/App.vue)
bin="${repo}-webbin"
web_default_stubs "$bin" 0
code=$(run_hook "$repo" "refs/heads/x $sha refs/heads/x $ZERO" \
    HUB_GATE_WITH_MODULES=0 HUB_GATE_STATE_DIR="$repo/.state" HUB_GATE_STATUS_CMD="true" \
    PATH="$bin:$PATH" DATABASE_URL=postgres://stub HUB_GATE_E2E_DB_CMD=true \
    HUB_GATE_TEST_CMD="true")
errs=""
[ "$code" = 0 ] || errs="$errs exit=$code(want 0)"
grep -q e2e-saw-latest "$bin/calls.log" 2>/dev/null || errs="$errs e2e-ran-on-the-pin"
[ ! -e "$repo/pnpm-lock.yaml" ] || errs="$errs lockfile-created-by-the-add-left-behind"
git -C "$repo" diff --quiet -- apps/web/package.json || errs="$errs package-json-left-modified"
[ -z "$errs" ] \
    && ok "web: un fichero del pin que no existía antes del add @latest no queda después (hub#2259)" \
    || bad "web: un fichero del pin que no existía antes del add @latest no queda después (hub#2259)" "$errs out=$(tr '\n' ' ' < "$repo/.out" | tail -c 300)"

# 2. Web en rojo = push ABORTADO (sin push no hay PR: es la puerta que pidió Ioan).
repo=$(make_cargo_repo)
git -C "$repo" config --bool hooks.hubPrepushGate true
sha=$(touch_and_commit "$repo" apps/web/src/App.vue)
code=$(run_hook "$repo" "refs/heads/x $sha refs/heads/x $ZERO" \
    HUB_GATE_WITH_MODULES=0 HUB_GATE_STATE_DIR="$repo/.state" HUB_GATE_STATUS_CMD="true" \
    HUB_GATE_TEST_CMD="true" \
    HUB_GATE_WEB_CMD="false")
[ "$code" != 0 ] \
    && ok "web: si la etapa web falla, el push se aborta" \
    || bad "web: si la etapa web falla, el push se aborta" "exit=$code"

# 3. Un diff sin web no paga la etapa web (los ~6 min de pnpm+playwright).
repo=$(make_cargo_repo)
git -C "$repo" config --bool hooks.hubPrepushGate true
sha=$(touch_and_commit "$repo" crates/a/src/lib.rs)
code=$(run_hook "$repo" "refs/heads/x $sha refs/heads/x $ZERO" \
    HUB_GATE_WITH_MODULES=0 HUB_GATE_STATE_DIR="$repo/.state" HUB_GATE_STATUS_CMD="true" \
    HUB_GATE_TEST_CMD="true" \
    HUB_GATE_WEB_CMD="touch $repo/WEBSTAGE; true")
errs=""
[ "$code" = 0 ]        || errs="$errs exit=$code(want 0)"
[ ! -f "$repo/WEBSTAGE" ]   || errs="$errs web-stage-ran-for-a-rust-only-diff"
[ -z "$errs" ] \
    && ok "web: un diff sin web no corre la etapa web" \
    || bad "web: un diff sin web no corre la etapa web" "$errs"

# 4. Ni Rust ni web: no se corre nada y el push pasa (un .md no paga 25 min).
repo=$(make_cargo_repo)
git -C "$repo" config --bool hooks.hubPrepushGate true
sha=$(touch_and_commit "$repo" docs/nota.md)
code=$(run_hook "$repo" "refs/heads/x $sha refs/heads/x $ZERO" \
    HUB_GATE_WITH_MODULES=0 HUB_GATE_STATE_DIR="$repo/.state" HUB_GATE_STATUS_CMD="true" \
    HUB_GATE_TEST_CMD="touch $repo/RAN; true" \
    HUB_GATE_WEB_CMD="touch $repo/WEBSTAGE; true")
errs=""
[ "$code" = 0 ]      || errs="$errs exit=$code(want 0)"
[ ! -f "$repo/RAN" ] || errs="$errs rust-ran-for-a-docs-only-diff"
[ ! -f "$repo/WEBSTAGE" ] || errs="$errs web-ran-for-a-docs-only-diff"
[ -z "$errs" ] \
    && ok "web: un diff de solo documentacion no corre nada" \
    || bad "web: un diff de solo documentacion no corre nada" "$errs"

# 5. Politica por defecto = la que dicta la REF (hub#1451). Este caso decia lo contrario —«por
#    defecto una PR con Rust corre el WORKSPACE entero»— y era correcto con SU premisa: el 29/08
#    (pm#197) Actions dejo de correr la suite en las PRs y `merge-pr.sh` solo aceptaba
#    `local-gate/hub-tests`, asi que una pasada acotada dejaba la PR inmergeable. pm#230 acepta
#    tambien `local-gate/hub-tests-scoped`, la premisa cae, y con ella este contrato: se REESCRIBE
#    a proposito, no se ajusta al codigo. El desglose completo de la regla nueva —develop/main,
#    tags, los dos escapes, la escalada por `schemas/`— esta en el bloque 40b.
repo=$(make_cargo_repo)
git -C "$repo" config --bool hooks.hubPrepushGate true
sha=$(touch_and_commit "$repo" crates/a/src/lib.rs)
rm -f "$repo/SCOPE"
code=$(run_hook "$repo" "refs/heads/x $sha refs/heads/x $ZERO" \
    HUB_GATE_WITH_MODULES=0 HUB_GATE_STATE_DIR="$repo/.state" HUB_GATE_STATUS_CMD="true" \
    HUB_GATE_TEST_CMD='printf "%s\n" "$HUB_GATE_SCOPE_MODE" > '"$repo/SCOPE")
errs=""
[ "$code" = 0 ] || errs="$errs exit=$code(want 0)"
[ "$(cat "$repo/SCOPE" 2>/dev/null)" = packages ] \
    || errs="$errs mode=$(cat "$repo/SCOPE" 2>/dev/null)(want packages)"
[ -z "$errs" ] \
    && ok "politica: por defecto una rama de PR corre por ALCANCE (hub#1451 enmienda pm#197)" \
    || bad "politica: por defecto una rama de PR corre por ALCANCE (hub#1451 enmienda pm#197)" "$errs"

# 6. Sin base contra la que diffear no se sabe que toca el cambio: para Rust ya se ensancha al
#    workspace, y para web hay que ser igual de conservador o el diff se cuela sin probar.
repo=$(make_cargo_repo)
git -C "$repo" config --bool hooks.hubPrepushGate true
# El repo TIENE web (como el hub): sin base para el diff, la etapa web debe correr igualmente.
mkdir -p "$repo/apps/web/src"; echo '{}' > "$repo/package.json"
git -C "$repo" add -A && git -C "$repo" commit -qm "web workspace"
git -C "$repo" update-ref -d refs/remotes/origin/develop 2>/dev/null || true
git -C "$repo" update-ref -d refs/remotes/origin/main 2>/dev/null || true
sha=$(touch_and_commit "$repo" crates/a/src/lib.rs)
code=$(run_hook "$repo" "refs/heads/x $sha refs/heads/x $ZERO" \
    HUB_GATE_WITH_MODULES=0 HUB_GATE_STATE_DIR="$repo/.state" HUB_GATE_STATUS_CMD="true" \
    HUB_GATE_TEST_CMD="true" \
    HUB_GATE_WEB_CMD="touch $repo/WEBSTAGE; true")
errs=""
[ "$code" = 0 ]            || errs="$errs exit=$code(want 0)"
[ -f "$repo/WEBSTAGE" ]    || errs="$errs web-stage-skipped-with-no-base-to-diff"
[ -z "$errs" ] \
    && ok "web: sin base para el diff se corre la etapa web igualmente (conservador)" \
    || bad "web: sin base para el diff se corre la etapa web igualmente (conservador)" "$errs"

# 7. Saltarse la etapa web NO puede dejar una atestacion: `merge-pr.sh` autoriza el merge con
#    ella, asi que atestiguar lo que no se ha corrido seria firmar en falso. Se usa el `gh` falso
#    (make_gh) porque el status solo se publica tras verificar el ref en origin.
attest_case() { # <SKIP_HUB_WEB 0|1> -> imprime los args del status publicado (vacio si no hubo)
    local skip=$1 repo ghdir sha
    repo=$(make_cargo_repo)
    git -C "$repo" config --bool hooks.hubPrepushGate true
    touch_and_commit "$repo" crates/c/src/lib.rs >/dev/null   # Rust: es lo que se atestigua
    sha=$(touch_and_commit "$repo" apps/web/src/App.vue)      # y web: es lo que se puede saltar
    # `>>`, no `>`: desde pm#198 un diff con Rust Y web publica DOS sellos, y con `>` el segundo
    # borraba al primero — el control de abajo («corriendo todo SÍ atestigua») se caía sin que
    # nada estuviera roto. Se acumulan, y las aserciones buscan cada contexto dentro del montón.
    ghdir=$(make_gh "$repo" <<GH
case "\$1 \$2" in
    ("repo view") echo 'ERPlora/hub'; exit 0 ;;
    ("auth status") exit 0 ;;
esac
for a in "\$@"; do [ "\$a" = "-X" ] && { printf '%s\n' "\$@" >> "$repo/POSTARGS"; exit 0; }; done
for a in "\$@"; do case "\$a" in (repos/*/git/ref/*) echo "$sha"; exit 0 ;; esac; done
exit 0
GH
)
    run_hook "$repo" "refs/heads/x $sha refs/heads/x $ZERO" \
        HUB_GATE_STATE_DIR="$repo/.state" PATH="$ghdir:$PATH" \
        HUB_GATE_PUSH_POLL_TRIES=2 HUB_GATE_PUSH_POLL_DELAY=0 \
        HUB_GATE_TEST_CMD="true" HUB_GATE_WEB_CMD="true" \
        SKIP_HUB_WEB="$skip" >/dev/null
    sleep 2
    tr '\n' ' ' < "$repo/POSTARGS" 2>/dev/null
}
# Control primero: corriendo TODO si atestigua (si no, el caso de abajo no probaria nada).
ctrl=$(attest_case 0)
skipped=$(attest_case 1)
errs=""
case "$ctrl" in *context=local-gate/hub-tests*) ;; *) errs="$errs CONTROL-no-atestiguo-corriendo-todo";; esac
[ -z "$skipped" ] || errs="$errs attested-a-run-that-skipped-web"
[ -z "$errs" ] \
    && ok "web: SKIP_HUB_WEB deja pasar el push pero NO atestigua (control: sin skip SI atestigua)" \
    || bad "web: SKIP_HUB_WEB deja pasar el push pero NO atestigua" "$errs"

# 8. La etapa web recibe los DSN del banco de e2e. `apps/web/tests/e2e/AssistantGrounded.spec.ts`
#    cae por defecto en `localhost:5434`, un Postgres que en local NO existe: sin exportarlos, el
#    playwright de cada push que toque web moriria en el arranque del runtime.
repo=$(make_cargo_repo)
git -C "$repo" config --bool hooks.hubPrepushGate true
sha=$(touch_and_commit "$repo" apps/web/src/App.vue)
code=$(run_hook "$repo" "refs/heads/x $sha refs/heads/x $ZERO" \
    HUB_GATE_WITH_MODULES=0 HUB_GATE_STATE_DIR="$repo/.state" HUB_GATE_STATUS_CMD="true" \
    HUB_GATE_TEST_CMD="true" \
    DATABASE_URL="postgres://postgres:test@localhost:5433/hub_test" \
    HUB_GATE_E2E_DB_CMD="true" \
    HUB_GATE_WEB_CMD='printf "%s|%s\n" "${HUB_E2E_DATABASE_URL:-}" "${E2E_DATABASE_URL:-}" > '"$repo/DSN")
got=$(cat "$repo/DSN" 2>/dev/null)
errs=""
[ "$code" = 0 ] || errs="$errs exit=$code(want 0)"
case "$got" in
    *hub_e2e_web*\|*hub_e2e_assistant*) ;;
    *) errs="$errs dsn='$got'" ;;
esac
case "$got" in *5434*) errs="$errs apunta-al-5434-que-no-existe" ;; esac
[ -z "$errs" ] \
    && ok "web: la etapa recibe HUB_E2E_DATABASE_URL y E2E_DATABASE_URL del Postgres del gate" \
    || bad "web: la etapa recibe HUB_E2E_DATABASE_URL y E2E_DATABASE_URL del Postgres del gate" "$errs"

# ── hub#1375: el gate llama a `raise_lock_limits` ANTES de definirla ─────────
# `ensure_postgres` (que la llama) corre en el camino TEMPRANO —el diff solo-web,
# alcance Rust `none`— mucho antes de que bash haya ejecutado la definición, que
# vivía 440 líneas más abajo. El hook corre con `set -uo pipefail` y SIN `-e`, así
# que no aborta nada: escupe `raise_lock_limits: command not found` y sigue. Un
# fallo MUDO, y con él los límites de locks que la función sube (hub#526) se
# quedan sin subir en ese camino.
#
# Es la misma familia que hub#1355 («ensure_postgres se define antes de su primer
# uso»): allí se movió la función que fallaba y la que ella llama se quedó abajo.
# Por eso van los dos controles: el SÍNTOMA (a) y el ORDEN (b), que caza la
# familia entera aunque el camino cambie de sitio.

# (a) El síntoma: un push solo-web no puede escupir `command not found`.
#     Los otros casos de web pasan DATABASE_URL, con lo que `ensure_postgres`
#     vuelve por la puerta de arriba y no llega nunca a la llamada — por eso este
#     banco no lo cazó en su día. Aquí se deja vacía a propósito y se stubbea
#     `docker` para que la función llegue hasta el final.
#
#     🔴 Sin fijar `HUB_GATE_WEB_CMD`: desde hub#1368 el gate solo prepara Postgres
#     cuando la etapa web es LA SUYA, así que con el comando fijado `ensure_postgres`
#     ya no se llama y este caso no probaría nada — verde por vacío, que es peor que
#     rojo. Se stubbea `pnpm` para llegar al camino de producción, y por eso NO se
#     mira el código de salida: el comando por defecto muere después, en
#     `cargo build -p erplora-server`, que este banco de juguete no tiene. Todo lo
#     que se mide ocurre antes, y el control POSITIVO («raising Postgres lock
#     limits») exige que `ensure_postgres` haya llegado hasta la llamada de verdad.
repo=$(make_cargo_repo)
git -C "$repo" config --bool hooks.hubPrepushGate true
sha=$(touch_and_commit "$repo" apps/web/src/App.vue)
dockerbin="${repo}-docker"; mkdir -p "$dockerbin"
cat > "$dockerbin/docker" <<'DOCK'
#!/usr/bin/env bash
# `ps --format '{{.Names}}'` → el contenedor ya está arriba, así que ensure_postgres
# se salta el run/start y cae directo en la llamada. Todo lo demás: mudo y OK.
if [ "$1" = ps ]; then
    for a in "$@"; do case "$a" in *Names*) echo erplora-test-pg-5433; exit 0 ;; esac; done
    exit 0
fi
exit 0
DOCK
chmod +x "$dockerbin/docker"
printf '#!/bin/sh\nexit 0\n' > "$dockerbin/pnpm"
chmod +x "$dockerbin/pnpm"
run_hook "$repo" "refs/heads/x $sha refs/heads/x $ZERO" \
    HUB_GATE_WITH_MODULES=0 HUB_GATE_STATE_DIR="$repo/.state" HUB_GATE_STATUS_CMD="true" \
    PATH="$dockerbin:$PATH" DATABASE_URL= \
    HUB_GATE_TEST_CMD="true" HUB_GATE_E2E_DB_CMD="true" >/dev/null
errs=""
grep -q 'raise_lock_limits: command not found' "$repo/.out" \
    && errs="$errs la-llamada-muere-muda(command-not-found)"
grep -q 'raising Postgres lock limits' "$repo/.out" \
    || errs="$errs CONTROL-ensure_postgres-no-llego-a-raise_lock_limits"
[ -z "$errs" ] \
    && ok "hub#1375: un push solo-web no escupe 'raise_lock_limits: command not found'" \
    || bad "hub#1375: un push solo-web no escupe 'raise_lock_limits: command not found'" "$errs out=$(tr '\n' ' ' < "$repo/.out" | tail -c 300)"

# (b) El orden, sobre el fichero: definida POR ENCIMA de su primera llamada.
# `-m1` on the grep, not `| head -1`: here grep reads the FILE, so stopping at
# the first match leaves no producer on the other side of a pipe to kill — and
# `cut` reads all of its output (hub#1552).
def_line=$(grep -n -m1 '^raise_lock_limits() {' "$HOOK" | cut -d: -f1)
call_line=$(grep -n -m1 '^[[:space:]]\+raise_lock_limits[[:space:]]*$' "$HOOK" | cut -d: -f1)
errs=""
[ -n "$def_line" ]  || errs="$errs no-encuentro-la-definicion"
[ -n "$call_line" ] || errs="$errs no-encuentro-la-llamada"
[ -n "$def_line" ] && [ -n "$call_line" ] && [ "$def_line" -gt "$call_line" ] \
    && errs="$errs definida-en-$def_line-pero-llamada-en-$call_line"
[ -z "$errs" ] \
    && ok "hub#1375: raise_lock_limits se define por encima de su primer uso" \
    || bad "hub#1375: raise_lock_limits se define por encima de su primer uso" "$errs"

# (c) `$VAR` pegado a un carácter multibyte se come el carácter DENTRO del nombre.
#     bash 5.3 lee `$PG_CONTAINER…` como la variable `PG_CONTAINER…`, que no existe:
#     con `set -u` eso NO es un aviso, es fatal — el hook muere y el push se aborta.
#     Estuvo escondido porque `raise_lock_limits` vuelve antes por la puerta de arriba
#     cuando el contenedor YA tiene los límites subidos; solo un contenedor RECIÉN
#     creado (una máquina nueva, un worktree nuevo) llegaba a la línea. El hook está
#     lleno de prosa con «—», «…» y «→», así que esto reaparece solo: la guardia mira
#     el fichero entero, no esa línea.
#
#     🔴 La guardia va en python3, NO en `grep -P`: el `grep` de macOS es BSD y NO
#     tiene `-P`. Con `2>/dev/null` el «invalid option -- P» se tragaba, la variable
#     salía vacía y el caso pasaba VERDE con el fallo delante — comprobado el 31/08
#     con el mutante puesto (`restarting $PG_CONTAINER…`): 72/72, la guardia en
#     verde. Los runners son Linux, así que en Actions sí cazaba; en el Mac donde
#     empujan los ~19 worktrees, no. Una guardia que no corre no es una guardia, así
#     que además EXIGE la marca de haber corrido: si no puede ejecutarse, es ROJO.
mb=$(HOOK="$HOOK" python3 - 2>&1 <<'PY'
import os, re
hits = []
with open(os.environ["HOOK"], encoding="utf-8") as fh:
    for n, line in enumerate(fh, 1):
        # `${VAR}` queda fuera solo: tras `$` viene `{`, que no abre un nombre.
        for m in re.finditer(r"\$[A-Za-z_][A-Za-z0-9_]*", line):
            nxt = line[m.end():m.end() + 1]
            if nxt and ord(nxt) > 127:
                hits.append("linea %d: %s" % (n, line.strip()[:100]))
for h in hits[:3]:
    print(h)
print("GUARDIA-EJECUTADA")
PY
)
errs=""
case "$mb" in
    *GUARDIA-EJECUTADA*) ;;
    *) errs="la guardia NO se pudo ejecutar, y eso NO es un verde: $mb" ;;
esac
found=$(printf '%s\n' "$mb" | grep -v 'GUARDIA-EJECUTADA' | grep -v '^$')
[ -z "$found" ] || errs="$errs usa \${VAR}: $found"
[ -z "$errs" ] \
    && ok "hub#1375: ningún \$VAR queda pegado a un carácter multibyte (se lo tragaría el nombre)" \
    || bad "hub#1375: ningún \$VAR queda pegado a un carácter multibyte (se lo tragaría el nombre)" "$errs"

# ── hub#1347: el hook consume scripts/ci/test-scope.py, no una copia suya ────
# hub#1346 extrajo el resolutor de alcance a `scripts/ci/test-scope.py` para que
# `test-hub.yml` corriera los paquetes que una PR alcanza. El hook se quedó con
# una copia INLINE de 66 líneas del mismo algoritmo. Dos copias del mismo
# resolutor divergen solas, y cuando divergen el gate local y la nube dejan de
# medir lo mismo sin que nadie se entere: el desfase no deja rojo en ningún sitio.

# (a) No queda copia inline, y el fichero canónico se nombra.
errs=""
grep -q 'scripts/ci/test-scope.py' "$HOOK" || errs="$errs no-nombra-el-resolutor-canonico"
grep -q "python3 -c '" "$HOOK"            && errs="$errs sigue-llevando-una-copia-inline"
[ -z "$errs" ] \
    && ok "hub#1347: el hook nombra scripts/ci/test-scope.py y no lleva copia inline" \
    || bad "hub#1347: el hook nombra scripts/ci/test-scope.py y no lleva copia inline" "$errs"

# (b) …y lo EJECUTA de verdad. Se sabotea el resolutor DEL REPO y el veredicto
#     del hook tiene que venir de ahí. Sin esto, «nombra el fichero» lo cumple
#     un comentario: es la comprobación que caza el positivo.
repo=$(make_cargo_repo)
git -C "$repo" config --bool hooks.hubPrepushGate true
cat > "$repo/scripts/ci/test-scope.py" <<'PY'
import sys
sys.stdin.read()
print("workspace")
print("VENGO-DE-SCRIPTS-CI-TEST-SCOPE")
PY
sha=$(touch_and_commit "$repo" crates/a/src/lib.rs)
code=$(run_hook "$repo" "refs/heads/x $sha refs/heads/x $ZERO" \
    HUB_GATE_WITH_MODULES=0 HUB_GATE_STATE_DIR="$repo/.state" HUB_GATE_STATUS_CMD="true" \
    HUB_GATE_TEST_CMD="true" HUB_GATE_WEB_CMD="true")
errs=""
[ "$code" = 0 ] || errs="$errs exit=$code(want 0)"
grep -q 'VENGO-DE-SCRIPTS-CI-TEST-SCOPE' "$repo/.out" \
    || errs="$errs el-veredicto-NO-sale-del-fichero-del-repo(sigue-la-copia-inline)"
[ -z "$errs" ] \
    && ok "hub#1347: el alcance lo decide el fichero del repo, no una copia dentro del hook" \
    || bad "hub#1347: el alcance lo decide el fichero del repo, no una copia dentro del hook" "$errs out=$(tr '\n' ' ' < "$repo/.out" | tail -c 250)"

# (c) Si el resolutor NO está, se ensancha al workspace: es la degradación segura
#     que el hook ya aplica a todo lo demás (metadata rota, python3 ausente). Un
#     hook que muriera aquí pararía a la flota entera por un fichero movido.
repo=$(make_cargo_repo)
git -C "$repo" config --bool hooks.hubPrepushGate true
git -C "$repo" rm -q scripts/ci/test-scope.py
git -C "$repo" commit -qm "sin resolutor"
sha=$(touch_and_commit "$repo" crates/a/src/lib.rs)
code=$(run_hook "$repo" "refs/heads/x $sha refs/heads/x $ZERO" \
    HUB_GATE_WITH_MODULES=0 HUB_GATE_STATE_DIR="$repo/.state" HUB_GATE_STATUS_CMD="true" \
    HUB_GATE_SCOPE_POLICY=scoped \
    HUB_GATE_TEST_CMD="touch $repo/RAN; true" HUB_GATE_WEB_CMD="true")
errs=""
[ "$code" = 0 ]      || errs="$errs exit=$code(want 0)"
[ -f "$repo/RAN" ]   || errs="$errs no-corrio-la-suite"
grep -q 'full workspace run' "$repo/.out" || errs="$errs no-se-ensancho-al-workspace"
[ -z "$errs" ] \
    && ok "hub#1347: sin resolutor en el repo, el gate se ensancha al workspace (nunca muere)" \
    || bad "hub#1347: sin resolutor en el repo, el gate se ensancha al workspace (nunca muere)" "$errs out=$(tr '\n' ' ' < "$repo/.out" | tail -c 250)"

# ── hub#1356: el gate dispara la etapa web con LOS MISMOS ficheros que el YAML ─
# `test-web.yml` perdió su trigger `pull_request` (hub#1352): la suite pesada se
# mudó a este gate. Pero la lista del hook tenía TRES entradas menos que
# `on.push.paths`, así que un push que solo tocara una de ellas no disparaba la
# etapa web en local NI ningún check en la nube antes de mergear — la única red
# que quedaba era el push a develop/main, o sea POST-MERGE. Es el defecto de
# hub#1247 («una PR que solo toque la guardia no la ejecuta») reaparecido en local.
#
# El contrato estaba escrito solo en un comentario del hook, y un comentario no
# falla cuando alguien cambia la lista de un lado.

# (a) Toda entrada de `on.push.paths` está cubierta por el hook — y se dice CUÁL falta.
mismatch=$(HOOK="$HOOK" ROOT="$ROOT" python3 - <<'PY'
import os, re, sys
hook = open(os.environ["HOOK"], encoding="utf-8").read()
wf   = open(os.path.join(os.environ["ROOT"], ".github/workflows/test-web.yml"), encoding="utf-8").read()

def hook_list(name):
    m = re.search(r'^%s="([^"]*)"' % name, hook, re.M)
    return m.group(1).split() if m else []

prefixes = hook_list("WEB_PREFIXES")
files    = hook_list("WEB_FILES") + hook_list("WEB_LIGHT_FILES")

# on: → push: → paths:  (los comentarios dentro del bloque no cuentan)
lines, paths, depth = wf.split("\n"), [], None
inside = False
for i, l in enumerate(lines):
    if re.match(r"^\s*paths:\s*$", l) and re.search(r"^on:", "\n".join(lines[:i]), re.M):
        # solo el bloque de push:
        prev = [p for p in lines[:i] if p.strip() and not p.strip().startswith("#")]
        if prev and re.match(r"^\s*push:\s*$", prev[-2] if len(prev) > 1 else ""):
            inside, depth = True, len(l) - len(l.lstrip())
            continue
    if inside:
        s = l.strip()
        if not s or s.startswith("#"):
            continue
        ind = len(l) - len(l.lstrip())
        if ind <= depth and not s.startswith("- "):
            break
        if s.startswith("- "):
            paths.append(s[2:].strip().strip('"').strip("'"))

missing = []
for p in paths:
    norm = p[:-3] if p.endswith("/**") else p
    if norm + "/" in prefixes or norm in files:
        continue
    missing.append(p)
if not paths:
    print("NO-PUDE-LEER-on.push.paths")
elif missing:
    print("faltan-en-el-hook: " + " ".join(missing))
PY
)
[ -z "$mismatch" ] \
    && ok "hub#1356: la etapa web se dispara con los mismos ficheros que test-web.yml" \
    || bad "hub#1356: la etapa web se dispara con los mismos ficheros que test-web.yml" "$mismatch"

# (a2) …and triggering is not enough: the default light command RUNS the check of every light
#      file. `web-format.test.sh` (hub#2156) and `merge-check-tree*` (pm#331) entered
#      `on.push.paths` without entering the hook; listing them alone would trigger a stage that
#      never runs them — green with the contract unproven.
light_gap=$(HOOK="$HOOK" python3 - <<'PY'
import os, re
hook = open(os.environ["HOOK"], encoding="utf-8").read()
m = re.search(r'^WEB_LIGHT_FILES="([^"]*)"', hook, re.M)
files = m.group(1).split() if m else []
m = re.search(r"light_cmd='([^']*)'", hook)
cmd = m.group(1) if m else ""
def check_of(f):
    if f == ".github/workflows/test-web.yml":
        return "scripts/tests/test-web-workflow.test.sh"
    ci = re.match(r"^scripts/ci/(.+)\.sh$", f)
    return "scripts/tests/%s.test.sh" % ci.group(1) if ci else f
if not files or not cmd:
    print("NO-PUDE-LEER-WEB_LIGHT_FILES-o-light_cmd")
else:
    gaps = [f for f in files if check_of(f) not in cmd]
    if gaps:
        print("sin-comprobacion-en-light_cmd: " + " ".join(gaps))
PY
)
[ -z "$light_gap" ] \
    && ok "hub#1356: la etapa ligera corre la comprobación de cada fichero que la dispara" \
    || bad "hub#1356: la etapa ligera corre la comprobación de cada fichero que la dispara" "$light_gap"

# (b) Tocar SOLO la guardia dispara la etapa — hoy no dispara nada.
repo=$(make_cargo_repo)
git -C "$repo" config --bool hooks.hubPrepushGate true
sha=$(touch_and_commit "$repo" scripts/tests/no-dead-packages.test.mjs)
code=$(run_hook "$repo" "refs/heads/x $sha refs/heads/x $ZERO" \
    HUB_GATE_WITH_MODULES=0 HUB_GATE_STATE_DIR="$repo/.state" HUB_GATE_STATUS_CMD="true" \
    HUB_GATE_TEST_CMD="true" \
    HUB_GATE_WEB_CMD="touch $repo/WEBFULL; true" \
    HUB_GATE_WEB_LIGHT_CMD="touch $repo/WEBLIGHT; true")
errs=""
[ "$code" = 0 ] || errs="$errs exit=$code(want 0)"
{ [ -f "$repo/WEBLIGHT" ] || [ -f "$repo/WEBFULL" ]; } \
    || errs="$errs tocar-la-guardia-no-disparo-NADA(el-agujero-de-hub#1247)"
[ -z "$errs" ] \
    && ok "hub#1356: un push que solo toca la guardia no-dead-packages SÍ la ejecuta" \
    || bad "hub#1356: un push que solo toca la guardia no-dead-packages SÍ la ejecuta" "$errs out=$(tr '\n' ' ' < "$repo/.out" | tail -c 250)"

# (c) …pero por el camino BARATO: un retoque del YAML no puede arrastrar cargo
#     build + vite build + playwright (~20-40 min). La profundidad va con lo que
#     cambió; los disparadores, con el YAML.
repo=$(make_cargo_repo)
git -C "$repo" config --bool hooks.hubPrepushGate true
sha=$(touch_and_commit "$repo" .github/workflows/test-web.yml)
code=$(run_hook "$repo" "refs/heads/x $sha refs/heads/x $ZERO" \
    HUB_GATE_WITH_MODULES=0 HUB_GATE_STATE_DIR="$repo/.state" HUB_GATE_STATUS_CMD="true" \
    HUB_GATE_TEST_CMD="true" \
    HUB_GATE_WEB_CMD="touch $repo/WEBFULL; true" \
    HUB_GATE_WEB_LIGHT_CMD="touch $repo/WEBLIGHT; true")
errs=""
[ "$code" = 0 ]         || errs="$errs exit=$code(want 0)"
[ -f "$repo/WEBLIGHT" ] || errs="$errs no-corrio-la-etapa-ligera"
[ -f "$repo/WEBFULL" ]  && errs="$errs un-retoque-del-YAML-arrastro-playwright"
[ -z "$errs" ] \
    && ok "hub#1356: tocar el YAML corre la etapa LIGERA, no playwright" \
    || bad "hub#1356: tocar el YAML corre la etapa LIGERA, no playwright" "$errs out=$(tr '\n' ' ' < "$repo/.out" | tail -c 250)"

# (d) La etapa completa sigue siendo la completa: apps/web NO se queda en ligera.
repo=$(make_cargo_repo)
git -C "$repo" config --bool hooks.hubPrepushGate true
sha=$(touch_and_commit "$repo" apps/web/src/App.vue)
code=$(run_hook "$repo" "refs/heads/x $sha refs/heads/x $ZERO" \
    HUB_GATE_WITH_MODULES=0 HUB_GATE_STATE_DIR="$repo/.state" HUB_GATE_STATUS_CMD="true" \
    HUB_GATE_TEST_CMD="true" \
    HUB_GATE_WEB_CMD="touch $repo/WEBFULL; true" \
    HUB_GATE_WEB_LIGHT_CMD="touch $repo/WEBLIGHT; true")
errs=""
[ "$code" = 0 ]        || errs="$errs exit=$code(want 0)"
[ -f "$repo/WEBFULL" ] || errs="$errs un-cambio-de-apps/web-no-corrio-la-etapa-completa"
[ -z "$errs" ] \
    && ok "hub#1356: un cambio de apps/web sigue corriendo la etapa COMPLETA" \
    || bad "hub#1356: un cambio de apps/web sigue corriendo la etapa COMPLETA" "$errs out=$(tr '\n' ' ' < "$repo/.out" | tail -c 250)"

# (e) …y los DOS niveles no son excluyentes: un diff que toca `apps/web` Y el YAML
#     tiene que correr TAMBIÉN el contrato ligero. `pnpm verify` —lo único que la
#     etapa completa corre de la tubería— incluye `no-dead-packages.test.mjs` pero
#     NO `test-web-workflow.test.sh`, y `test-web.yml` ya no tiene `pull_request`
#     (hub#1352): en ese diff combinado el contrato del workflow no lo corría NADIE
#     antes del merge. Es el agujero de hub#1247/#1356 otra vez, por la puerta de
#     al lado — y tocar la app y su workflow en el mismo commit es lo normal.
repo=$(make_cargo_repo)
git -C "$repo" config --bool hooks.hubPrepushGate true
mkdir -p "$repo/apps/web/src" "$repo/.github/workflows"
echo "x" >> "$repo/apps/web/src/App.vue"
echo "# retoque" >> "$repo/.github/workflows/test-web.yml"
git -C "$repo" add -A >/dev/null 2>&1
git -C "$repo" commit -qm "web + yaml en el mismo commit"
sha=$(git -C "$repo" rev-parse HEAD)
code=$(run_hook "$repo" "refs/heads/x $sha refs/heads/x $ZERO" \
    HUB_GATE_WITH_MODULES=0 HUB_GATE_STATE_DIR="$repo/.state" HUB_GATE_STATUS_CMD="true" \
    HUB_GATE_TEST_CMD="true" \
    HUB_GATE_WEB_CMD="touch $repo/WEBFULL; true" \
    HUB_GATE_WEB_LIGHT_CMD="touch $repo/WEBLIGHT; true")
errs=""
[ "$code" = 0 ]         || errs="$errs exit=$code(want 0)"
[ -f "$repo/WEBFULL" ]  || errs="$errs no-corrio-la-etapa-completa"
[ -f "$repo/WEBLIGHT" ] || errs="$errs el-contrato-del-workflow-NO-lo-corrio-nadie(pnpm-verify-no-lo-incluye)"
[ -z "$errs" ] \
    && ok "hub#1356: apps/web + el YAML en el mismo diff corre la completa Y el contrato ligero" \
    || bad "hub#1356: apps/web + el YAML en el mismo diff corre la completa Y el contrato ligero" "$errs out=$(tr '\n' ' ' < "$repo/.out" | tail -c 250)"

# ── Web ATTESTATION: the gate vouches for what it ran (pm#198, hub#1368) ─────
#
# Since hub#1352 the cloud keeps only path-filtered workflows, so a hub PR that
# touches ONLY web or ONLY docs reports ZERO checks — and merge-pr.sh refuses
# that silence unless a seal vouches for the head sha:
#   · local-gate/hub-web          — the web stage ran green on this machine;
#   · local-gate/no-suite-needed  — the diff touches neither Rust nor web.
# Regression tests for ERPlora/pm#198 (web-only PRs unmergeable) and
# ERPlora/hub#1368 (docs-only pushes with no seal). The fake `gh` (make_gh)
# captures every status POST — appending, so a push that posts two seals shows
# both. DATABASE_URL and HUB_GATE_E2E_DB_CMD are pinned so the web stage never
# touches docker.

# 1. A WEB-ONLY diff posts the web seal: the stage ran green, and the seal is
#    the only witness merge-pr.sh can read (the PR has zero Actions checks).
repo=$(make_cargo_repo)
git -C "$repo" config --bool hooks.hubPrepushGate true
sha=$(touch_and_commit "$repo" apps/web/src/App.vue)
ghdir=$(make_gh "$repo" <<GH
case "\$1 \$2" in
    ("repo view") echo 'ERPlora/hub'; exit 0 ;;
    ("auth status") exit 0 ;;
esac
for a in "\$@"; do [ "\$a" = "-X" ] && { printf '%s\n' "\$@" >> "$repo/POSTARGS"; exit 0; }; done
for a in "\$@"; do case "\$a" in (repos/*/git/ref/*) echo "$sha"; exit 0 ;; esac; done
exit 0
GH
)
code=$(run_hook "$repo" "refs/heads/x $sha refs/heads/x $ZERO" \
    HUB_GATE_STATE_DIR="$repo/.state" PATH="$ghdir:$PATH" \
    HUB_GATE_PUSH_POLL_TRIES=2 HUB_GATE_PUSH_POLL_DELAY=0 \
    DATABASE_URL="postgres://postgres:test@localhost:5433/hub_test" \
    HUB_GATE_E2E_DB_CMD="true" \
    HUB_GATE_TEST_CMD="true" HUB_GATE_WEB_CMD="true")
sleep 2   # el status se publica en SEGUNDO PLANO tras verificar el ref: sin esta espera,
          # «no se publicó nada» y «aún no se ha publicado» se leen igual (un verde falso).
args=$(tr '\n' ' ' < "$repo/POSTARGS" 2>/dev/null)
errs=""
[ "$code" = 0 ]                                          || errs="$errs exit=$code(want 0) out=$(tr '\n' ' ' < "$repo/.out" | tail -c 300)"
grep -q 'context=local-gate/hub-web' <<<"$args"          || errs="$errs web-only-diff-posted-no-hub-web-seal"
grep -q 'context=local-gate/hub-tests' <<<"$args"        && errs="$errs web-only-diff-claimed-the-rust-seal"
grep -q 'context=local-gate/no-suite-needed' <<<"$args"  && errs="$errs web-only-diff-claimed-nothing-ran"
[ -z "$errs" ] \
    && ok "attestation: a web-only diff posts local-gate/hub-web and nothing else (pm#198)" \
    || bad "attestation: a web-only diff posts local-gate/hub-web and nothing else (pm#198)" "$errs args='$args'"

# 2. A DOCS-ONLY diff posts the no-suite seal: the gate resolved the sha and
#    decided there was nothing to run — which is NOT the same shape as a dead
#    Actions, and the seal is what lets merge-pr.sh tell them apart.
repo=$(make_cargo_repo)
git -C "$repo" config --bool hooks.hubPrepushGate true
sha=$(touch_and_commit "$repo" docs/nota.md)
ghdir=$(make_gh "$repo" <<GH
case "\$1 \$2" in
    ("repo view") echo 'ERPlora/hub'; exit 0 ;;
    ("auth status") exit 0 ;;
esac
for a in "\$@"; do [ "\$a" = "-X" ] && { printf '%s\n' "\$@" >> "$repo/POSTARGS"; exit 0; }; done
for a in "\$@"; do case "\$a" in (repos/*/git/ref/*) echo "$sha"; exit 0 ;; esac; done
exit 0
GH
)
code=$(run_hook "$repo" "refs/heads/x $sha refs/heads/x $ZERO" \
    HUB_GATE_STATE_DIR="$repo/.state" PATH="$ghdir:$PATH" \
    HUB_GATE_PUSH_POLL_TRIES=2 HUB_GATE_PUSH_POLL_DELAY=0 \
    DATABASE_URL="postgres://postgres:test@localhost:5433/hub_test" \
    HUB_GATE_E2E_DB_CMD="true" \
    HUB_GATE_TEST_CMD="touch $repo/RAN; true" HUB_GATE_WEB_CMD="touch $repo/WEBSTAGE; true")
sleep 2   # el status se publica en SEGUNDO PLANO tras verificar el ref: sin esta espera,
          # «no se publicó nada» y «aún no se ha publicado» se leen igual (un verde falso).
args=$(tr '\n' ' ' < "$repo/POSTARGS" 2>/dev/null)
errs=""
[ "$code" = 0 ]                                          || errs="$errs exit=$code(want 0) out=$(tr '\n' ' ' < "$repo/.out" | tail -c 300)"
grep -q 'context=local-gate/no-suite-needed' <<<"$args"  || errs="$errs docs-only-diff-posted-no-no-suite-seal"
grep -q 'context=local-gate/hub-web' <<<"$args"          && errs="$errs docs-only-diff-claimed-the-web-seal"
grep -q 'context=local-gate/hub-tests' <<<"$args"        && errs="$errs docs-only-diff-claimed-the-rust-seal"
[ -f "$repo/RAN" ]                                       && errs="$errs rust-ran-for-a-docs-only-diff"
[ -f "$repo/WEBSTAGE" ]                                  && errs="$errs web-ran-for-a-docs-only-diff"
[ -z "$errs" ] \
    && ok "attestation: a docs-only diff posts local-gate/no-suite-needed and runs nothing (hub#1368)" \
    || bad "attestation: a docs-only diff posts local-gate/no-suite-needed and runs nothing (hub#1368)" "$errs args='$args'"

# 3. A diff with RUST AND WEB posts BOTH seals: merge-pr.sh needs the Rust one
#    for the suite and the web one for the stage — each seal names what ran.
repo=$(make_cargo_repo)
git -C "$repo" config --bool hooks.hubPrepushGate true
touch_and_commit "$repo" crates/c/src/lib.rs >/dev/null
sha=$(touch_and_commit "$repo" apps/web/src/App.vue)
ghdir=$(make_gh "$repo" <<GH
case "\$1 \$2" in
    ("repo view") echo 'ERPlora/hub'; exit 0 ;;
    ("auth status") exit 0 ;;
esac
for a in "\$@"; do [ "\$a" = "-X" ] && { printf '%s\n' "\$@" >> "$repo/POSTARGS"; exit 0; }; done
for a in "\$@"; do case "\$a" in (repos/*/git/ref/*) echo "$sha"; exit 0 ;; esac; done
exit 0
GH
)
code=$(run_hook "$repo" "refs/heads/x $sha refs/heads/x $ZERO" \
    HUB_GATE_STATE_DIR="$repo/.state" PATH="$ghdir:$PATH" \
    HUB_GATE_PUSH_POLL_TRIES=2 HUB_GATE_PUSH_POLL_DELAY=0 \
    DATABASE_URL="postgres://postgres:test@localhost:5433/hub_test" \
    HUB_GATE_E2E_DB_CMD="true" \
    HUB_GATE_TEST_CMD="true" HUB_GATE_WEB_CMD="true")
sleep 2   # el status se publica en SEGUNDO PLANO tras verificar el ref: sin esta espera,
          # «no se publicó nada» y «aún no se ha publicado» se leen igual (un verde falso).
args=$(tr '\n' ' ' < "$repo/POSTARGS" 2>/dev/null)
errs=""
[ "$code" = 0 ]                                   || errs="$errs exit=$code(want 0) out=$(tr '\n' ' ' < "$repo/.out" | tail -c 300)"
grep -q 'context=local-gate/hub-tests' <<<"$args" || errs="$errs rust-plus-web-did-not-post-the-rust-seal"
grep -q 'context=local-gate/hub-web' <<<"$args"   || errs="$errs rust-plus-web-did-not-post-the-web-seal"
[ -z "$errs" ] \
    && ok "attestation: a diff with Rust and web posts BOTH seals (pm#198)" \
    || bad "attestation: a diff with Rust and web posts BOTH seals (pm#198)" "$errs args='$args'"

# 4. SKIP_HUB_WEB on a web-only diff posts NOTHING: a bypass produces absence
#    of seal, never a false seal — merge-pr.sh keeps refusing, which is the point.
repo=$(make_cargo_repo)
git -C "$repo" config --bool hooks.hubPrepushGate true
sha=$(touch_and_commit "$repo" apps/web/src/App.vue)
ghdir=$(make_gh "$repo" <<GH
case "\$1 \$2" in
    ("repo view") echo 'ERPlora/hub'; exit 0 ;;
    ("auth status") exit 0 ;;
esac
for a in "\$@"; do [ "\$a" = "-X" ] && { printf '%s\n' "\$@" >> "$repo/POSTARGS"; exit 0; }; done
for a in "\$@"; do case "\$a" in (repos/*/git/ref/*) echo "$sha"; exit 0 ;; esac; done
exit 0
GH
)
code=$(run_hook "$repo" "refs/heads/x $sha refs/heads/x $ZERO" \
    HUB_GATE_STATE_DIR="$repo/.state" PATH="$ghdir:$PATH" \
    HUB_GATE_PUSH_POLL_TRIES=2 HUB_GATE_PUSH_POLL_DELAY=0 \
    DATABASE_URL="postgres://postgres:test@localhost:5433/hub_test" \
    HUB_GATE_E2E_DB_CMD="true" \
    HUB_GATE_TEST_CMD="true" HUB_GATE_WEB_CMD="true" \
    SKIP_HUB_WEB=1)
sleep 2   # el status se publica en SEGUNDO PLANO tras verificar el ref: sin esta espera,
          # «no se publicó nada» y «aún no se ha publicado» se leen igual (un verde falso).
out=$(cat "$repo/.out" 2>/dev/null)
errs=""
[ "$code" = 0 ]                || errs="$errs exit=$code(want 0)"
[ ! -f "$repo/POSTARGS" ]      || errs="$errs skipped-web-still-attested: $(tr '\n' ' ' < "$repo/POSTARGS" | tail -c 200)"
grep -qi 'no se atestigua' <<<"$out" || errs="$errs skipped-web-not-called-out"
[ -z "$errs" ] \
    && ok "attestation: SKIP_HUB_WEB on a web-only diff posts nothing and says so" \
    || bad "attestation: SKIP_HUB_WEB on a web-only diff posts nothing and says so" "$errs"

# Regression test for ERPlora/hub#1417
# The local PR reviewer was removed on 2026-09-02 — and the first removal attempt
# left its hook wiring alive for a whole day, spawning reviewers nobody wanted.
# This guard keeps the gate from ever growing that call back: the hook must not
# reference the reviewer handoff (or its fleet seal dir) in any form.
# Positive control, verified when this landed: the pre-removal hook
# (develop@dcdab145) had 3 matches; this check turns red on any of them.
hook="$(dirname "$0")/../.githooks/pre-push"
if grep -nE "pr-reviewer|review_handoff|/reviewed/" "$hook"; then
    bad "hub#1417: the gate never calls the removed local PR reviewer again" "reference found (lines above)"
else
    ok "hub#1417: the gate never calls the removed local PR reviewer again"
fi

# ── hub#1468: un script que no parsea con el bash de ESTA máquina aborta el push ──
#    El bug que lo motivó llegó a `develop` con todos los checks en verde: los runners son
#    Ubuntu con bash 5 y el `case` dentro de `$( … )` solo lo rechaza el 3.2 de macOS, que es
#    donde vive este gate. Aquí se comprueba que el cable BITE de verdad — no que exista.
#    El banco lleva su propio `scripts/ci/shell-syntax.sh` (el real, copiado) porque los repos
#    de mentira de este fichero no tienen `scripts/`, y sin él el gate se lo salta a propósito.
repo=$(make_repo)
git -C "$repo" config --bool hooks.hubPrepushGate true
mkdir -p "$repo/scripts/ci"
cp "$(dirname "$0")/ci/shell-syntax.sh" "$repo/scripts/ci/shell-syntax.sh"
cat > "$repo/scripts/ci/broken.sh" <<'BROKEN'
#!/usr/bin/env bash
# Arms sin paréntesis dentro de una sustitución: lo que bash 3.2 no parsea.
x=$(
    case "a" in
        a) echo one ;;
        *) echo other ;;
    esac
)
echo "$x"
BROKEN
git -C "$repo" add scripts
git -C "$repo" commit -qm scripts
sha=$(touch_and_commit "$repo" crates/c/src/lib.rs)
code=$(run_hook "$repo" "refs/heads/x $sha refs/heads/x $ZERO" \
    HUB_GATE_STATE_DIR="$repo/.state" \
    HUB_GATE_DEPTH=fast HUB_GATE_FAST_CMD="touch $repo/RAN")
out=$(cat "$repo/.out" 2>/dev/null)
errs=""
if [ "$(uname -s)" = Darwin ]; then
    [ "$code" = 1 ]                       || errs="$errs exit=$code(want 1)"
    grep -q 'broken.sh' <<<"$out"         || errs="$errs no-file-named"
    grep -q 'no parsea' <<<"$out"         || errs="$errs no-verdict"
    [ ! -f "$repo/RAN" ]                  || errs="$errs ran-the-suite-anyway"
    [ -z "$errs" ] \
        && ok "hub#1468: un script que no parsea con el bash del sistema aborta el push" \
        || bad "hub#1468: un script que no parsea con el bash del sistema aborta el push" "$errs"
else
    # Fuera de macOS no hay bash < 4 y este positivo NO se puede montar: bash 5 parsea el
    # fixture sin pestañear. Se dice en voz alta en vez de contarlo como verde.
    printf '  \033[33m—\033[0m hub#1468: sin bash < 4 en esta máquina, el positivo del suelo solo corre en macOS\n'
fi

# …y con el checker fuera del checkout el gate no se inventa un rojo: los 99 casos de arriba
# corren en repos de mentira sin `scripts/`, y siguen pasando. Aquí se fija explícitamente.
repo=$(make_repo)
git -C "$repo" config --bool hooks.hubPrepushGate true
sha=$(touch_and_commit "$repo" crates/c/src/lib.rs)
code=$(run_hook "$repo" "refs/heads/x $sha refs/heads/x $ZERO" \
    HUB_GATE_STATE_DIR="$repo/.state" \
    HUB_GATE_DEPTH=fast HUB_GATE_FAST_CMD="true")
[ "$code" = 0 ] \
    && ok "hub#1468: sin el checker en el checkout, el gate sigue su camino" \
    || bad "hub#1468: sin el checker en el checkout, el gate sigue su camino" "exit=$code"

# ── hub#1534: un script que canaliza hacia un lector que CORTA aborta el push ──
#    `productor | grep -q PATRÓN` bajo `pipefail` reporta un MATCH como FALLO, y es una
#    carrera: verde en macOS y en un runner ocioso, rojo en uno cargado. El 04/09 tumbó la PR
#    de hub#1530 diciendo que faltaba una línea puesta desde julio. Aquí se comprueba que el
#    cable BITE —no que exista—, igual que el de hub#1468 justo arriba. El banco copia los DOS
#    scripts reales porque el scanner delega el descubrimiento en `shell-syntax.sh`.
#    La línea ofensora se CONSTRUYE, nunca se escribe literal: así este fichero sigue limpio
#    bajo el guard que está probando.
repo=$(make_repo)
git -C "$repo" config --bool hooks.hubPrepushGate true
mkdir -p "$repo/scripts/ci"
cp "$(dirname "$0")/ci/shell-syntax.sh" "$repo/scripts/ci/shell-syntax.sh"
cp "$(dirname "$0")/ci/no-short-circuit-pipes.sh" "$repo/scripts/ci/no-short-circuit-pipes.sh"
{
    printf '#!/usr/bin/env bash\n'
    printf 'set -uo pipefail\n'
    printf 'block=NEEDLE\n'
    printf "printf '%%s' \"\$block\" | %s -q NEEDLE\n" grep
} > "$repo/scripts/ci/short-circuit.sh"
git -C "$repo" add scripts
git -C "$repo" commit -qm scripts
sha=$(touch_and_commit "$repo" crates/c/src/lib.rs)
code=$(run_hook "$repo" "refs/heads/x $sha refs/heads/x $ZERO" \
    HUB_GATE_STATE_DIR="$repo/.state" \
    HUB_GATE_DEPTH=fast HUB_GATE_FAST_CMD="touch $repo/RAN")
out=$(cat "$repo/.out" 2>/dev/null)
errs=""
[ "$code" = 1 ]                          || errs="$errs exit=$code(want 1)"
grep -q 'short-circuit.sh' <<<"$out"     || errs="$errs no-file-named"
grep -q 'lector que corta' <<<"$out"     || errs="$errs no-verdict"
[ ! -f "$repo/RAN" ]                     || errs="$errs ran-the-suite-anyway"
[ -z "$errs" ] \
    && ok "hub#1534: un script que canaliza hacia un lector que corta aborta el push" \
    || bad "hub#1534: un script que canaliza hacia un lector que corta aborta el push" "$errs"

# …y con el mismo banco LIMPIO (here-string en vez de tubería) el gate deja pasar: un guard que
# no se puede satisfacer es un guard que se acaba desactivando.
repo=$(make_repo)
git -C "$repo" config --bool hooks.hubPrepushGate true
mkdir -p "$repo/scripts/ci"
cp "$(dirname "$0")/ci/shell-syntax.sh" "$repo/scripts/ci/shell-syntax.sh"
cp "$(dirname "$0")/ci/no-short-circuit-pipes.sh" "$repo/scripts/ci/no-short-circuit-pipes.sh"
{
    printf '#!/usr/bin/env bash\n'
    printf 'set -uo pipefail\n'
    printf 'block=NEEDLE\n'
    printf '%s -q NEEDLE <<<"$block"\n' grep
} > "$repo/scripts/ci/clean.sh"
git -C "$repo" add scripts
git -C "$repo" commit -qm scripts
sha=$(touch_and_commit "$repo" crates/c/src/lib.rs)
code=$(run_hook "$repo" "refs/heads/x $sha refs/heads/x $ZERO" \
    HUB_GATE_STATE_DIR="$repo/.state" \
    HUB_GATE_DEPTH=fast HUB_GATE_FAST_CMD="true")
[ "$code" = 0 ] \
    && ok "hub#1534: el arreglo con here-string pasa el gate" \
    || bad "hub#1534: el arreglo con here-string pasa el gate" "exit=$code out=$(cat "$repo/.out" 2>/dev/null)"

# ── 55. hub#1602 — canonical installed copy → the warning must not DOWNGRADE ──
#    Same state as 46 (installed copy IS the integration ref's blob, checkout is
#    behind), but this pins the MESSAGE instead of the file. `install-hooks.sh`
#    copies `$REPO_ROOT/.githooks/pre-push` — the WORKING TREE — into the shared
#    `core.hooksPath`, so following that advice from a stale checkout installs the
#    OLD gate for every worktree on the machine. And a stale checkout is the state
#    that fires this warning most often: it fired on 06/09 during the release, on a
#    machine whose installed hook was byte-identical to origin/develop.
#    Warning: right. Remedy: backwards.
repo=$(make_cargo_repo)
git -C "$repo" config --bool hooks.hubPrepushGate true
mkdir -p "$repo/.githooks"
printf '%s\n' '#!/usr/bin/env bash' '# ancient gate: no self-heal here' 'exit 0' > "$repo/.githooks/pre-push"
chmod +x "$repo/.githooks/pre-push"
git -C "$repo" add -A && git -C "$repo" commit -qm "vendor the OLD hook"
old_base=$(git -C "$repo" rev-parse HEAD)
cp "$HOOK" "$repo/.githooks/pre-push"
git -C "$repo" add -A && git -C "$repo" commit -qm "upgrade the gate"
git -C "$repo" update-ref refs/remotes/origin/develop HEAD
git -C "$repo" checkout -q "$old_base"
git -C "$repo" checkout -qb feature
sha=$(touch_and_commit "$repo" crates/c/src/lib.rs)
mkdir -p "$repo/installed"
cp "$HOOK" "$repo/installed/pre-push"
chmod +x "$repo/installed/pre-push"
( cd "$repo" && printf '%s\n' "refs/heads/feature $sha refs/heads/feature $ZERO" | env \
    HUB_GATE_WITH_MODULES=0 HUB_GATE_STATE_DIR="$repo/.state" HUB_GATE_STATUS_CMD="true" \
    HUB_GATE_TEST_CMD="true" \
    bash "$repo/installed/pre-push" ) >"$repo/.out" 2>&1
code=$?
out=$(cat "$repo/.out" 2>/dev/null)
errs=""
[ "$code" = 0 ]                          || errs="$errs exit=$code(want 0)"
grep -qi 'out of sync' <<<"$out"         || errs="$errs no-drift-warning"
grep -qi 'canonical' <<<"$out"           || errs="$errs does-not-say-the-installed-copy-is-canonical"
grep -q 'install-hooks.sh' <<<"$out"     && errs="$errs sends-you-to-downgrade-the-machine-wide-gate"
[ -z "$errs" ] \
    && ok "drift: a canonical installed copy is not sent to resync from a stale checkout" \
    || bad "drift: a canonical installed copy is not sent to resync from a stale checkout" "$errs out=$(tr '\n' ' ' <<<"$out" | tail -c 300)"

# ─────────────────────────────────────────────────────────────────────────────
#  Un árbol que Actions YA probó (hub#1679)
# ─────────────────────────────────────────────────────────────────────────────
#  Promoting develop → main pushes a commit whose TREE is, byte for byte, one
#  Actions already ran `cargo test --workspace` on. Today that push has to pay
#  the suite again (>40 min) from a checkout parked on that exact tree — so in
#  practice it is pushed with SKIP_HUB_TESTS=1 and the release carries NO seal.
#  The gate already reuses a green it recorded itself (case 32); these cases say
#  it must also accept the proof Actions produced on the identical tree.
#
#  It is not a softening: `merge-pr.sh` treats the CI check as the AUTHORITY and
#  the local attestation as "an additional signal, never accepted in place of
#  the check". And the seal names its provenance, per hub#1207 §4: a run that
#  happened in Actions publishes `local-gate/hub-tests-ci`, never the context
#  that claims the pusher's machine.

# ── 63. The release case: proof lives on the PARENT with the identical tree ───
repo=$(make_repo)
git -C "$repo" config --bool hooks.hubPrepushGate true
base=$(git -C "$repo" rev-parse HEAD)
echo two > "$repo/file"
git -C "$repo" commit -qam two            # develop head — this is what CI tested
dev=$(git -C "$repo" rev-parse HEAD)
# The promotion commit: develop's tree, parented on main. The remote has never
# seen it, so nothing can be asked about the pushed sha itself.
prom=$(git -C "$repo" commit-tree "$dev^{tree}" -p "$base" -p "$dev" -m "Merge pull request #1 from ERPlora/develop")
git -C "$repo" update-ref refs/remotes/origin/develop "$dev"   # the remote knows develop…
echo three > "$repo/file"
git -C "$repo" commit -qam three          # …and the checkout moves on
code=$(run_hook "$repo" "refs/heads/main $prom refs/heads/main $ZERO" \
    HUB_GATE_STATE_DIR="$repo/.state" \
    HUB_GATE_STATUS_CMD="printf '%s %s\n' \"\$1\" \"\$2\" >> $repo/STATUS" \
    HUB_GATE_CI_CHECKS_CMD="[ \"\$1\" = $dev ] && printf 'success\tcargo test --workspace\n'; true" \
    HUB_GATE_TEST_CMD="touch $repo/RAN; true")
out=$(cat "$repo/.out" 2>/dev/null)
errs=""
[ "$code" = 0 ]                                   || errs="$errs exit=$code(want 0)"
[ ! -f "$repo/RAN" ]                              || errs="$errs suite-rerun-on-an-already-proven-tree"
grep -q "^$prom local-gate/hub-tests-ci$" "$repo/STATUS" 2>/dev/null \
                                                  || errs="$errs seal=$(cat "$repo/STATUS" 2>/dev/null | tr '\n' ',')(want $prom local-gate/hub-tests-ci)"
# The proof is Actions', so it must NOT be filed as a local green: the next
# push would then claim `local-gate/hub-tests` — a run on this machine that
# never happened.
ls "$repo/.state"/*.green >/dev/null 2>&1         && errs="$errs recorded-actions-run-as-a-local-green"
[ -z "$errs" ] \
    && ok "hub#1679: tree already green in Actions — push passes, nothing recompiled, seal names CI" \
    || bad "hub#1679: tree already green in Actions — push passes, nothing recompiled, seal names CI" "$errs out=$(tr '\n' ' ' <<<"$out" | tail -c 300)"

# ── 64. A RED workspace check on that tree proves nothing → refuse ────────────
repo=$(make_repo)
git -C "$repo" config --bool hooks.hubPrepushGate true
sha=$(git -C "$repo" rev-parse HEAD)
git -C "$repo" update-ref refs/remotes/origin/develop "$sha"   # the remote has it…
echo two > "$repo/file"
git -C "$repo" commit -qam two            # checkout moves on: hub#855 would refuse
code=$(run_hook "$repo" "refs/heads/main $sha refs/heads/main $ZERO" \
    HUB_GATE_STATE_DIR="$repo/.state" \
    HUB_GATE_STATUS_CMD="printf '%s %s\n' \"\$1\" \"\$2\" >> $repo/STATUS" \
    HUB_GATE_CI_CHECKS_CMD="printf 'failure\tcargo test --workspace\n'" \
    HUB_GATE_TEST_CMD="touch $repo/RAN; true")
errs=""
[ "$code" = 1 ]                            || errs="$errs exit=$code(want 1)"
[ ! -f "$repo/STATUS" ]                    || errs="$errs attested-a-red-run"
ls "$repo/.state"/*.green >/dev/null 2>&1  && errs="$errs green-recorded"
[ -z "$errs" ] \
    && ok "hub#1679: CI workspace check RED on that tree — still refused, nothing attested" \
    || bad "hub#1679: CI workspace check RED on that tree — still refused, nothing attested" "$errs"

# ── 65. Green checks that do not RUN the workspace prove nothing (hub#640) ────
#    The exact shape merge-pr.sh was built against: two greens, and nothing
#    anywhere executed the code. Only `cargo test --workspace` answers this.
repo=$(make_repo)
git -C "$repo" config --bool hooks.hubPrepushGate true
sha=$(git -C "$repo" rev-parse HEAD)
git -C "$repo" update-ref refs/remotes/origin/develop "$sha"
echo two > "$repo/file"
git -C "$repo" commit -qam two
code=$(run_hook "$repo" "refs/heads/main $sha refs/heads/main $ZERO" \
    HUB_GATE_STATE_DIR="$repo/.state" \
    HUB_GATE_STATUS_CMD="printf '%s %s\n' \"\$1\" \"\$2\" >> $repo/STATUS" \
    HUB_GATE_CI_CHECKS_CMD="printf 'success\tpnpm verify (vue-tsc + vitest + module-sdk)\nsuccess\tcargo test -p erplora-tauri + Kotlin del plugin\n'" \
    HUB_GATE_TEST_CMD="touch $repo/RAN; true")
errs=""
[ "$code" = 1 ]                            || errs="$errs exit=$code(want 1)"
[ ! -f "$repo/STATUS" ]                    || errs="$errs attested-without-the-workspace-check"
[ -z "$errs" ] \
    && ok "hub#1679: green checks that never ran the workspace — refused, not accepted as proof" \
    || bad "hub#1679: green checks that never ran the workspace — refused, not accepted as proof" "$errs"

# ── 66. The proof must be on THIS tree, not merely somewhere in history ───────
repo=$(make_repo)
git -C "$repo" config --bool hooks.hubPrepushGate true
old=$(git -C "$repo" rev-parse HEAD)       # green in CI…
echo two > "$repo/file"
git -C "$repo" commit -qam two             # …but we push THIS one, another tree
sha=$(git -C "$repo" rev-parse HEAD)
git -C "$repo" update-ref refs/remotes/origin/develop "$sha"   # both are on the remote
echo three > "$repo/file"
git -C "$repo" commit -qam three           # and the checkout moves on again
code=$(run_hook "$repo" "refs/heads/main $sha refs/heads/main $ZERO" \
    HUB_GATE_STATE_DIR="$repo/.state" \
    HUB_GATE_STATUS_CMD="printf '%s %s\n' \"\$1\" \"\$2\" >> $repo/STATUS" \
    HUB_GATE_CI_CHECKS_CMD="[ \"\$1\" = $old ] && printf 'success\tcargo test --workspace\n'; true" \
    HUB_GATE_TEST_CMD="touch $repo/RAN; true")
errs=""
[ "$code" = 1 ]                            || errs="$errs exit=$code(want 1)"
[ ! -f "$repo/STATUS" ]                    || errs="$errs attested-from-another-tree"
[ -z "$errs" ] \
    && ok "hub#1679: CI green on a DIFFERENT tree — the proof must be this content" \
    || bad "hub#1679: CI green on a DIFFERENT tree — the proof must be this content" "$errs"


# ── 67. An ordinary push asks GitHub NOTHING (hub#1679 must cost the fleet 0) ──
#    Case 63 runs BEFORE the depth dispatch, so it is on the path of every push
#    this machine makes — ~19 worktrees. A brand-new commit carries a tree the
#    remote has never seen, so probing it is a guaranteed 404: the candidate is
#    filtered LOCALLY (is it reachable from a remote-tracking ref?) and the
#    network is never touched.
repo=$(make_repo)
git -C "$repo" config --bool hooks.hubPrepushGate true
git -C "$repo" update-ref refs/remotes/origin/develop HEAD
echo two > "$repo/file"
git -C "$repo" commit -qam two            # a commit the remote cannot know
sha=$(git -C "$repo" rev-parse HEAD)
echo three > "$repo/file"
git -C "$repo" commit -qam three          # …pushed from a checkout that moved on
code=$(run_hook "$repo" "refs/heads/feature $sha refs/heads/feature $ZERO" \
    HUB_GATE_STATE_DIR="$repo/.state" \
    HUB_GATE_STATUS_CMD="printf '%s %s\n' \"\$1\" \"\$2\" >> $repo/STATUS" \
    HUB_GATE_CI_CHECKS_CMD="touch $repo/ASKED; true" \
    HUB_GATE_TEST_CMD="touch $repo/RAN; true")
errs=""
[ "$code" = 1 ]              || errs="$errs exit=$code(want 1)"
[ ! -f "$repo/ASKED" ]       || errs="$errs asked-github-about-a-sha-it-cannot-have"
[ ! -f "$repo/STATUS" ]      || errs="$errs attested"
[ -z "$errs" ] \
    && ok "hub#1679: ordinary push — the CI lookup is filtered out locally, GitHub is never asked" \
    || bad "hub#1679: ordinary push — the CI lookup is filtered out locally, GitHub is never asked" "$errs"

# ── 68. A check whose name merely CONTAINS the workspace check is another check ─
#    The match is the whole line. `cargo test --workspace (shard 2)` green says
#    nothing about the job `merge-pr.sh` treats as the authority — a substring
#    match survived every other case of this block (review of hub#1956).
repo=$(make_repo)
git -C "$repo" config --bool hooks.hubPrepushGate true
sha=$(git -C "$repo" rev-parse HEAD)
git -C "$repo" update-ref refs/remotes/origin/develop "$sha"
echo two > "$repo/file"
git -C "$repo" commit -qam two
code=$(run_hook "$repo" "refs/heads/main $sha refs/heads/main $ZERO" \
    HUB_GATE_STATE_DIR="$repo/.state" \
    HUB_GATE_STATUS_CMD="printf '%s %s\n' \"\$1\" \"\$2\" >> $repo/STATUS" \
    HUB_GATE_CI_CHECKS_CMD="printf 'success\tcargo test --workspace (shard 2)\nnot-success\tcargo test --workspace\n'" \
    HUB_GATE_TEST_CMD="touch $repo/RAN; true")
errs=""
[ "$code" = 1 ]                            || errs="$errs exit=$code(want 1)"
[ ! -f "$repo/STATUS" ]                    || errs="$errs attested-from-a-lookalike-check"
[ -z "$errs" ] \
    && ok "hub#1679: a green check that only CONTAINS the workspace name — refused" \
    || bad "hub#1679: a green check that only CONTAINS the workspace name — refused" "$errs"

# ── 69. The same commit carries the workspace check RED and GREEN → no proof ───
#    One sha holds one check run PER EVENT (measured on c0fbc3fc: a `push` run
#    and a `pull_request` run, both named `cargo test --workspace`). "Any line is
#    green" would seal a tree that Actions ALSO saw fail: the red run is evidence
#    about this very content, so it falls through to the refusal — the safe side.
repo=$(make_repo)
git -C "$repo" config --bool hooks.hubPrepushGate true
sha=$(git -C "$repo" rev-parse HEAD)
git -C "$repo" update-ref refs/remotes/origin/develop "$sha"
echo two > "$repo/file"
git -C "$repo" commit -qam two
code=$(run_hook "$repo" "refs/heads/main $sha refs/heads/main $ZERO" \
    HUB_GATE_STATE_DIR="$repo/.state" \
    HUB_GATE_STATUS_CMD="printf '%s %s\n' \"\$1\" \"\$2\" >> $repo/STATUS" \
    HUB_GATE_CI_CHECKS_CMD="printf 'success\tcargo test --workspace\nfailure\tcargo test --workspace\n'" \
    HUB_GATE_TEST_CMD="touch $repo/RAN; true")
errs=""
[ "$code" = 1 ]                            || errs="$errs exit=$code(want 1)"
[ ! -f "$repo/STATUS" ]                    || errs="$errs attested-a-tree-actions-also-saw-fail"
[ -z "$errs" ] \
    && ok "hub#1679: workspace check green AND red on the same commit — refused, nothing attested" \
    || bad "hub#1679: workspace check green AND red on the same commit — refused, nothing attested" "$errs"

# ── 70. …but a CANCELLED twin is not evidence: concurrency cancels runs all day ─
repo=$(make_repo)
git -C "$repo" config --bool hooks.hubPrepushGate true
sha=$(git -C "$repo" rev-parse HEAD)
git -C "$repo" update-ref refs/remotes/origin/develop "$sha"
echo two > "$repo/file"
git -C "$repo" commit -qam two
code=$(run_hook "$repo" "refs/heads/main $sha refs/heads/main $ZERO" \
    HUB_GATE_STATE_DIR="$repo/.state" \
    HUB_GATE_STATUS_CMD="printf '%s %s\n' \"\$1\" \"\$2\" >> $repo/STATUS" \
    HUB_GATE_CI_CHECKS_CMD="printf 'cancelled\tcargo test --workspace\nsuccess\tcargo test --workspace\n'" \
    HUB_GATE_TEST_CMD="touch $repo/RAN; true")
errs=""
[ "$code" = 0 ]                            || errs="$errs exit=$code(want 0)"
grep -q "^$sha local-gate/hub-tests-ci$" "$repo/STATUS" 2>/dev/null \
                                           || errs="$errs seal=$(cat "$repo/STATUS" 2>/dev/null | tr '\n' ',')"
[ -z "$errs" ] \
    && ok "hub#1679: a cancelled twin next to the green one — still sealed" \
    || bad "hub#1679: a cancelled twin next to the green one — still sealed" "$errs"

# ── hub#1998: every web pass starts on a FRESH e2e bench ─────────────────────
# The bench databases used to be created only when missing, so they PERSISTED
# between pushes. The demo seed never overwrites (`WHERE NOT EXISTS … 'Demo'`), so
# once hub#1929 moved the Demo PIN to six digits, the bench kept the old `0000`
# Demo: 401 → 429 too_many_attempts → 18 red specs on every push touching web,
# unrelated to the diff. The bench must be born empty on every pass.
#
# And it cannot be emptied IN PLACE: two worktrees run the web stage at the same
# time on this Mac (per-PID ports, hub#1812/#1756), so dropping a SHARED database
# would kill the neighbour's run. Each pass gets databases of its own, drops them
# when it ends, and prunes the ones a dead pass left behind — never a live one.
#
# `docker` is faked with STATE: one file per database under $dbs, its content the
# rows. The stubbed `pnpm` is the first command of the default web stage, so it
# records what the bench looks like at the exact moment the specs would start.
repo=$(make_cargo_repo)
git -C "$repo" config --bool hooks.hubPrepushGate true
sha=$(touch_and_commit "$repo" apps/web/src/App.vue)
fakebin="${repo}-pgstate"; dbs="$fakebin/dbs"; mkdir -p "$dbs"
cat > "$fakebin/docker" <<DOCK
#!/usr/bin/env bash
dbs="$dbs"
DOCK
cat >> "$fakebin/docker" <<'DOCK'
if [ "$1" = ps ]; then
    for a in "$@"; do case "$a" in *Names*) echo erplora-test-pg-5433; exit 0 ;; esac; done
    exit 0
fi
[ "$1" = exec ] || exit 0
sql="${!#}"
case "$sql" in
    *max_locks_per_transaction*) echo 1228800 ;;
    *pg_database*)
        # Existence probe or listing: answer from the state dir.
        for f in "$dbs"/*; do [ -e "$f" ] || continue; n=$(basename "$f")
            case "$sql" in
                *"datname='$n'"*) echo 1 ;;
                *"datname='"*) ;;
                *) echo "$n" ;;
            esac
        done ;;
    *"DROP DATABASE"*)
        n=$(printf '%s' "$sql" | sed -E 's/.*DROP DATABASE (IF EXISTS )?"?([a-z0-9_]+)"?.*/\2/')
        rm -f "$dbs/$n" ;;
    *"CREATE DATABASE"*)
        n=$(printf '%s' "$sql" | sed -E 's/.*CREATE DATABASE "?([a-z0-9_]+)"?.*/\1/')
        [ -e "$dbs/$n" ] && { echo "ERROR: database \"$n\" already exists" >&2; exit 1; }
        : > "$dbs/$n" ;;
esac
exit 0
DOCK
chmod +x "$fakebin/docker"
cat > "$fakebin/pnpm" <<PNPM
#!/usr/bin/env bash
{ for u in "\$HUB_E2E_DATABASE_URL" "\$E2E_DATABASE_URL"; do
    n=\${u##*/}
    if [ ! -e "$dbs/\$n" ]; then echo "\$n=MISSING"
    elif [ -s "$dbs/\$n" ]; then echo "\$n=STALE:\$(cat "$dbs/\$n")"
    else echo "\$n=FRESH"; fi
  done; } > "$repo/BENCH"
exit 0
PNPM
chmod +x "$fakebin/pnpm"
# The stale bench of the incident: both databases exist, holding the four-digit Demo.
echo "Demo pin=0000" > "$dbs/hub_e2e_web"
echo "Demo pin=0000" > "$dbs/hub_e2e_assistant"
# A pass that died without cleaning up (its PID is gone) and one still running.
sleep 300 & live_pid=$!
dead_pid=$( (sh -c 'echo $$') )
echo "rows" > "$dbs/hub_e2e_web_${dead_pid}"
echo "rows" > "$dbs/hub_e2e_web_${live_pid}"
run_hook "$repo" "refs/heads/x $sha refs/heads/x $ZERO" \
    HUB_GATE_WITH_MODULES=0 HUB_GATE_STATE_DIR="$repo/.state" HUB_GATE_STATUS_CMD="true" \
    PATH="$fakebin:$PATH" DATABASE_URL= HUB_E2E_DATABASE_URL= E2E_DATABASE_URL= \
    HUB_GATE_TEST_CMD="true" >/dev/null
bench=$(tr '\n' ' ' < "$repo/BENCH" 2>/dev/null)
errs=""
[ -n "$bench" ] || errs="$errs CONTROL-the-web-stage-never-ran"
case "$bench" in *STALE*|*MISSING*) errs="$errs bench-not-fresh:[$bench]" ;; esac
[ "$(printf '%s' "$bench" | grep -o '=FRESH' | wc -l | tr -d ' ')" = 2 ] || errs="$errs want-2-fresh:[$bench]"
case "$bench" in *"hub_e2e_web="*|*"hub_e2e_assistant="*) errs="$errs uses-the-SHARED-database:[$bench]" ;; esac
[ -e "$dbs/hub_e2e_web_${live_pid}" ] || errs="$errs dropped-a-LIVE-neighbour"
[ ! -e "$dbs/hub_e2e_web_${dead_pid}" ] || errs="$errs left-a-dead-pass-leftover"
for n in $(printf '%s' "$bench" | grep -oE 'hub_e2e_[a-z]+_[0-9]+'); do
    [ ! -e "$dbs/$n" ] || errs="$errs leaked-its-own:$n"
done
kill "$live_pid" 2>/dev/null; wait "$live_pid" 2>/dev/null
[ -z "$errs" ] \
    && ok "hub#1998: each web pass runs on fresh bench databases of its own (stale/dead dropped, live neighbour kept)" \
    || bad "hub#1998: each web pass runs on fresh bench databases of its own (stale/dead dropped, live neighbour kept)" "$errs out=$(tr '\n' ' ' < "$repo/.out" | tail -c 400)"


echo
echo "  $pass passed, $fail failed"
[ "$fail" -eq 0 ]
