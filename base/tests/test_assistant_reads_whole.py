"""What the assistant reads of an answer too long to be told at once: the answer is cut, and the cut only asks for what
the read takes. A read that grows with the apps that are on (what a role allows, the help of an app, the automations
the apps bring) pages by ``offset``, so following its cut reads every item, and the last ones as well."""

import json

import pytest
from live.assistant.cutting import CUT
from live.context import OperationContext
from live.operations import get

from base import assistant
from base.catalog.verticals import template_apps
from base.models import Membership
from base.permissions import access_for
from base.queries.app_help import ready_apps
from base.tenancy.tests.business import A, HUB_DB, in_business_a
from base.tests.roles import a_role

__all__ = ["in_business_a"]

pytestmark = HUB_DB

#: More calls than any read of these needs to be read whole, so that a read that never moves on still ends.
MOST_CALLS = 60


@pytest.fixture
def olga(make_user):
    return make_user("saas:1", host=A.key, role=Membership.Role.OWNER, first_name="Olga")


def asking(user, language: str) -> OperationContext:
    return OperationContext(scope=A, actor=user, permissions=access_for(user, A), language=language)


def told(ctx: OperationContext, name: str, data: dict) -> dict:
    """What the model is told when it calls the read ``name`` with ``data``."""
    return json.loads(assistant.tools.run(ctx, get(name), json.dumps(data)).content)


def whole(ctx: OperationContext, name: str, data: dict, monkeypatch) -> dict:
    """The answer of ``name`` with nothing cut."""
    with monkeypatch.context() as patched:
        patched.setattr("live.assistant.running.MAX_RESULT_CHARS", 10**9)
        return told(ctx, name, data)


def read_on(ctx: OperationContext, name: str, data: dict, key: str) -> list:
    """Every item of the list ``key`` the model reads of ``name`` by calling it again from where each cut answer stopped."""
    items: list = []
    for _ in range(MOST_CALLS):
        answer = told(ctx, name, {**data, "offset": len(items)} if items else data)
        items += answer[key]
        if CUT not in answer:
            break
    return items


def trimmed_list(answer: dict, full: dict) -> str:
    """The list of ``full`` the cut ``answer`` kept fewer items of."""
    return next(key for key, value in full.items() if isinstance(value, list) and len(answer.get(key, [])) < len(value))


def test_the_assistant_reads_every_permission_of_a_cashier_with_23_apps_on_sales_among_them(olga, monkeypatch):
    on = frozenset({"base", *template_apps("restaurant")})
    monkeypatch.setattr("base.queries.roles.active_apps", lambda scope: on)
    ctx = asking(olga, "es")
    create = get("base.role.create")
    cashier = create(ctx, create.input(based_on=Membership.Role.EMPLOYEE, name="Cajero")).key
    full = whole(ctx, "base.role.detail", {"role": cashier}, monkeypatch)
    listed = {row["key"]: row["permissions"] for row in told(ctx, "base.role.list", {})["roles"]}
    assert (listed[cashier], len(full["apps"])) == (77, 23)
    assert CUT in told(ctx, "base.role.detail", {"role": cashier})

    apps = read_on(ctx, "base.role.detail", {"role": cashier}, "apps")

    assert apps == full["apps"]
    assert {"sale.take_payment", "sale.void_sale"} <= {line["permission"] for app in apps for line in app["permissions"]}


def reads_that_grow_with_the_apps(ctx: OperationContext) -> list[tuple[str, dict]]:
    """The assistant's reads of ``ctx``'s person that need nothing to be read, what each role allows and each app's help:
    their answers grow with the apps that are on, whatever records the business has."""
    plain = [
        (name, {})
        for name, op in assistant.tools.catalog(ctx).items()
        if op.kind == "query" and not any(field.is_required() for field in op.input.model_fields.values())
    ]
    roles = [*Membership.Role.values, str(a_role().pk)]
    return [
        *plain,
        *(("base.role.detail", {"role": role}) for role in roles),
        *(("base.help.get", {"app": app}) for app in ready_apps()),
    ]


def what_the_cut_asks_that_cannot_be_done(ctx: OperationContext, name: str, data: dict, monkeypatch) -> str | None:
    """Why the cut answer of ``name`` cannot be read on as it says: it pages and its next pages do not bring the rest, or
    it does not page and its input has nothing to narrow it with; ``None`` when it can, or when nothing is cut."""
    answer = told(ctx, name, data)
    if CUT not in answer:
        return None
    fields = get(name).input.model_fields
    if "offset" not in fields:
        return None if any(not field.is_required() for field in fields.values()) else "nothing to narrow it with"
    full = whole(ctx, name, data, monkeypatch)
    key = trimmed_list(answer, full)
    return None if read_on(ctx, name, data, key) == full[key] else f"its pages do not bring every item of {key}"


@pytest.mark.parametrize("language", ["en", "es"])
def test_a_cut_answer_only_asks_for_what_its_read_takes_and_reading_on_brings_the_rest(olga, language, monkeypatch):
    ctx = asking(olga, language)

    unreadable = {
        f"{name} {json.dumps(data)}": why
        for name, data in reads_that_grow_with_the_apps(ctx)
        if (why := what_the_cut_asks_that_cannot_be_done(ctx, name, data, monkeypatch)) is not None
    }

    assert unreadable == {}
