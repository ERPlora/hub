"""``manage.py export_assistant_catalog``: the catalogue layer 2 of the assistant's QA reads (docs plan 2026-10-31, the
assistant's knowledge and QA, §1.5) — a role's real tools, in a language, as ``live.assistant_qa.export_catalog``
gives them, as JSON on the standard output.

The export names no business: it is the catalogue of a business with every app on (``--apps`` narrows it), which is
what the e2e business ``a`` has, so it needs no database.
"""

import json
from io import StringIO

import pytest
from django.core.management import CommandError, call_command
from live.assistant import asks_of
from live.context import OperationContext, Scope
from live.meta import all_live_app_configs
from live.operations import registry

from base import assistant
from base.models import Membership
from base.permissions import permissions_for

A = Scope("host", "a")
ROLES = {
    "owner": Membership.Role.OWNER,
    "admin": Membership.Role.ADMIN,
    "manager": Membership.Role.MANAGER,
    "employee": Membership.Role.EMPLOYEE,
}


def export(*args: str) -> list[dict]:
    out = StringIO()
    call_command("export_assistant_catalog", *args, stdout=out)
    return json.loads(out.getvalue())


def names(exported: list[dict]) -> list[str]:
    return [tool["name"] for tool in exported]


def test_the_owner_s_export_is_every_tool_of_every_app_by_name_with_its_asks_in_the_language():
    exported = export("--role", "owner", "--language", "es")
    assert names(exported) == sorted(name for name, op in registry.items() if assistant.is_tool(op))
    assert {tool["app_label"] for tool in exported} >= {"base", "sale", "staff"}  # every app, not only the platform
    enable = next(tool for tool in exported if tool["name"] == "base.app.enable")
    assert enable["tool_name"] == "base__app__enable"
    assert (enable["kind"], enable["permission"]) == ("write", "base.administer_hub")
    assert enable["asks"] == list(asks_of(registry["base.app.enable"])["es"]) != []
    assert "base.hub.reset" not in names(exported)  # never done from the chat (NOT_FROM_CHAT), as in a turn


def test_the_asks_come_in_the_language_asked():
    english = next(tool for tool in export("--role", "owner", "--language", "en") if tool["name"] == "base.app.enable")
    assert english["asks"] == list(asks_of(registry["base.app.enable"])["en"]) != []


@pytest.mark.django_db  # the catalogue of a member of business a, which has every app on
@pytest.mark.parametrize("role", sorted(ROLES))
def test_each_role_exports_exactly_the_catalogue_a_member_with_it_has_in_a_turn(make_user, role):
    user = make_user(f"qa-{role}", host=A.key, role=ROLES[role])
    ctx = OperationContext(scope=A, actor=user, permissions=permissions_for(user, A), language="en")
    assert names(export("--role", role, "--language", "en")) == list(assistant.catalog(ctx))


def test_a_role_without_the_permission_does_not_get_the_tool():
    employee = set(names(export("--role", "employee", "--language", "en")))
    owner = set(names(export("--role", "owner", "--language", "en")))
    assert "base.profile.update" in employee  # their own profile: the export is not merely empty
    assert "base.app.enable" in owner and "base.app.enable" not in employee  # base.administer_hub
    assert employee < owner


def test_apps_narrow_the_export_to_those_apps():
    exported = export("--role", "owner", "--language", "en", "--apps", "base, staff")
    assert {tool["app_label"] for tool in exported} == {"base", "staff"}


@pytest.mark.parametrize(
    "args",
    [
        ("--role", "owner", "--language", "en", "--apps", "base,nonexistent"),
        ("--role", "superuser", "--language", "en"),
        ("--role", "owner", "--language", "fr"),
    ],
)
def test_an_unknown_app_role_or_language_is_refused(args):
    with pytest.raises(CommandError):
        export(*args)


def test_every_app_label_is_accepted():
    labels = ",".join(config.label for config in all_live_app_configs())
    assert names(export("--role", "owner", "--language", "en", "--apps", labels)) == names(
        export("--role", "owner", "--language", "en")
    )
