"""The platform's reactions to a customer's changes, on the vouchers sold: only the platform reassigns or forgets."""

import uuid

import pytest
from live.errors import PermissionDenied

from apps.service.schemas.customer_reactions import ReassignIn

from .conftest import HUB_DB, run

pytestmark = HUB_DB


def test_forgetting_a_customer_is_the_platforms_only():
    with pytest.raises(PermissionDenied):
        run("service.grant.forget_customer", {"id": str(uuid.uuid7())})


def test_reassigning_is_the_platforms_only():
    with pytest.raises(PermissionDenied):
        run(
            "service.grant.reassign",
            ReassignIn(id=uuid.uuid7(), absorbed_id=uuid.uuid7()),
        )
