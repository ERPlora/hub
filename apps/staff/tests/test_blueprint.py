"""What of Staff travels in an export of the business (BASE-F35): the catalogue of roles it uses, read with Staff's own
list and written with its own create. The people, their schedules and their time off never travel. Like the business's
settings, a role a load brought stays when the load is undone: a role is retired, never deleted.

Every test runs against the real apps, in business A's own database, as production does.
"""

from apps.staff.tests.conftest import HUB_DB, in_business_a
from base.tests.blueprint_round_trip import app_report, call, ctx, data_of, exported, loaded_back

__all__ = ["ctx", "in_business_a"]
pytestmark = HUB_DB

STYLIST = {"name": "Stylist", "description": "Cuts and colour", "color": "#AA3366", "order": 1}
RECEPTION = {"name": "Reception", "description": "", "color": "", "order": 2}


def the_roles(ctx) -> list[tuple]:
    return sorted(
        tuple(getattr(row, name) for name in STYLIST)
        for row in call(ctx, "staff.role.list", limit=100, is_active=True).rows
    )


def test_a_backup_brings_back_the_roles_the_business_no_longer_has(ctx):
    for role in (STYLIST, RECEPTION):
        call(ctx, "staff.role.create", **role)
    before = the_roles(ctx)
    file = exported(ctx, ["staff"])
    for role in call(ctx, "staff.role.list", limit=100).rows:
        call(ctx, "staff.role.update", id=role.id, name=f"Old {role.name}", order=9)

    report = loaded_back(ctx, file)

    assert [role for role in the_roles(ctx) if not role[0].startswith("Old ")] == before
    assert [(part["created"], part["already"]) for part in app_report(report, "staff")["datasets"]] == [(2, 0)]


def test_a_retired_role_and_the_people_never_travel(ctx):
    call(ctx, "staff.role.create", **STYLIST)
    retired = call(ctx, "staff.role.create", **RECEPTION)
    call(ctx, "staff.role.update", id=retired.id, is_active=False)
    call(ctx, "staff.member.create", first_name="Ana", last_name="Gil", role="Stylist")

    data = data_of(ctx, ["staff"])

    assert set(data) == {"staff.role"}
    assert [row["name"] for row in data["staff.role"]] == ["Stylist"]
