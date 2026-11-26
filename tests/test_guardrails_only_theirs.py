"""Guardrail: a read that keeps a role to the caller's own says so to the assistant (hub#2688).

A read keeps a person to their own when it asks a permission (``ctx.has``, ``<DECLARATION>.sees_all``) and who the
caller is (``own_member``, ``actor_user``, ``me``…). Its answer then lacks everyone else's rows, and the model, which
never sees that rule, takes the missing rows for none. So where such a read narrows it calls
``base.only_theirs.only_theirs``, as an ``Owned`` declaration does by itself, and the assistant's tool result says
the answer holds only the person's own.

Every read door that asks both and never says so is in :data:`NOT_A_NARROWING`, closed and with its reason; what the
list names must still ask both, so it never rots; and a planted narrowing is caught, so a scan that found nothing is
never taken for a clean tree.

A door that says so in one read may keep another to the caller's own in silence (one tip by its sale, a day by its id).
So each function that asks both by itself says so too, or calls one of its door that does, or is in
:data:`NOT_NARROWING_BY_ITSELF`.
"""

import ast
import re
from pathlib import Path

from test_guardrails_ownership import REPO, query_doors

#: A call that asks a permission; ``_reads_any`` is how the time clock asks for any of several.
ASKS = frozenset({"has", "sees_all", "_reads_any"})
#: A call that asks who the caller is: by a name that says their own («own_member», «_own_days», «me») or their account.
WHO = re.compile(r"(^|_)(own|owns|mine|me)(_|$)|actor_user|get_username")
#: The call that says a read answers only the caller's own.
TELLS = "only_theirs"

#: Every read door that asks a permission and who the caller is without keeping a read to their own: ``path → why``.
NOT_A_NARROWING: dict[str, str] = {
    "apps/appointment/queries/access.py": (
        "Whether the caller may book or change an appointment of a professional: a write's permission, no read's rows."
    ),
    "apps/appointment/queries/ownership.py": (
        "The declaration of whose an appointment is and whether a write may touch or name one; the reads narrow "
        "through APPOINTMENTS.visible, which says so."
    ),
    "apps/attendance/queries/people.py": (
        "Whose clock a clock-in or a break acts on: the caller's own, or someone else's with attendance.clock_others."
    ),
    "apps/attendance/queries/reads.py": (
        "Only defines the helpers (_reads_any, _own_days); the reads that narrow with them say so where they narrow."
    ),
    "apps/sale/queries/service_lines.py": "A service's own price (own_price), not the caller's own.",
    "apps/staff/queries/members.py": (
        "The caller's own record, asked for as theirs, and a colleague's contact, hidden field by field: no row held "
        "back."
    ),
}


#: Every function of a read door that asks both by itself without keeping a read to the caller's own:
#: ``path::function → why``.
NOT_NARROWING_BY_ITSELF: dict[str, str] = {
    "apps/appointment/queries/access.py::may_change": "Whether a write may change an appointment of a professional.",
    "apps/appointment/queries/access.py::may_book_for": "Whether a write may book for a professional.",
    "apps/appointment/queries/ownership.py::sees_whose": (
        "Whether a taken time names whose appointment takes it: a name left out of a refusal, no row held back."
    ),
    "apps/attendance/queries/people.py::clocked": (
        "Whose clock a clock-in or a break acts on; someone else's without attendance.clock_others is refused in words."
    ),
    "apps/task/queries/reads.py::sees": (
        "Whether a task's detail names its parent task: a field left empty, the task itself is read through visible."
    ),
    "apps/task/queries/reads.py::may_change": "Whether a write may change a task.",
}


def calls(tree: ast.AST) -> set[str]:
    """The names of everything ``tree`` calls: ``f(…)`` and ``x.f(…)`` alike."""
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            name = func.id if isinstance(func, ast.Name) else func.attr if isinstance(func, ast.Attribute) else None
            if name is not None:
                found.add(name)
    return found


def silent_narrowings(root: Path) -> set[str]:
    """Every read door under ``root`` that asks a permission and who the caller is, and never says a read of it
    answers only the caller's own."""
    found: set[str] = set()
    for path in query_doors(root):
        called = calls(ast.parse((root / path).read_text(encoding="utf-8")))
        if called & ASKS and any(WHO.search(name) for name in called) and TELLS not in called:
            found.add(str(path))
    return found


def silent_functions(root: Path) -> set[str]:
    """Every function of a read door under ``root`` (``path::function``) that asks a permission and who the caller is
    by itself, and neither says a read answers only the caller's own nor calls a function of its door that does."""
    found: set[str] = set()
    for path in query_doors(root):
        tree = ast.parse((root / path).read_text(encoding="utf-8"))
        functions = [node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)]
        tellers = {TELLS} | {function.name for function in functions if TELLS in calls(function)}
        for function in functions:
            called = calls(function)
            if called & ASKS and any(WHO.search(name) for name in called) and not called & tellers:
                found.add(f"{path}::{function.name}")
    return found


# ── The tree as it is ────────────────────────────────────────────────────────────────────────────────────────────────


def test_every_read_that_keeps_a_role_to_its_own_says_so_or_is_listed_with_its_reason():
    silent = silent_narrowings(REPO) - set(NOT_A_NARROWING)
    assert silent == set(), (
        f"{sorted(silent)} ask a permission and who the caller is: where a read keeps the caller to their own, call "
        "base.only_theirs.only_theirs() (or read through an Owned declaration), so the assistant says it can "
        "only see theirs; if no read is kept to their own, add it to NOT_A_NARROWING with a reason a reviewer can weigh"
    )


def test_what_the_list_names_still_asks_a_permission_and_who_the_caller_is():
    gone = set(NOT_A_NARROWING) - silent_narrowings(REPO)
    assert gone == set(), f"{sorted(gone)} no longer ask both without saying so: take them off NOT_A_NARROWING"


def test_every_function_that_keeps_a_role_to_its_own_says_so_or_is_listed_with_its_reason():
    silent = silent_functions(REPO) - set(NOT_NARROWING_BY_ITSELF)
    assert silent == set(), (
        f"{sorted(silent)} ask a permission and who the caller is: where the read keeps the caller to their own (also "
        "one record by its id, answered as not found), call base.only_theirs.only_theirs(); if no read is kept to "
        "their own, add the function to NOT_NARROWING_BY_ITSELF with a reason a reviewer can weigh"
    )


def test_the_functions_the_list_names_still_ask_both_without_saying_so():
    gone = set(NOT_NARROWING_BY_ITSELF) - silent_functions(REPO)
    assert gone == set(), f"{sorted(gone)} no longer ask both without saying so: take them off NOT_NARROWING_BY_ITSELF"


def test_every_reason_says_why():
    for path, why in (NOT_A_NARROWING | NOT_NARROWING_BY_ITSELF).items():
        assert why.endswith("."), path


# ── A planted narrowing is caught ────────────────────────────────────────────────────────────────────────────────────

NARROWS = (
    "from apps.staff.queries.reads import own_member\n\n\n"
    "def rows(ctx, rows):\n"
    "    if ctx.has('shop.view_all'):\n"
    "        return rows\n"
    "    {tells}return rows.filter(member=own_member(ctx))\n"
)


def tree_with(tmp_path: Path, files: dict[str, str]) -> Path:
    for path, source in files.items():
        (tmp_path / path).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / path).write_text(source, encoding="utf-8")
    return tmp_path


def test_a_planted_read_that_keeps_a_role_to_its_own_without_saying_so_is_caught(tmp_path):
    root = tree_with(
        tmp_path,
        {
            "apps/shop/queries.py": NARROWS.format(tells=""),
            "apps/desk/queries/rows.py": NARROWS.format(tells="").replace("own_member(ctx)", "ctx.actor.get_username()"),
        },
    )
    assert silent_narrowings(root) == {"apps/shop/queries.py", "apps/desk/queries/rows.py"}


def test_a_planted_read_that_says_so_or_a_services_door_is_not_caught(tmp_path):
    root = tree_with(
        tmp_path,
        {
            "apps/shop/queries.py": NARROWS.format(tells="only_theirs()\n    "),
            "apps/shop/services.py": NARROWS.format(tells=""),
        },
    )
    assert silent_narrowings(root) == set()


ONE_BY_ITS_ID = (
    "def one(ctx, row):\n"
    "    if not ctx.has('shop.view_all') and row.member != own_member(ctx):\n"
    "        raise LookupError\n"
    "    return row\n"
)


def test_a_planted_read_kept_to_its_own_in_a_door_that_says_so_elsewhere_is_caught(tmp_path):
    says_so = NARROWS.format(tells="only_theirs()\n    ")
    through_its_door = "\n\ndef listed(ctx, rows):\n    return rows(ctx, rows) if ctx.has('shop.view') else own_member(ctx)\n"
    root = tree_with(
        tmp_path,
        {"apps/shop/queries.py": says_so + "\n\n" + ONE_BY_ITS_ID, "apps/desk/queries.py": says_so + through_its_door},
    )
    assert silent_narrowings(root) == set()
    assert silent_functions(root) == {"apps/shop/queries.py::one"}
