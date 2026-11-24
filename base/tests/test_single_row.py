"""A setting the business keeps in one row at most: the row a command changes is locked, and made when missing."""

from live.operations import atomic

from base.models.support_access import SupportAccess
from base.services.single_row import locked_single_row
from base.tenancy.tests.business import HUB_DB, in_business_a

__all__ = ["in_business_a"]

pytestmark = HUB_DB


def test_the_row_is_made_with_its_defaults_when_the_business_has_none():
    with atomic():
        row = locked_single_row(SupportAccess)
    assert row.enabled is False
    assert list(SupportAccess.objects.all()) == [row]


def test_the_row_the_business_already_has_is_the_one_returned():
    kept = SupportAccess.objects.create(enabled=True)
    with atomic():
        row = locked_single_row(SupportAccess)
    assert row == kept and row.enabled is True
    assert SupportAccess.objects.count() == 1
