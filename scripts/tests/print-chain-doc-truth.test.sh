#!/usr/bin/env bash
# Regression test for ERPlora/hub#1593 — the print chain's prose must match the print chain's CODE.
#
# What happened: ADR-0196 §6 closed 4/4 on 2026-08-08 (queue hub#341, host registry hub#342, drain
# hub#343, `sdk.print` producing hub#344) and for almost a month `ARQUITECTURA.md` still said
# «Falta que `sdk.print` encole (hub#344)», with the same claim copied into three code comments.
# `architecture/hub/crates/peripherals.md` still said the crate is shared by TWO consumers. A reader
# concluded the queue does not exist and either rebuilt it or gave up on it.
#
# Why a test and not another paragraph: prose has no regression test, but BOTH claims are decidable
# from this repository's own code, so the prose can be pinned to it. That is what this file does.
#
#   1. Is `sdk.print` wired to enqueue?      answered by apps/web/src/main.ts + apps/web/src/lib/print.ts
#   2. How many crates consume peripherals?  answered by the Cargo manifests, dev-dependencies excluded
#
# It runs in BOTH directions on purpose. A guard that only banned the stale sentence would go green
# the day somebody DELETES the producer and leaves the docs claiming it works — the same failure
# mirrored. So: producer wired ⇒ no file may call it pending; producer gone ⇒ some file must.
#
# History may still be told, as long as a tombstone travels with it (same line or the two around
# it): the guard must never push anyone towards deleting the past instead of marking it — the rule
# `pm/ai/doc-freshness.sh` already learned. That script is the corpus-wide version of this check and
# carries the same rule (ERPlora/pm#270); this one exists because the hub does not run it, so
# without it the hub is unprotected — which is exactly how hub#1593 happened.
#
# Run:  bash scripts/tests/print-chain-doc-truth.test.sh
set -uo pipefail

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repo_root=$(CDPATH= cd -- "$script_dir/../.." && pwd)

pass=0; fail=0
ok()  { pass=$((pass+1)); printf '  ok   %s\n' "$1"; }
bad() { fail=$((fail+1)); printf '  FAIL %s\n     expected: %s\n     actual:   %s\n' "$1" "$2" "$3"; }

TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT

cat > "$TMP/check.py" <<'PY'
import os
import re
import sys

ROOT = sys.argv[1]
SKIP_DIRS = {'.git', 'node_modules', 'target', 'dist', '.venv', 'gen'}
SCAN_EXT = ('.md', '.rs', '.ts', '.vue')

# ── The sentence shapes that declare the chain PENDING ────────────────────────────────────────
# Anchored on the verb of pendency plus the symbol, never on `sdk.print` alone: the symbol is named
# in dozens of legitimate places (the SDK, the crate README, the tests) and flagging them all is the
# noise that teaches everyone to ignore a guard.
PENDING = re.compile(
    r'(?:falta|faltan|pendiente|a[uú]n no|todav[ií]a no)[^\n]{0,40}`?sdk\.print`?'
    r'|`?sdk\.print`?[^\n]{0,40}(?:sigue siendo hub#344|a[uú]n no encola|todav[ií]a no encola'
    r'|est[aá] pendiente|starts producing jobs)'
    r'|lo que falta es el host'
    r'|ning[uú]n productor encola\b'
    r'|producer path[^\n]{0,40}(?:are|is) separate work',
    re.I)

# The claim that the crate is shared by two consumers.
TWO_CONSUMERS = re.compile(
    r'(?:comparten|la comparten|lo comparten)[^\n]{0,20}\bdos consumidores'
    r'|\bdos consumidores\b'
    r'|\btwo consumers\b',
    re.I)

# Words that turn a claim into history. A tombstone is signal for whoever comes looking; a silent
# deletion is not, so a marked mention is never a finding.
MARKER = re.compile(
    r'🪦|⛔|derogad|obsolet|retirad|hist[oó]ric|ya no es cierto|dec[ií]a|se escribi[oó]|'
    r'no longer true|used to say|tombstone|l[aá]pida',
    re.I)


def scan(pattern):
    """Every (path, lineno, text) matching `pattern` without a tombstone within two lines."""
    hits = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            if not name.endswith(SCAN_EXT):
                continue
            path = os.path.join(dirpath, name)
            try:
                lines = open(path, encoding='utf-8', errors='replace').read().splitlines()
            except OSError:
                continue
            for i, line in enumerate(lines):
                if not pattern.search(line):
                    continue
                window = '\n'.join(lines[max(0, i - 2):i + 3])
                if MARKER.search(window):
                    continue
                hits.append((os.path.relpath(path, ROOT), i + 1, line.strip()))
    return hits


def producer_is_wired():
    """Does `sdk.print` enqueue today? Read the shell, not the docs (hub#344)."""
    main_ts = os.path.join(ROOT, 'apps/web/src/main.ts')
    print_ts = os.path.join(ROOT, 'apps/web/src/lib/print.ts')
    try:
        main = open(main_ts, encoding='utf-8', errors='replace').read()
        cascade = open(print_ts, encoding='utf-8', errors='replace').read()
    except OSError:
        return None  # not a hub tree: the caller decides
    wired = 'enqueue:' in main and '/api/print/jobs' in main
    return wired and "via: 'queue'" in cascade


def production_consumers():
    """Crates that depend on `erplora-peripherals` for REAL — dev/build dependencies excluded.

    `crates/server` declares it too, but under `[dev-dependencies]`, for the manual bench against a
    real thermal printer (`tests/print_to_real_printer.rs`). Counting it is how a reader concludes
    there are two consumers, which is the second half of hub#1593.
    """
    found = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        if 'Cargo.toml' not in filenames:
            continue
        rel = os.path.relpath(os.path.join(dirpath, 'Cargo.toml'), ROOT)
        if rel.startswith('crates/peripherals'):
            continue  # the crate is not its own consumer
        section = ''
        for line in open(os.path.join(dirpath, 'Cargo.toml'), encoding='utf-8', errors='replace'):
            header = re.match(r'\s*\[([^\]]+)\]', line)
            if header:
                section = header.group(1)
                continue
            if not re.match(r'\s*erplora-peripherals\s*=', line):
                continue
            # `[dependencies]` and `[target.'cfg(…)'.dependencies]` count; dev/build do not.
            if section.split('.')[-1] == 'dependencies':
                found.append(rel)
    return sorted(found)


wired = producer_is_wired()
consumers = production_consumers()
findings = []

if wired is True:
    for path, line, text in scan(PENDING):
        findings.append(f'{path}:{line}: `sdk.print` DOES enqueue (hub#344, wired in '
                        f'apps/web/src/main.ts) but this line calls the chain pending: {text}')
elif wired is False:
    if not scan(PENDING):
        findings.append('apps/web/src/main.ts no longer wires the `enqueue` producer, so '
                        '`sdk.print` does NOT enqueue — and no document says so. Say it, or put '
                        'the producer back (hub#344).')

if len(consumers) == 1:
    for path, line, text in scan(TWO_CONSUMERS):
        findings.append(f'{path}:{line}: `erplora-peripherals` has ONE production consumer '
                        f'({consumers[0]}) but this line claims two: {text}')

print(f'consumers={len(consumers)} {consumers}')
print(f'wired={wired}')
for f in findings:
    print(f'FINDING {f}')
sys.exit(1 if findings else 0)
PY

check() { python3 "$TMP/check.py" "$1" 2>&1; }

# ── Hermetic fixtures: prove the mechanism BEFORE sweeping the real tree ───────────────────────
# A guard that only ever runs against a green tree has never been shown to catch anything.
mkfix() {
    d="$TMP/$1"; shift
    mkdir -p "$d/apps/web/src/lib" "$d/crates/peripherals" "$d/apps/tauri/src-tauri"
    printf 'const s = { enqueue: async () => fetch("/api/print/jobs") };\n' > "$d/apps/web/src/main.ts"
    printf "return { via: 'queue', role };\n" > "$d/apps/web/src/lib/print.ts"
    printf '[package]\nname = "erplora-peripherals"\n' > "$d/crates/peripherals/Cargo.toml"
    printf '[package]\nname = "app"\n\n[dependencies]\nerplora-peripherals = { path = "x" }\n' \
        > "$d/apps/tauri/src-tauri/Cargo.toml"
    echo "$d"
}

echo "1. la frase que da la cola por PENDIENTE, con el productor cableado"
d=$(mkfix pending)
printf 'Falta que `sdk.print` encole (hub#344).\n' > "$d/ARQUITECTURA.md"
out=$(check "$d")
case "$out" in *"FINDING"*"calls the chain pending"*) ok "caza «Falta que sdk.print encole»" ;;
    *) bad "caza «Falta que sdk.print encole»" "un FINDING" "$out" ;; esac

# El texto real de `peripherals.md` venía PARTIDO en dos líneas («…es el host\n> de impresión…») y
# el escáner lee línea a línea: un patrón que exigiera la frase entera pasa un fixture cómodo de una
# sola línea y NO caza el documento. Por eso el fixture lleva el salto.
d=$(mkfix pending2)
printf 'La cola existe; lo que falta es el host\nde impresión y el drenaje.\n' > "$d/ARQUITECTURA.md"
out=$(check "$d")
case "$out" in *"FINDING"*) ok "caza «lo que falta es el host», aunque la frase venga PARTIDA" ;;
    *) bad "caza «lo que falta es el host» partida" "un FINDING" "$out" ;; esac

d=$(mkfix pending3)
printf '//! the `sdk.print` producer path (hub#344) are separate work.\n' > "$d/crates/x.rs"
out=$(check "$d")
case "$out" in *"FINDING"*) ok "caza la misma afirmación en un comentario de código" ;;
    *) bad "caza la afirmación en un comentario" "un FINDING" "$out" ;; esac

echo "2. la prosa correcta NO dispara"
d=$(mkfix clean)
printf 'As-built (hub#344): `sdk.print` ENCOLA; sin app instalada el tique espera en la cola.\n' \
    > "$d/ARQUITECTURA.md"
check "$d" >/dev/null && ok "decir que sdk.print SÍ encola pasa" || bad "decir que sdk.print SÍ encola pasa" "exit 0" "$(check "$d")"

d=$(mkfix tomb)
printf '🪦 El doc decía «Falta que `sdk.print` encole»; derogado por hub#344.\n' > "$d/ARQUITECTURA.md"
check "$d" >/dev/null && ok "la frase vieja CON lápida pasa (no se borra la historia)" \
    || bad "la frase vieja con lápida pasa" "exit 0" "$(check "$d")"

echo "3. la dirección CONTRARIA: el productor desaparece y la doc calla"
d=$(mkfix unwired)
printf 'const s = {};\n' > "$d/apps/web/src/main.ts"
printf 'As-built (hub#344): `sdk.print` ENCOLA.\n' > "$d/ARQUITECTURA.md"
out=$(check "$d")
case "$out" in *"no longer wires"*) ok "si se borra el productor y nadie lo dice, salta" ;;
    *) bad "si se borra el productor y nadie lo dice, salta" "un FINDING" "$out" ;; esac

echo "4. el recuento de consumidores sale de los Cargo.toml, no de la prosa"
d=$(mkfix twoclaim)
printf 'El crate lo comparten dos consumidores que montan su propio transporte.\n' > "$d/doc.md"
out=$(check "$d")
case "$out" in *"claims two"*) ok "con UN consumidor real, «dos consumidores» es un hallazgo" ;;
    *) bad "con UN consumidor real, «dos consumidores» es un hallazgo" "un FINDING" "$out" ;; esac

d=$(mkfix devdep); mkdir -p "$d/crates/server"
printf '[package]\nname = "srv"\n\n[dependencies]\nserde = "1"\n\n[dev-dependencies]\nerplora-peripherals = { path = "x" }\n' \
    > "$d/crates/server/Cargo.toml"
printf 'Un solo consumidor de producción.\n' > "$d/doc.md"
out=$(check "$d")
case "$out" in *"consumers=1 "*) ok "una dev-dependency NO cuenta como consumidor" ;;
    *) bad "una dev-dependency NO cuenta como consumidor" "consumers=1" "$out" ;; esac

# El control de arriba solo vale si el MISMO fichero, movido a `[dependencies]`, SÍ cuenta: si no,
# «consumers=1» podría estar diciendo que el parser no lee ese Cargo.toml en absoluto.
d=$(mkfix realdep); mkdir -p "$d/crates/server"
printf '[package]\nname = "srv"\n\n[dependencies]\nerplora-peripherals = { path = "x" }\n' \
    > "$d/crates/server/Cargo.toml"
out=$(check "$d")
case "$out" in *"consumers=2 "*) ok "el MISMO fichero en [dependencies] sí cuenta (el control ve el positivo)" ;;
    *) bad "el mismo fichero en [dependencies] sí cuenta" "consumers=2" "$out" ;; esac

d=$(mkfix twodeps)
mkdir -p "$d/crates/other"
printf '[package]\nname = "o"\n\n[dependencies]\nerplora-peripherals = { path = "x" }\n' \
    > "$d/crates/other/Cargo.toml"
printf 'El crate lo comparten dos consumidores.\n' > "$d/doc.md"
out=$(check "$d")
case "$out" in *"consumers=2"*) ok "con DOS consumidores reales, decir «dos» deja de ser un fallo" ;;
    *) bad "con DOS consumidores reales, decir «dos» deja de ser un fallo" "consumers=2" "$out" ;; esac

echo "5. el árbol REAL del hub"
out=$(check "$repo_root")
case "$out" in
    *FINDING*) bad "la doc del hub concuerda con su código" "sin hallazgos" "$out" ;;
    *)         ok "la doc del hub concuerda con su código  [$(printf '%s' "$out" | tr '\n' ' ')]" ;;
esac

printf '\n  %s: %d failed, %d passed\n' "$( [ "$fail" -eq 0 ] && echo GREEN || echo RED )" "$fail" "$pass"
[ "$fail" -eq 0 ]
