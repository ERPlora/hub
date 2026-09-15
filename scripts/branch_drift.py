#!/usr/bin/env python3
"""Signal for the `develop` → `main` drift of this repo, and for a batch that landed FLATTENED
(hub#1878).

`main` is the branch that deploys: a push to it publishes `ghcr.io/erplora/hub:latest`, which is
what the fleet runs and what a new hub starts on. So everything sitting in `develop` is finished
work with **zero effect for any customer**, and it is worth measuring.

But the fault this was ported for is the other one, the quiet one. A release batch merged with
`--squash` past `merge-pr.sh` breaks nothing anybody can see: CI passes, the content really does
reach production, and the board marks the work done. The only casualty is the SHAPE of the
history — `main` stops descending from `develop` — and nothing was looking at the shape. All 15
promotions between 2026-08-30 and 2026-09-13 landed with one parent and nobody noticed for two
weeks; the bill arrived as hub#1876, a release PR reported CONFLICTING in 12 files that were not
real conflicts. The danger is not the conflict: it is that resolving one in a hurry "in favour of
develop" overwrites whatever the other side really had.

GitHub cannot be asked to refuse the squash — rulesets and branch protection are paywalled on
private repos with the org on Free — so this catches it the day it happens instead of letting the
next release trip over it.

Three measurements, and an issue only where an issue makes sense:

  - `main..develop` — finished work not deployed yet. Keeps one issue, refreshed while it lasts
    and closed by itself when the batch ships. A job that opened a new issue every morning would
    be noise, and noise stops being read.
  - `develop..main` — a hotfix that went into `main` and never came back. If it does not return,
    the next batch silently reverts it in production.
  - the SHAPE of the last batch — flattened or not. This one opens no issue: it makes the job
    FAIL with its own exit code (4), because it is not a backlog to work through, it is a history
    to repair before the next release.

Usage (see `.github/workflows/develop-main-drift.yml`):

    python3 scripts/branch_drift.py --repo ERPlora/hub      # measure and sync the issues
    python3 scripts/branch_drift.py --dry-run               # measure and print, touch nothing

Stdlib only, on purpose: the signal must not depend on resolving this repo's toolchains (Rust,
pnpm) to say whether the history is sound.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

# Two days of work, from both sides — either threshold alone is enough to fire.
#
# 60 is this repo's two days, not a number copied from elsewhere: measured over the 30 days to
# 2026-09-15, `develop` takes a median of ~15 commits/day, and its busiest single day was 45
# (2026-08-29). A threshold of 40 — the one `saas` uses for its own, slower pace — would go off
# on an ordinary big day here, and a guard that cries wolf is the one everybody learns to skip.
# Raising or lowering these is a policy change: record the measurement that justifies it here
# too, or the number becomes folklore.
DEFAULT_MAX_COMMITS = 60
DEFAULT_MAX_AGE_DAYS = 2.0

# Identifies the signal's own issue across runs. It lives in the body (invisible when rendered)
# instead of in the title, so retitling the issue by hand never orphans it.
MARKER = "<!-- erplora:develop-main-drift -->"
ISSUE_TITLE = "Hay trabajo terminado que no está en producción: `main` se ha quedado atrás de `develop`"
ISSUE_LABELS = ("prio:P1", "area:ci-cd")
# The label is also how the issue is FOUND again (see `GhIssues.find_open`): scanning a label is
# deterministic, while searching the body depends on GitHub's search index catching up — and a
# stale index means a duplicate issue every morning.
LOOKUP_LABEL = "area:ci-cd"

# Exit code of "I could not measure": the ref is not in this checkout. It is NOT 1, because a run
# that measured nothing must never be read as a run that found nothing.
EXIT_MISSING_REF = 3
# Its own code, distinct from 0, from 1 and from a missing ref: a flattened batch is neither "I
# could not measure" nor a generic failure — it is a finding, and whoever reads the job has to be
# able to tell them apart without opening the log.
EXIT_FLATTENED_BATCH = 4

CLOSE_COMMENT = (
    "El lote ya está en `main`: la deriva ha vuelto por debajo del umbral. "
    "Se cierra sola; volverá a abrirse si el hueco crece otra vez."
)

# `main` → `develop`: a hotfix that never came back. ZERO commits allowed (`>` threshold, so one
# commit fires) once it is a day old — the return PR is part of merging the hotfix, not a chore
# for later.
DEFAULT_RETURN_MAX_COMMITS = 0
DEFAULT_RETURN_MAX_AGE_DAYS = 1.0
RETURN_MARKER = "<!-- erplora:main-develop-unreturned -->"
RETURN_ISSUE_TITLE = "Un arreglo urgente vive solo en `main`: el próximo lote lo va a borrar de producción"
RETURN_CLOSE_COMMENT = (
    "`develop` ya contiene cuanto hay en `main`: el hotfix ha vuelto. "
    "Se cierra sola; volverá a abrirse si aparece otro sin retorno."
)


class MissingRefError(RuntimeError):
    """One of the two refs to compare does not exist in this checkout.

    Raised instead of letting a raw `CalledProcessError` out: git's own `fatal: ambiguous
    argument 'origin/develop'` plus a traceback tells whoever opens the red log nothing about what
    to do, and an unmeasurable range looks exactly like an empty one in the output.
    """

    def __init__(self, ref: str):
        self.ref = ref
        branch = ref.removeprefix("origin/")
        super().__init__(
            f"missing ref {ref} in checkout — fetch it before measuring: "
            f"git fetch origin {branch}:refs/remotes/origin/{branch}"
        )


@dataclass(frozen=True)
class Drift:
    """What git says: how much work is waiting, and since when."""

    commits: int
    oldest_commit_at: datetime | None
    oldest_commit_subject: str = ""


@dataclass(frozen=True)
class Verdict:
    drifting: bool
    reasons: tuple[str, ...]
    commits: int
    age_days: float
    oldest_commit_subject: str
    max_commits: int
    max_age_days: float


def evaluate(
    drift: Drift,
    *,
    now: datetime,
    max_commits: int = DEFAULT_MAX_COMMITS,
    max_age_days: float = DEFAULT_MAX_AGE_DAYS,
) -> Verdict:
    """Turns a measurement into a verdict. Either threshold alone is enough to fire.

    Both are needed: sixty commits from this morning are a busy day here, and one commit stuck
    for a week is not — neither threshold catches the other's case.
    """
    age_days = 0.0
    if drift.oldest_commit_at is not None:
        age_days = (now - drift.oldest_commit_at).total_seconds() / 86400

    reasons: list[str] = []
    if drift.commits > max_commits:
        reasons.append(f"{drift.commits} commits sin desplegar (umbral: {max_commits})")
    if age_days > max_age_days:
        reasons.append(
            f"el commit más antiguo lleva {age_days:.1f} días esperando (umbral: {max_age_days:g})"
        )

    return Verdict(
        drifting=bool(reasons),
        reasons=tuple(reasons),
        commits=drift.commits,
        age_days=age_days,
        oldest_commit_subject=drift.oldest_commit_subject,
        max_commits=max_commits,
        max_age_days=max_age_days,
    )


def _git_env() -> dict[str, str]:
    """The environment every git call below runs with, with `GIT_*` stripped.

    `git -C <path>` does NOT override `GIT_DIR`/`GIT_WORK_TREE` — the environment wins. Run from
    anything that exports them (a git hook does), these would silently measure the CALLER's
    repository instead of the one asked for, and report a drift that is not this one's.
    """
    return {
        key: value for key, value in os.environ.items() if not key.startswith("GIT_")
    }


def _require_refs(repo_path, refs, *, env) -> None:
    """Both refs must resolve BEFORE anything is compared.

    With a ref missing, `git diff` exits 128 exactly like "there are differences" and
    `git merge-tree`/`git log` blow up with a raw `CalledProcessError`. Checking first is what
    turns "I could not measure" into an actionable line instead of a mute alarm.
    """
    for ref in refs:
        resolved = subprocess.run(
            [
                "git",
                "-C",
                str(repo_path),
                "rev-parse",
                "--verify",
                "--quiet",
                f"{ref}^{{commit}}",
            ],
            capture_output=True,
            text=True,
            env=env,
        )
        if resolved.returncode != 0:
            raise MissingRefError(ref)


def measure(repo_path, *, base: str = "main", head: str = "develop") -> Drift:
    """Reads `base..head` out of git.

    The age comes from the OLDEST waiting commit and from its **committer** date. `git log` walks
    newest-first, so the first line would always look fresh; and the author date survives rebases
    and squashes, so it answers "when was this written", not "how long has it been sitting on this
    branch unshipped" — which is the actual question.
    """
    env = _git_env()
    _require_refs(repo_path, (base, head), env=env)

    # FIRST: is the content already deployed? If the two trees are identical there is NO drift,
    # however many commits `git rev-list` counts. A batch that landed squashed leaves the commits
    # of `develop` as non-ancestors forever, so the counter would keep saying 6, 11, 40… and this
    # signal would open a false drift issue two days after EVERY such batch — exactly the noise it
    # exists not to produce.
    if (
        subprocess.run(
            ["git", "-C", str(repo_path), "diff", "--quiet", base, head], env=env
        ).returncode
        == 0
    ):
        return Drift(commits=0, oldest_commit_at=None)

    out = subprocess.run(
        [
            "git",
            "-C",
            str(repo_path),
            "log",
            "--reverse",
            "--format=%cI%x1f%s",
            f"{base}..{head}",
        ],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    ).stdout
    lines = [line for line in out.splitlines() if line.strip()]
    if not lines:
        return Drift(commits=0, oldest_commit_at=None)

    timestamp, _, subject = lines[0].partition("\x1f")
    return Drift(
        commits=len(lines),
        oldest_commit_at=datetime.fromisoformat(timestamp),
        oldest_commit_subject=subject,
    )


def measure_unreturned(
    repo_path, *, develop: str = "develop", main: str = "main"
) -> Drift:
    """Reads what `main` carries that `develop` does not — by CONTENT, not by ancestry.

    The count `develop..main` alone cannot be the signal: every batch that landed squashed leaves
    a commit on `main` that `develop` has no ancestor for, while its content is already there. So
    the probe is a merge: if merging `main` into `develop` would leave `develop`'s tree untouched,
    nothing is missing. `git merge-tree --write-tree` answers that without touching the working
    tree; a conflict (exit 1) means `main` carries something different, and that IS the case to
    report.
    """
    env = _git_env()
    _require_refs(repo_path, (develop, main), env=env)
    git = ["git", "-C", str(repo_path)]

    merged = subprocess.run(
        [*git, "merge-tree", "--write-tree", develop, main],
        capture_output=True,
        text=True,
        env=env,
    )
    if merged.returncode > 1:
        raise RuntimeError(f"git merge-tree failed: {merged.stderr.strip()}")
    if merged.returncode == 0:
        develop_tree = subprocess.run(
            [*git, "rev-parse", f"{develop}^{{tree}}"],
            check=True,
            capture_output=True,
            text=True,
            env=env,
        ).stdout.strip()
        if merged.stdout.strip().splitlines()[0] == develop_tree:
            return Drift(commits=0, oldest_commit_at=None)

    out = subprocess.run(
        [*git, "log", "--reverse", "--format=%cI%x1f%s", f"{develop}..{main}"],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    ).stdout
    lines = [line for line in out.splitlines() if line.strip()]
    if not lines:
        return Drift(commits=0, oldest_commit_at=None)
    timestamp, _, subject = lines[0].partition("\x1f")
    return Drift(
        commits=len(lines),
        oldest_commit_at=datetime.fromisoformat(timestamp),
        oldest_commit_subject=subject,
    )


@dataclass(frozen=True)
class FlattenedBatch:
    """A release batch that reached `main` WITHOUT keeping `develop` as an ancestor."""

    main_sha: str
    develop_sha: str
    develop_subject: str


def measure_flattened_batch(
    repo_path, *, main: str = "main", develop: str = "develop", window: int = 500
):
    """Did the last release batch land on `main` FLATTENED? Returns the batch, or ``None``.

    The invariant a release must keep is one line long: **`main` has to descend from the `develop`
    commit whose content it carries.** A squash hands `main` a brand-new sha with no parent link,
    so it does not — and from then on git 3-ways every future batch against an ever-older common
    base and reports the same change under two shas as a conflict. It gets worse with every
    release (pm#111).

    That is not theory, it is this repo's last fortnight. The 15 promotions from 2026-08-30 to
    2026-09-13 all landed with one parent, the common base stayed pinned at `3d8359fa` (29/08),
    and hub#1876 came out CONFLICTING in 12 files that were the same change wearing two shas.

    `merge-pr.sh` already refuses to flatten this shape — it has merged batches with `--merge`
    since 2026-08-16 — and those 15 went in past it, from the GitHub button or
    `gh pr merge --squash`. What the script cannot do is stop that, so the flattening is caught
    here.

    **The probe is the tree, not the commit count.** After a squash the counters never reach zero,
    so they cannot tell a flattened batch from an ordinary one; the tree can. Find the commit
    reachable from `develop` whose tree `main` is serving, then ask whether `main` descends from
    it:

    - not an ancestor → the batch was flattened (what this reports);
    - an ancestor → a healthy merge, silence;
    - no commit of `develop` has that tree → `main` carries something of its own. That is an
      unreturned hotfix, a different fault with its own signal (:func:`measure_unreturned`);
      reporting it here would fire on every hotfix and teach everyone to ignore this.

    ⚠️ It measures repos whose `main` INTEGRATES `develop`, which this one does: `main` has a root
    commit of its own and shares history with `develop` up to `3d8359fa`, and `125da1ac` is a real
    two-parent merge. The belief that the Hub's `main` is an ORPHAN branch promoted with
    `commit-tree` — still written in `scripts/image-tags.sh`, and repeated in `saas`'s copy of
    this file as the reason not to port it here — was a shallow-clone artefact, as hub#1877
    established with the full history. It changes nothing about what `image-tags.sh` does (it
    numbers by the tags the repository HOLDS, not by what is reachable from `develop`), but it is
    why this guard took two weeks to arrive.
    """
    env = _git_env()
    _require_refs(repo_path, (main, develop), env=env)
    git = ["git", "-C", str(repo_path)]

    main_sha, main_tree = subprocess.run(
        [*git, "rev-parse", main, f"{main}^{{tree}}"],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    ).stdout.split()

    out = subprocess.run(
        [*git, "log", f"--max-count={window}", "--format=%H%x1f%T%x1f%s", develop],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    ).stdout

    for line in out.splitlines():
        if not line.strip():
            continue
        sha, tree, subject = line.split("\x1f", 2)
        if tree != main_tree:
            continue
        descends = (
            subprocess.run(
                [*git, "merge-base", "--is-ancestor", sha, main], env=env
            ).returncode
            == 0
        )
        return (
            None
            if descends
            else FlattenedBatch(
                main_sha=main_sha, develop_sha=sha, develop_subject=subject
            )
        )
    return None


def render_return_issue_body(verdict: Verdict) -> str:
    """Body of the unreturned-hotfix issue.

    Spanish, and in the shape every issue of this org takes since 2026-09-04: the problem in plain
    language first (`## Qué pasa`), then what to do about it (`## Propuesta`), and only then the
    numbers (`## Detalle técnico`).
    """
    reasons = (
        "\n".join(f"- {reason}" for reason in verdict.reasons)
        or "- (sin hotfix pendiente)"
    )
    waiting = verdict.oldest_commit_subject or "(desconocido)"
    return f"""{RETURN_MARKER}
## Qué pasa

Alguien arregló algo urgente directamente en `main` —la rama que despliega la imagen de la
flota— y ese arreglo **no ha vuelto a `develop`**. Mientras siga así, el próximo lote
`develop` → `main` lo **revierte en producción** sin que nadie lo vea: el fallo que se arregló
esta mañana vuelve esta noche.

## Propuesta

1. Abrir la PR de vuelta: `gh pr create --base develop --head main`.
2. Mergearla con `./pm/merge-pr.sh hub <nº PR>` — nunca `gh pr merge` a pelo.

## Detalle técnico

{reasons}

- Commits en `main` sin retorno: **{verdict.commits}**
- El más antiguo lleva **{verdict.age_days:.1f} días** y es: `{waiting}`

La medida es por CONTENIDO, no por ascendencia (`git merge-tree --write-tree`): contar commits
mentiría, porque cada lote que entró aplastado deja en `main` un commit del que `develop` no
desciende aunque su contenido ya esté allí.

Esta issue la mantiene `scripts/branch_drift.py` y **se cierra sola** cuando `develop` recupera
lo que hay en `main`.
"""


def render_issue_body(verdict: Verdict) -> str:
    """The drift issue body — same shape, same reason."""
    reasons = "\n".join(f"- {reason}" for reason in verdict.reasons) or "- (sin deriva)"
    waiting = verdict.oldest_commit_subject or "(desconocido)"
    return f"""{MARKER}
## Qué pasa

`main` es la rama que despliega: al mergear en ella se publica `ghcr.io/erplora/hub:latest`, que
es la imagen que corre la flota y con la que arranca un hub nuevo. Lo que está en `develop` y no
en `main` es trabajo **terminado y cerrado con efecto cero para cualquier cliente** — incluida
cualquier issue que se diera por hecha al mergearla.

## Propuesta

1. Abrir la PR `develop` → `main`.
2. Mergearla con `./pm/merge-pr.sh hub <nº PR>` — **nunca** `gh pr merge` a pelo: el script
   espera al gate, solo mergea en verde (pm#58/#60) y **no aplasta el lote**, que es lo que
   rompió la historia entre el 30/08 y el 13/09 (hub#1876/#1877).
3. Comprobar que la imagen salió: workflow `Build Hub Image (latest)`.

## Detalle técnico

{reasons}

- Commits esperando: **{verdict.commits}**
- El más antiguo lleva **{verdict.age_days:.1f} días** y es: `{waiting}`
- Umbrales: {verdict.max_commits} commits o {verdict.max_age_days:g} días — lo que llegue antes.

Esta issue la mantiene `scripts/branch_drift.py` y **se cierra sola** cuando el lote sale.
"""


def sync_issue(
    verdict,
    *,
    title: str,
    body: str,
    issues,
    marker: str = MARKER,
    close_comment: str = CLOSE_COMMENT,
    labels: Sequence[str] = ISSUE_LABELS,
) -> str:
    """Keeps exactly one issue (found by `marker`) in sync with the verdict. Returns what it did.

    `verdict` only has to expose `.drifting` and `issues` only the four calls below, which is what
    lets the second signal reuse this instead of writing the open/refresh/close rule again.
    `labels` is a parameter for the same reason — the rule is what must not be written twice, the
    labels are per-signal.
    """
    number = issues.find_open(marker)

    if verdict.drifting:
        if number is None:
            issues.create(title, body, list(labels))
            return "opened"
        issues.update(number, title, body)
        return "updated"

    if number is None:
        return "noop"
    issues.close(number, close_comment)
    return "closed"


class GhIssues:
    """`gh issue` behind the four calls `sync_issue` needs. `run` is the test seam."""

    def __init__(self, repo: str, run=None, lookup_label: str = LOOKUP_LABEL):
        self.repo = repo
        self._run = run or self._gh
        self.lookup_label = lookup_label

    @staticmethod
    def _gh(args: list[str]) -> str:
        return subprocess.run(
            ["gh", *args], check=True, capture_output=True, text=True
        ).stdout

    def find_open(self, marker: str) -> int | None:
        query = ["issue", "list", "--repo", self.repo, "--state", "open"]
        query += [
            "--label",
            self.lookup_label,
            "--limit",
            "100",
            "--json",
            "number,body",
        ]
        raw = self._run(query)
        for issue in json.loads(raw or "[]"):
            if marker in (issue.get("body") or ""):
                return issue["number"]
        return None

    def create(self, title: str, body: str, labels: list[str]) -> None:
        args = [
            "issue",
            "create",
            "--repo",
            self.repo,
            "--title",
            title,
            "--body",
            body,
        ]
        for label in labels:
            args += ["--label", label]
        self._run(args)

    def update(self, number: int, title: str, body: str) -> None:
        self._run(
            [
                "issue",
                "edit",
                str(number),
                "--repo",
                self.repo,
                "--title",
                title,
                "--body",
                body,
            ]
        )

    def close(self, number: int, comment: str) -> None:
        self._run(
            ["issue", "close", str(number), "--repo", self.repo, "--comment", comment]
        )


def _print_flattened(flattened: FlattenedBatch, *, base: str, head: str) -> None:
    """Says the finding out loud, with the repair that actually worked here (hub#1877).

    A red exit code nobody can act on is half a guard, and the recipe is not obvious: the fix is a
    merge that registers the ancestry WITHOUT changing a single line of content.
    """
    print()
    print(f"  ❌ el lote de release entró APLASTADO en `{base}`:")
    print(
        f"     {base} = {flattened.main_sha[:8]} lleva el árbol de {flattened.develop_sha[:8]}"
    )
    print(f"     ({flattened.develop_subject})")
    print(
        "     …pero NO desciende de él, así que el SIGUIENTE lote conflictará contra una"
    )
    print(
        "     base cada vez más vieja, y ahí un conflicto mal resuelto pisa a otro worker."
    )
    print()
    print(
        "     Se repara con un retro-merge que registre la ascendencia SIN cambiar contenido"
    )
    print("     (es lo que hizo hub#1877, con el árbol verificado antes de mergear):")
    print(f"       git switch -c chore/retro-merge-main-into-develop {head}")
    print(
        f"       git merge -s ours --no-commit {base}   # el árbol queda EXACTAMENTE el de {head}"
    )
    print(
        f"       git diff --quiet {head} && git commit  # y no se commitea sin comprobarlo"
    )
    print(
        f"     La PR va contra `{head}` y se mergea SIN squash: lleva un merge commit cuyo 2.º"
    )
    print(f"     padre es `{base}`, y aplastarla borraría el único enlace que aporta.")
    print(
        "     El lote se mergea SOLO con merge-pr.sh: fue saltárselo lo que produjo esto."
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo", default="ERPlora/hub", help="owner/name donde vive la issue-señal"
    )
    parser.add_argument("--repo-path", default=".", help="checkout de git a medir")
    parser.add_argument("--base", default="origin/main")
    parser.add_argument("--head", default="origin/develop")
    parser.add_argument("--max-commits", type=int, default=DEFAULT_MAX_COMMITS)
    parser.add_argument("--max-age-days", type=float, default=DEFAULT_MAX_AGE_DAYS)
    parser.add_argument(
        "--dry-run", action="store_true", help="mide e imprime; no toca ninguna issue"
    )
    args = parser.parse_args(argv)

    try:
        drift = measure(args.repo_path, base=args.base, head=args.head)
        unreturned_drift = measure_unreturned(
            args.repo_path, develop=args.head, main=args.base
        )
        flattened = measure_flattened_batch(
            args.repo_path, main=args.base, develop=args.head
        )
    except MissingRefError as error:
        # Dies out loud and with its own code: the signal did NOT measure, and that is not "there
        # is no drift". The workflow fetches both refs explicitly before getting here.
        print(f"error: {error}", file=sys.stderr)
        return EXIT_MISSING_REF

    now = datetime.now(UTC)
    verdict = evaluate(
        drift, now=now, max_commits=args.max_commits, max_age_days=args.max_age_days
    )
    print(
        f"{args.base}..{args.head}: {verdict.commits} commits, {verdict.age_days:.1f} días esperando"
    )
    for reason in verdict.reasons:
        print(f"  ⚠️  {reason}")

    unreturned = evaluate(
        unreturned_drift,
        now=now,
        max_commits=DEFAULT_RETURN_MAX_COMMITS,
        max_age_days=DEFAULT_RETURN_MAX_AGE_DAYS,
    )
    print(
        f"{args.head}..{args.base} (sin retorno): {unreturned.commits} commits, {unreturned.age_days:.1f} días"
    )
    for reason in unreturned.reasons:
        print(f"  ⚠️  {reason}")

    if flattened is not None:
        _print_flattened(flattened, base=args.base, head=args.head)

    if args.dry_run:
        print("(--dry-run: no se toca ninguna issue)")
        return EXIT_FLATTENED_BATCH if flattened is not None else 0

    issues = GhIssues(args.repo)
    action = sync_issue(
        verdict, title=ISSUE_TITLE, body=render_issue_body(verdict), issues=issues
    )
    print(f"issue-señal (deriva): {action}")
    action = sync_issue(
        unreturned,
        title=RETURN_ISSUE_TITLE,
        body=render_return_issue_body(unreturned),
        issues=issues,
        marker=RETURN_MARKER,
        close_comment=RETURN_CLOSE_COMMENT,
    )
    print(f"issue-señal (hotfix sin retorno): {action}")
    # LAST, after keeping both signal issues: the finding fails the job, and returning earlier
    # would leave the drift signal unrefreshed on exactly the day it is looked at most.
    return EXIT_FLATTENED_BATCH if flattened is not None else 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
