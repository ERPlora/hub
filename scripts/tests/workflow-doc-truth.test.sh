#!/usr/bin/env bash
# Regression test for ERPlora/hub#2491 — the hub's WORKFLOW documents must stay a usable map.
#
# What happened: nothing in the hub said what each flow has to do, so every fix reinterpreted it and
# the next one changed it again (ERPlora/pm#620, pm#621). The answer is a functional spec per area
# (`WORKFLOW.md` + `workflow/<area>.md`) that a worker MUST read before touching the code under it.
# A spec only helps while it can be navigated: the index says which file holds each flow, a flow ID
# is cited from 19 modules and 5 cross-component journeys, and the status in the index is what a
# reader trusts before opening the file. Each of those rots silently — a flow added to an area file
# and never listed, an ID reused, a status changed in one place only (that last one happened while
# the spec was being integrated: HUB-F202 went to «parcial» in its file and stayed «hecho» in the
# index).
#
# Why a test and not a review rule: all of it is decidable from this repository alone, so the prose
# can be pinned instead of trusted. This does NOT check that a flow tells the truth about the code —
# that is the independent verifier's job (architecture/contracts/workflow-contract.md). It checks
# that the documents still hang together:
#
#   1. the five components exist, each with its declared prefix;
#   2. an area file sits next to its index and repeats the index's prefix;
#   3. every flow header carries the prefix of its file, and no ID appears twice in the repo;
#   4. every live flow has a well-formed `Estado:` and an `Implicados:` line;
#   5. the index table and the area files list exactly the same flows, and each row points at the
#      file that really holds the flow;
#   6. the status in the index row is the status of the flow.
#
# Run:  bash scripts/tests/workflow-doc-truth.test.sh [repo_root]
set -uo pipefail

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repo_root=${1:-$(CDPATH= cd -- "$script_dir/../.." && pwd)}

TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT

cat > "$TMP/check.py" <<'PY'
import os
import re
import sys

ROOT = sys.argv[1]

# component directory (relative to the repo root) -> prefix
COMPONENTS = {
    '.': 'HUB',
    'apps/web': 'HUB_SHELL',
    'apps/tauri': 'HUB_APP',
    'crates/peripherals': 'HUB_PERIPHERALS',
    'crates/plugins/verifactu': 'HUB_VERIFACTU',
}

HEAD = re.compile(r'^### ([A-Z][A-Z0-9_]*-F[0-9]{2,})\b(.*)$')
ROW = re.compile(r'^\|\s*([A-Z][A-Z0-9_]*-F[0-9]{2,})\s*\|(.*)\|\s*$')
LINK = re.compile(r'\]\(([^)]+)\)')
STATES = ('hecho', 'parcial', 'no hecho')

fails = []
passes = 0


def bad(what):
    fails.append(what)


def ok():
    global passes
    passes += 1


def state_of(text):
    """`hecho` | `parcial` | `no hecho` | None, read from an `Estado:` value or a table cell."""
    t = text.strip().strip('*').strip().lower()
    for s in ('no hecho', 'hecho', 'parcial'):
        if t == s or t.startswith(s + ' —') or t.startswith(s + ' -') or t.startswith(s + ' ('):
            return s
    return None


def prefix_of(path):
    for line in open(path, encoding='utf-8'):
        if line.startswith('Prefijo:'):
            return line.split(':', 1)[1].strip()
        if line.startswith('## '):
            return None
    return None


def flows_in(path):
    """[(id, retired, state, has_implicados, line_no)] for every flow header of `path`."""
    out, cur = [], None
    for n, line in enumerate(open(path, encoding='utf-8'), 1):
        line = line.rstrip('\n')
        m = HEAD.match(line)
        if m:
            cur = {'id': m.group(1), 'retired': '[retirado]' in line, 'state': None,
                   'raw_state': None, 'impl': False, 'line': n}
            out.append(cur)
            continue
        if line.startswith('## '):
            cur = None
        if cur is None:
            continue
        if line.startswith('Estado:') and cur['raw_state'] is None:
            cur['raw_state'] = line[len('Estado:'):].strip()
            cur['state'] = state_of(cur['raw_state'])
        elif line.startswith('Implicados:'):
            cur['impl'] = True
    return out


def index_rows(path):
    """{id: (state_or_None, linked_file_or_None)} from the «flow → file» table of an index."""
    rows = {}
    in_flows = False
    for line in open(path, encoding='utf-8'):
        line = line.rstrip('\n')
        if line.startswith('## '):
            in_flows = line.strip() == '## Flujos'
            continue
        if not in_flows:
            continue
        m = ROW.match(line)
        if not m:
            continue
        cells = [c.strip() for c in m.group(2).split('|')]
        state = next((s for s in (state_of(c) for c in cells) if s), None)
        link = None
        for c in cells:
            lm = LINK.search(c)
            if lm:
                link = lm.group(1)
        rows[m.group(1)] = (state, link)
    return rows


seen = {}          # id -> file, repo-wide
for comp, prefix in COMPONENTS.items():
    base = os.path.join(ROOT, comp)
    index = os.path.join(base, 'WORKFLOW.md')
    label = os.path.normpath(os.path.join(comp, 'WORKFLOW.md'))
    if not os.path.isfile(index):
        bad(f'{label}: missing — the component has no functional spec')
        continue
    got = prefix_of(index)
    if got != prefix:
        bad(f'{label}: `Prefijo:` is {got!r}, expected {prefix!r}')
    else:
        ok()

    files = [index]
    wdir = os.path.join(base, 'workflow')
    if os.path.isdir(wdir):
        for fn in sorted(os.listdir(wdir)):
            if not fn.endswith('.md'):
                continue
            p = os.path.join(wdir, fn)
            files.append(p)
            sub = prefix_of(p)
            if sub != prefix:
                bad(f'{os.path.relpath(p, ROOT)}: `Prefijo:` is {sub!r}, its index says {prefix!r}')
            else:
                ok()

    where = {}     # id -> relative file inside the component
    for p in files:
        rel = os.path.relpath(p, ROOT)
        for f in flows_in(p):
            fid = f['id']
            if not fid.startswith(prefix + '-F'):
                bad(f'{rel}:{f["line"]}: {fid} does not carry the prefix {prefix} of its file')
            if fid in seen:
                bad(f'{rel}:{f["line"]}: {fid} is already defined in {seen[fid]} — an ID is never reused')
            else:
                seen[fid] = rel
                ok()
            where[fid] = (os.path.relpath(p, base), f)
            if f['retired']:
                continue
            if f['raw_state'] is None:
                bad(f'{rel}:{f["line"]}: {fid} has no `Estado:`')
            elif f['state'] is None:
                bad(f'{rel}:{f["line"]}: {fid} `Estado: {f["raw_state"][:40]}` is not hecho | parcial — … | no hecho — …')
            elif f['state'] != 'hecho' and '—' not in f['raw_state']:
                bad(f'{rel}:{f["line"]}: {fid} is «{f["state"]}» and does not say what is missing (`{f["state"]} — …`)')
            if not f['impl']:
                bad(f'{rel}:{f["line"]}: {fid} has no `Implicados:` line')

    split = len(files) > 1
    if not split:
        continue
    rows = index_rows(index)
    if not rows:
        bad(f'{label}: split into area files but its `## Flujos` holds no «flow → file» table')
        continue
    for fid, (rel_file, f) in sorted(where.items()):
        if rel_file == 'WORKFLOW.md':
            continue
        if fid not in rows:
            bad(f'{label}: {fid} lives in {rel_file} and the index table does not list it')
            continue
        state, link = rows[fid]
        if link is not None and os.path.normpath(link) != os.path.normpath(rel_file):
            bad(f'{label}: the row of {fid} points at {link}, the flow is in {rel_file}')
        if not f['retired'] and state is not None and f['state'] is not None and state != f['state']:
            bad(f'{label}: the row of {fid} says «{state}», the flow says «{f["state"]}»')
        else:
            ok()
    for fid in sorted(rows):
        if fid not in where:
            bad(f'{label}: the index table lists {fid} and no file of the component defines it')

for f in fails:
    print('  FAIL ' + f)
print(f'workflow-doc-truth: {passes} checks ok, {len(fails)} failed, {len(seen)} flows')
sys.exit(1 if fails else 0)
PY

python3 "$TMP/check.py" "$repo_root"
