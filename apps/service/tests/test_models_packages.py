"""Models of the vouchers of the catalog: the rules the database itself keeps.

The operations check every rule first, with their own messages; these constraints are the last line
(the Django admin and two writes at once do not go through the operations' checks).
"""

from apps.service.models.packages import Package, PackageItem
from apps.service.tests.conftest import HUB_DB, make_package, make_service, refused

pytestmark = HUB_DB


def test_a_live_package_name_is_unique_and_a_deleted_one_frees_it():
    old = make_package("Bono 5")
    assert refused(model=Package, name="bono 5")
    old.is_deleted = True
    old.save()
    assert not refused(model=Package, name="Bono 5")


def test_a_package_discount_validity_and_uses_stay_in_their_range():
    assert refused(model=Package, name="Too much", discount_percent_bp=10001)
    assert refused(model=Package, name="No days", validity_days=0)
    assert refused(model=Package, name="No uses", max_uses=0)
    assert refused(model=Package, name="Odd", discount_type="gift")


def test_a_package_line_is_one_service_once_with_at_least_one_session():
    cut = make_service("Cut")
    package = make_package("Bono", [cut])
    assert refused(model=PackageItem, package=package, service=cut)
    assert refused(
        model=PackageItem, package=make_package("Other"), service=cut, sessions=0
    )
