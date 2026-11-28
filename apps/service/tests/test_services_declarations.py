"""What every write operation of the service app declares (kind, permission, risk and whether an API key reaches it),
and that a refusal leaves no trace (nothing written, no event): the checks run before the first write.
"""

import uuid

import pytest
from live.errors import NotFound
from live.operations import get

from apps.service.schemas.assignments import AssignmentPatchIn
from apps.service.schemas.categories import CategoryPatchIn
from apps.service.schemas.grants import AdjustIn, VoidIn
from apps.service.schemas.packages import PackagePatchIn

from .conftest import HUB_DB, events, run

pytestmark = HUB_DB


@pytest.mark.parametrize(
    ("name", "permission", "risk"),
    [
        ("service.service.create", "service.add_service", "normal"),
        ("service.service.bulk_create", "service.change_service", "high"),
        ("service.service.update", "service.change_service", "normal"),
        ("service.service.archive", "service.delete_service", "high"),
        ("service.service.restore", "service.change_service", "normal"),
        ("service.category.create", "service.add_category", "normal"),
        ("service.category.update", "service.change_category", "normal"),
        ("service.category.delete", "service.delete_category", "high"),
        ("service.settings.update", "service.manage_settings", "high"),
        ("service.assignment.assign", "service.change_service", "normal"),
        ("service.assignment.update", "service.change_service", "normal"),
        ("service.assignment.remove", "service.change_service", "normal"),
        ("service.assignment.release_member", "service.system", "normal"),
        ("service.package.create", "service.add_package", "normal"),
        ("service.package.update", "service.change_package", "normal"),
        ("service.package.delete", "service.delete_package", "high"),
        ("service.grant.create", "service.grant_package", "normal"),
        ("service.grant.void", "service.void_grant", "high"),
        ("service.grant.adjust", "service.adjust_grant", "high"),
        ("service.grant.redeem", "service.redeem_package", "normal"),
        ("service.grant.reassign", "service.system", "normal"),
        ("service.grant.forget_customer", "service.system", "normal"),
    ],
)
def test_declarations(name, permission, risk):
    op = get(name)
    assert (op.kind, op.permission, op.ai["risk"]) == ("command", permission, risk)
    # The reactions are the platform's: no API key reaches them.
    assert op.expose_api is (permission != "service.system")


def test_the_refusals_leave_no_trace(tax):
    for name, data in (
        ("service.category.update", CategoryPatchIn(id=uuid.uuid7(), name="X")),
        ("service.package.update", PackagePatchIn(id=uuid.uuid7(), name="X")),
        (
            "service.assignment.update",
            AssignmentPatchIn(id=uuid.uuid7(), is_active=False),
        ),
        ("service.grant.void", VoidIn(id=uuid.uuid7(), reason="x")),
        ("service.grant.adjust", AdjustIn(id=uuid.uuid7(), uses_delta=1, reason="x")),
    ):
        with pytest.raises(NotFound):
            run(name, data)
    assert events() == []
