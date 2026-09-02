#!/usr/bin/env bash
# Contract test: the PROSE of the CI files must not claim triggers that do not exist
# (ERPlora/hub#1438).
#
# WHY THIS EXISTS. Nothing tied a comment to the `on:` block it describes, so the two drifted
# apart and the comment kept being read as fact:
#
#   · `.github/workflows/test-hub-modules.yml` documented "the THREE triggers" and spent a
#     paragraph on a `pull_request` that pm#197 had removed. Read as written, it says a red run
#     of that workflow blocks `kind:contract` PRs. It blocks nothing — and the claim was
#     repeated in the alert issue the workflow OPENS, so the falsehood replicated itself once
#     per detection.
#
#   · `.githooks/pre-push` (twice, header and scope section) said `test-hub.yml` "declares
#     `on: pull_request`" and that Actions "is the one that decides the merge". That is the
#     dangerous direction: it describes the local gate as a redundant, expensive copy of
#     something already running for free, which is an argument for DELETING it, written inside
#     the file it argues against. Deleting it would leave the hub's Rust with nobody testing it
#     before a merge — since 2026-08-29 the `local-gate/hub-tests` seal is the only proof
#     `merge-pr.sh` accepts for a workspace PR. It already misled a human on 2026-09-02.
#
# WHAT IT CHECKS. Four rules, deliberately narrow. Precision over recall: a guard that cries
# wolf over ordinary prose is a guard the fleet learns to bypass, so each rule fires only on a
# shape that is unambiguously a claim.
#
#   A · TRIGGER ENUMERATIONS — inside a comment block that announces a list of triggers, every
#       bullet that STARTS with a trigger name declares that trigger. It must be in `on:`.
#   B · AFFIRMATIVE RUN CLAIMS — a sentence with a present-tense claim verb ("runs on",
#       "declares", "se dispara en"...) plus a trigger name asserts that trigger is live.
#   C · MERGE AUTHORITY — prose asserting that a workflow decides or blocks merges, when that
#       workflow has no `pull_request` trigger. Scanned over the WHOLE file, not just comments:
#       the false claim of hub#1438 lived in the alert-issue body the workflow writes.
#   F · DEAD EVENT CONDITIONS — a workflow condition that filters by an event its own `on:`
#       can never fire (hub#1443). Not prose: read off the PARSED workflow, so it sees what
#       Actions evaluates and a comment can never trip it.
#
# The subject of a claim is not assumed to be the file it appears in: the prose that lied about
# `test-hub.yml` lives in `.githooks/pre-push`. Each claim resolves to the last workflow file
# NAMED at or before it, and falls back to the containing file only when that is a workflow.
#
# Negated and historical statements are the normal way to record why a trigger left, and they
# stay legal: rules A and B skip a claim whose text is negated ("Sin `pull_request` desde...",
# "NOT `pull_request`", "No se dispara en `pull_request`"). What is NOT legal is the present
# tense describing something that is not true today.
#
# The workflows are parsed as YAML (never grepped) and both the scanned files and the workflow
# directory are parameters, so the guard can be PROVEN to catch the positive: copy the tree,
# put a false claim back, run this against the copy, watch it fail naming that line.
#
#   scripts/tests/ci-prose-matches-triggers.test.sh [--workflows-dir DIR] [--file PATH]...

set -uo pipefail

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repo_root=$(CDPATH= cd -- "$script_dir/../.." && pwd)

workflows_dir="$repo_root/.github/workflows"
files=()

while [ $# -gt 0 ]; do
    case "$1" in
        --workflows-dir) workflows_dir="$2"; shift 2 ;;
        --file) files+=("$2"); shift 2 ;;
        *) printf 'usage: %s [--workflows-dir DIR] [--file PATH]...\n' "$0" >&2; exit 2 ;;
    esac
done

if [ ${#files[@]} -eq 0 ]; then
    # The default surface: every workflow, plus the local gate — the file that lied about
    # another workflow, and the reason the subject of a claim cannot be assumed to be the file.
    while IFS= read -r f; do files+=("$f"); done < <(find "$workflows_dir" -maxdepth 1 -name '*.yml' | sort)
    files+=("$repo_root/.githooks/pre-push")
fi

# A YAML parser is REQUIRED, never optional: a guard that degrades to "skipped" when a tool is
# missing is the same mute green this file exists to abolish.
if ! python3 -c 'import yaml' 2>/dev/null; then
    printf 'FAIL: python3 with PyYAML is required (apt: python3-yaml)\n' >&2
    exit 1
fi

WORKFLOWS_DIR="$workflows_dir" FILES=$(printf '%s\n' "${files[@]}") python3 - <<'PY'
import os
import re
import sys

import yaml

workflows_dir = os.environ["WORKFLOWS_DIR"]
files = [f for f in os.environ["FILES"].split("\n") if f]

TRIGGERS = [
    "pull_request_target", "repository_dispatch", "workflow_dispatch",
    "workflow_call", "pull_request", "schedule", "push",
]

failures = []
passed = 0


def check(name, ok, detail=""):
    global passed
    if ok:
        passed += 1
    else:
        failures.append(f"{name}{': ' + detail if detail else ''}")


# ── The ground truth: what each workflow REALLY declares ─────────────────────────────
real = {}
for name in sorted(os.listdir(workflows_dir)):
    if not name.endswith((".yml", ".yaml")):
        continue
    with open(os.path.join(workflows_dir, name), encoding="utf-8") as fh:
        doc = yaml.safe_load(fh)
    # YAML 1.1 turns the bare key `on` into the boolean True — the classic Actions gotcha.
    on = doc.get("on", doc.get(True)) if isinstance(doc, dict) else None
    if isinstance(on, dict):
        real[name] = set(on)
    elif isinstance(on, list):
        real[name] = set(on)
    elif isinstance(on, str):
        real[name] = {on}
    else:
        real[name] = set()

check("the workflow directory parses and declares triggers", bool(real),
      f"no workflows found under {workflows_dir}")

BACKTICKED = re.compile(r"`([^`]+)`")
WORKFLOW_NAME = re.compile(r"([A-Za-z0-9._-]+\.ya?ml)")
# A bullet in these headers is `·`, `-` or `*`; the trigger may or may not be backticked.
BULLET = re.compile(r"^\s*[·*-]\s+`?(" + "|".join(TRIGGERS) + r")`?")
ENUM_HEADING = re.compile(r"disparador|trigger", re.IGNORECASE)

# Present-tense assertions that a trigger is live. Kept short on purpose — every entry has to
# be a verb that only makes sense as a claim about what runs TODAY.
CLAIM_VERB = re.compile(
    r"\b(runs?\s+on|running\s+on|run\s+there|triggers?\s+on|fires?\s+on|declares?|"
    r"is\s+triggered\s+by|corren?\s+en|se\s+dispara\s+en|dispara\s+en|va\s+por)\b",
    re.IGNORECASE,
)
# Negation/history markers. A claim carrying one is a record of why something left, not an
# assertion that it is there.
NEGATED = re.compile(
    r"\b(not|no|never|without|sin|nunca|ya\s+no|no\s+longer|dejó\s+de|hasta|until|"
    r"en\s+vez\s+de|instead\s+of|used\s+to)\b",
    re.IGNORECASE,
)
# Phrases that assert a workflow is the PRE-MERGE gate. `manda para mergear` is here because
# it is what `test-hub.yml` said about itself for four days after pm#197 took its
# `pull_request` away, and the first two rules had no way to see it: no trigger name in the
# sentence, no claim verb — just the authority, asserted directly.
MERGE_AUTHORITY = re.compile(
    r"(decides?\s+the\s+merge|blocks?\s+the\s+merge|gates?\s+the\s+merge|"
    r"condición\s+de\s+mergeo|puede[n]?\s+mergear|bloquea\s+el\s+merge|"
    r"decide\s+el\s+merge|impide\s+mergear|manda\s+para\s+(el\s+)?merge)",
    re.IGNORECASE,
)


def triggers_in(text):
    """Trigger names mentioned inside backticks — `push`, `on: pull_request`, `schedule:`."""
    found = []
    for span in BACKTICKED.findall(text):
        for t in TRIGGERS:
            if re.search(r"(?:^|[^a-z_])" + t + r"(?:$|[^a-z_])", span) and t not in found:
                found.append(t)
    return found


def comment_blocks(lines):
    """Maximal runs of comment lines. Yields (block_lines) where each is (lineno, text)."""
    block = []
    for i, raw in enumerate(lines, 1):
        s = raw.strip()
        if s.startswith("#"):
            block.append((i, re.sub(r"^#\s?", "", s)))
        else:
            if block:
                yield block
            block = []
    if block:
        yield block


def paragraphs(block):
    """Split a block on blank comment lines; join wrapped lines into one string."""
    para, out = [], []
    for lineno, text in block:
        if not text.strip():
            if para:
                out.append(para)
            para = []
        else:
            para.append((lineno, text))
    if para:
        out.append(para)
    return out


def block_is_enumeration(block):
    """Is this comment block a list of triggers, so rule A applies to its bullets?

    By WORDING or by SHAPE, and the second half is what makes the detector survive an edit
    (hub#1445). Keying only on the heading meant that rewording it — «Los CUATRO disparadores»
    → «Las CUATRO vías de entrada» — switched rule A off for the whole block, without a word,
    and hub#1442 rewrote exactly that heading. Two or more bullets each STARTING with a trigger
    name is not something ordinary prose does; one is (`· \\`push\\` es lo que usamos para
    desplegar`), which is why the threshold is two and not one.
    """
    if ENUM_HEADING.search(" ".join(t for _, t in block)):
        return True
    return sum(1 for _, t in block if BULLET.match(t)) >= 2


SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


def resolve(default_file, named_before, *scopes):
    """The workflow a claim is ABOUT, narrowest scope first.

    A name in the sentence wins, then one anywhere in the same paragraph — `test-hub.yml`
    introduces a paragraph with "Los corre `test-hub-modules.yml`" and then says "Va por
    `schedule`", and that `schedule` is the other workflow's, not its own.

    Only then the file itself, because a claim written INSIDE a workflow is about that
    workflow. Falling back to "the last workflow named earlier in the block" ahead of self made
    the `test-hub-modules.yml` header describe `test-hub.yml`, which its first paragraph merely
    mentions. A file that is NOT a workflow (`.githooks/pre-push`) has no default subject, so
    there the nearest workflow named above is the best answer available.
    """
    for scope in scopes:
        for n in reversed(WORKFLOW_NAME.findall(scope)):
            if n in real:
                return n
    base = os.path.basename(default_file)
    if base in real:
        return base
    return named_before if named_before in real else None


# Clause splitting, so a negation binds only to its own clause. The sentence that lied about
# `test-hub.yml` also contained an unrelated "not" ("whose minutes are not billed"), which at
# sentence level masked the claim entirely.
BACKTICK_SPAN = re.compile(r"`[^`]*`")


def clauses(sentence):
    holes = []

    def stash(m):
        holes.append(m.group(0))
        return f"\x00{len(holes) - 1}\x00"

    masked = BACKTICK_SPAN.sub(stash, sentence)
    parts = re.split(r"[,;]|\s—\s", masked)
    return [re.sub(r"\x00(\d+)\x00", lambda m: holes[int(m.group(1))], p) for p in parts]


for path in files:
    if not os.path.exists(path):
        check(f"{path} exists", False, "no such file")
        continue
    base = os.path.basename(path)
    with open(path, encoding="utf-8") as fh:
        raw = fh.read()
    lines = raw.split("\n")

    for block in comment_blocks(lines):
        is_enum = block_is_enumeration(block)
        named_before = None

        for para in paragraphs(block):
            first_line = para[0][0]
            joined = " ".join(t.strip() for _, t in para)

            # ── A · a bullet inside a trigger enumeration DECLARES that trigger ──────
            m = BULLET.match(para[0][1])
            if is_enum and m and not NEGATED.match(para[0][1].strip()):
                trig = m.group(1)
                target = resolve(path, named_before, joined)
                if target:
                    check(
                        f"{base}:{first_line} enumerates `{trig}` and {target} declares it",
                        trig in real[target],
                        f"the header lists `{trig}` as a live trigger of {target}, whose real "
                        f"`on:` is {sorted(real[target])} — an enumeration that documents a "
                        f"trigger nobody removed from the prose",
                    )

            # ── B · an affirmative, present-tense claim that a trigger is live ───────
            for sentence in SENTENCE_SPLIT.split(joined):
                for n in WORKFLOW_NAME.findall(sentence):
                    if n in real:
                        named_before = n
                for clause in clauses(sentence):
                    if not CLAIM_VERB.search(clause) or NEGATED.search(clause):
                        continue
                    trigs = triggers_in(clause)
                    if not trigs:
                        continue
                    # The subject can be named anywhere in the sentence ("so `test-hub.yml`
                    # declares..."), so resolve against the sentence, not the clause.
                    target = resolve(path, named_before, sentence, joined)
                    if not target:
                        continue
                    for trig in trigs:
                        check(
                            f"{base}:{first_line} claims {target} runs on `{trig}`, and it does",
                            trig in real[target],
                            f"prose asserts `{trig}` is a live trigger of {target}, whose real "
                            f"`on:` is {sorted(real[target])} — rewrite it in the past, dated, "
                            f"or drop it",
                        )

    # ── C · merge authority, over the WHOLE file (the alert-issue body is prose too) ──
    named_before = None
    for i, line in enumerate(lines, 1):
        for n in WORKFLOW_NAME.findall(line):
            if n in real:
                named_before = n
        if not MERGE_AUTHORITY.search(line):
            continue
        target = resolve(path, named_before, line)
        if not target:
            continue
        check(
            f"{base}:{i} attributes merge authority to {target}, which runs on `pull_request`",
            "pull_request" in real[target],
            f"the text says {target} decides or blocks merges, but its `on:` is "
            f"{sorted(real[target])} — with no `pull_request` it cannot gate a PR. Since "
            f"2026-08-29 (pm#197) the pre-merge proof is the `local-gate/hub-tests` seal that "
            f"`merge-pr.sh` requires, not a cloud run",
        )

# ── D · this guard is actually RUN, and by a workflow that sees the files it guards ──
# hub#1381: a battery nobody executes is worth nothing, and hub#1365: asserting a MENTION is
# not asserting an invocation — `actionlint.yml` names this script in a comment and in `paths:`
# too, so a `grep` over the file would still pass with the step deleted. The step is read out
# of the parsed YAML; the `paths:` entries are checked separately because losing those is the
# quieter failure — the guard survives, and simply stops being triggered.
SELF = "scripts/tests/ci-prose-matches-triggers.test.sh"
runner = os.path.join(workflows_dir, "actionlint.yml")
if os.path.exists(runner):
    with open(runner, encoding="utf-8") as fh:
        rdoc = yaml.safe_load(fh)
    runs = []
    for job in (rdoc.get("jobs") or {}).values():
        for step in (job.get("steps") or []):
            if isinstance(step, dict) and step.get("run"):
                runs.append(step["run"])
    check(
        f"actionlint.yml has a STEP that runs {SELF}",
        any(SELF in r for r in runs),
        "no `run:` step invokes it — a mention in a comment or in `paths:` executes nothing",
    )
    ron = rdoc.get("on", rdoc.get(True)) or {}
    pr_paths = (ron.get("pull_request") or {}).get("paths") or []
    for needed in (SELF, ".githooks/pre-push"):
        check(
            f"actionlint.yml's `paths:` covers {needed}",
            needed in pr_paths,
            f"without it, a PR touching only {needed} never runs this guard",
        )
else:
    check("actionlint.yml exists to run this guard", False, f"missing {runner}")

# ── E · the enumeration detector reads SHAPE, not wording (hub#1445) ─────────────────
# Rule A used to apply only inside a block whose text contained "disparador"/"trigger", so
# rewriting that heading turned it off — silently, and for the WHOLE block: measured on
# `test-hub-modules.yml`, renaming «Los CUATRO disparadores» to «Las CUATRO vías de entrada»
# took the run from 11 checks to 7 and let a false `pull_request` bullet through, still
# printing "passed". A guard whose coverage depends on a word nobody knows is load-bearing is
# a guard that switches itself off during an ordinary edit — hub#1442 rewrote exactly that
# heading. The shape is the honest signal: two or more bullets that each START with a trigger
# name is not ordinary prose, whatever the heading calls itself.
ENUM_FIXTURES = [
    (
        "a heading that says «disparadores»",
        ["── Los CUATRO disparadores ──", "· `push` a `main`", "· `schedule` diario"],
        True,
    ),
    (
        "the SAME list with the heading reworded (hub#1445)",
        ["── Las CUATRO vías de entrada ──", "· `push` a `main`", "· `schedule` diario"],
        True,
    ),
    (
        "ordinary prose that merely mentions a trigger in a bullet",
        ["Notas sueltas:", "· `push` es lo que usamos para desplegar."],
        False,
    ),
    (
        "a single bullet, which stays ordinary prose",
        ["Detalle:", "· `push` a `main`/`develop`: la red POST-MERGE."],
        False,
    ),
]
for label, body, want in ENUM_FIXTURES:
    got = block_is_enumeration(list(enumerate(body, 1)))
    check(
        f"enumeration detector: {label} → {'enumeration' if want else 'plain prose'}",
        got == want,
        f"detector said {got}, expected {want} — rule A "
        f"{'stops covering' if want else 'starts firing on'} this block",
    )

# ── F · DEAD EVENT CONDITIONS — an expression that names an event the `on:` cannot fire ──
# hub#1443: the prose rules above only read comments, so a CONDITION that filters by an
# impossible event was invisible to them. `test-hub.yml`, `test-hub-modules.yml` and
# `test-web.yml` all carried
#
#     if: github.event_name != 'pull_request' || !github.event.pull_request.draft
#
# after pm#197/hub#1352 took `pull_request` out of their `on:`. With no `pull_request` trigger
# the first half is ALWAYS true, so the whole condition is constant and the draft optimisation
# it documents never runs — while the file still reads as if the workflow gated PRs and skipped
# drafts. Same family as hub#1438, but in behaviour instead of prose.
#
# Narrow on purpose, like every rule here. Only two shapes are unambiguous:
#   · a comparison of `github.event_name` against a trigger name, and
#   · a read of a payload root that a single family of events produces.
# `github.event.inputs`, `head_commit` and friends are ambiguous and stay out: a guard that
# cries wolf is a guard the fleet learns to bypass.
EVENT_NAME_CMP = re.compile(r"github\.event_name\s*(?:==|!=)\s*'([a-z_]+)'")
PAYLOAD_ROOT = {
    "pull_request": {"pull_request", "pull_request_target"},
    "client_payload": {"repository_dispatch"},
}
PAYLOAD_ACCESS = re.compile(r"github\.event\.(" + "|".join(PAYLOAD_ROOT) + r")\b")


def yaml_strings(node):
    """Every string scalar of a parsed workflow — `if:`, `${{ }}` interpolations, `run:` bodies.

    Read off the PARSED document, never the raw text, so a comment discussing a trigger can
    never trip this rule: only what Actions actually evaluates counts.
    """
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for k, v in node.items():
            yield from yaml_strings(k)
            yield from yaml_strings(v)
    elif isinstance(node, list):
        for v in node:
            yield from yaml_strings(v)


def dead_event_conditions(triggers, doc):
    """(needed event, offending text) for every condition this `on:` can never satisfy."""
    if "workflow_call" in triggers:
        # A reusable workflow evaluates under the CALLER's event, so its own `on:` proves
        # nothing about which events reach it.
        return []
    dead = []
    for expr in yaml_strings(doc):
        for name in EVENT_NAME_CMP.findall(expr):
            if name in TRIGGERS and name not in triggers:
                dead.append((name, f"github.event_name compared with '{name}'"))
        for root in PAYLOAD_ACCESS.findall(expr):
            if not PAYLOAD_ROOT[root] & triggers:
                dead.append((root, f"github.event.{root} read"))
    return dead


for name in sorted(real):
    path = os.path.join(workflows_dir, name)
    with open(path, encoding="utf-8") as fh:
        raw_lines = fh.read().split("\n")
    doc = yaml.safe_load("\n".join(raw_lines))
    seen = set()
    for needed, what in dead_event_conditions(real[name], doc):
        if (needed, what) in seen:
            continue
        seen.add((needed, what))
        # The line is looked up only to point at it; the finding itself came from the parsed
        # document, so a comment mentioning the same text cannot be what is reported.
        where = next(
            (
                str(i)
                for i, line in enumerate(raw_lines, 1)
                if not line.strip().startswith("#")
                and (
                    EVENT_NAME_CMP.search(line) and needed in line
                    or PAYLOAD_ACCESS.search(line) and needed in line
                )
            ),
            "?",
        )
        check(
            f"{name}:{where} filters by `{needed}`, and its `on:` can fire it",
            False,
            f"{what} but the `on:` of {name} is {sorted(real[name])} — the condition is "
            f"constant, so the branch it guards never runs while the file reads as if it "
            f"did. Delete it, or bring the trigger back with it",
        )
    if not seen:
        # One green line per clean workflow: the rule has to be visibly RUNNING over each
        # file, not only visible when it fires.
        check(f"{name} has no condition filtering by an event it never receives", True)

# ── F fixtures · the rule fires on the shape it exists for, and only on it ───────────
# Same reason as rule E: a detector nobody proves is a detector that can quietly stop
# detecting. Each fixture is (label, `on:` triggers, workflow body, expected findings).
DEAD_EVENT_FIXTURES = [
    (
        "the hub#1443 shape: a draft filter on a workflow without `pull_request`",
        {"push"},
        {"jobs": {"t": {"if": "github.event_name != 'pull_request' "
                              "|| !github.event.pull_request.draft"}}},
        2,
    ),
    (
        "the same condition where `pull_request` IS a trigger",
        {"push", "pull_request"},
        {"jobs": {"t": {"if": "github.event_name != 'pull_request' "
                              "|| !github.event.pull_request.draft"}}},
        0,
    ),
    (
        "a reusable workflow, which runs under the caller's event",
        {"workflow_call"},
        {"jobs": {"t": {"if": "github.event_name != 'pull_request'"}}},
        0,
    ),
    (
        "`client_payload` read by a workflow that declares `repository_dispatch`",
        {"repository_dispatch", "push"},
        {"jobs": {"t": {"steps": [{"run": "echo ${{ github.event.client_payload.module }}"}]}}},
        0,
    ),
    (
        "`client_payload` read by a workflow that does not",
        {"push"},
        {"jobs": {"t": {"steps": [{"run": "echo ${{ github.event.client_payload.module }}"}]}}},
        1,
    ),
    (
        "an ordinary condition on a trigger the file really has",
        {"push", "schedule"},
        {"jobs": {"t": {"steps": [{"with": {"ref": "${{ github.event_name == 'schedule' "
                                                   "&& 'develop' || github.ref }}"}}]}}},
        0,
    ),
]
for label, triggers, body, want in DEAD_EVENT_FIXTURES:
    got = len(dead_event_conditions(triggers, body))
    check(
        f"dead-event detector: {label} → {want} finding(s)",
        got == want,
        f"detector found {got}, expected {want} — rule F "
        f"{'stops covering' if want else 'starts firing on'} this shape",
    )

for f in failures:
    print(f"  ✗ {f}")
print(f"\n{passed} passed, {len(failures)} failed")
sys.exit(1 if failures else 0)
PY
