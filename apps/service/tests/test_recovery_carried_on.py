"""Asked again after one that failed halfway, a recovery from a separate copy finishes what that one left (hub#1495;
BASE-F114, SERVICE-F08).

Services brings a deleted category back and, apart and afterwards, puts back into it what the business kept. A recovery
that fails between the two leaves the category in the business, made by its own actor. The one asked next of the same
copy carries it on (``base.recovery.carries_on``): the category counts as its own, and what the business has not
touched since the category came back goes into it.
"""

from apps.service import queries
from apps.service.models import Category, Service
from base.recovery import giving_back
from base.tenancy.tests.test_recovery import fresh, run, run_in

from . import test_recovery as whole
from .conftest import HUB_DB, make_category, make_service, make_tax
from .test_recovery import recoveries  # noqa: F401 - the fixture of the two databases

pytestmark = HUB_DB


def test_a_category_a_failed_recovery_brought_back_takes_back_what_it_had_inside_from_the_one_that_carries_it_on():
    tax = make_tax("test.service", "Service — test")
    gloss, toning = make_service("Gloss", tax=tax), make_category("Toning")
    failed = whole.a_recovery()
    [service], [subcategory] = whole.links_of(failed, services=[gloss], subcategories=[toning])
    now = whole.a_recovery()

    with giving_back(now, carrying_on=[failed]):
        whole.create(service, "service.service.return_to_category", now)
        whole.create(subcategory, "service.category.return_to_parent", now)

    color = Category.objects.get(name="Color", is_deleted=False)
    assert Service.objects.get(pk=gloss.pk).category_id == color.pk
    assert Category.objects.get(pk=toning.pk).parent_id == color.pk


def failed_halfway(recoveries, every_app_on, monkeypatch):  # noqa: F811 - the fixture
    """A business whose recovery of Services failed once its deleted category was back and before anything went back
    into it: the business, its services' ids and the copy."""
    hub, ids, color, copy = whole.TestServicesComeBack().a_full_category(recoveries, every_app_on)
    run_in(hub, "service.category.delete", id=color)
    read_links = queries.recovery.service_links_not_in_business

    def broken(categories):
        raise RuntimeError("the worker died")

    monkeypatch.setattr(queries.recovery, "service_links_not_in_business", broken)
    failed = recoveries.ask(copy, "service")
    assert run() == 1
    failed = fresh(failed)
    assert (failed.status, failed.results) == (
        "failed",
        [whole.CATEGORIES | {"created": 1}, whole.SERVICES, whole.SERVICE_LINKS],
    )
    monkeypatch.setattr(queries.recovery, "service_links_not_in_business", read_links)
    return hub, ids, copy


def test_asked_again_after_one_that_failed_halfway_its_category_gets_back_what_the_business_kept(
    recoveries,  # noqa: F811 - the fixture
    every_app_on,
    monkeypatch,
):
    hub, _, copy = failed_halfway(recoveries, every_app_on, monkeypatch)

    # Asked again, it finishes what the one that failed left: the same category, with what the business kept.
    assert whole.recovered(recoveries, copy) == [
        whole.CATEGORIES,
        whole.SERVICES,
        whole.SERVICE_LINKS | {"created": 3},
        whole.SUBCATEGORY_LINKS | {"created": 1},
    ]
    assert whole.live_categories(hub) == [
        ("Color", None, "#cc0066", 4),
        ("Hair", None, "", 0),
        ("Toning", "Color", "", 0),
    ]
    assert [one for one in whole.in_categories(hub) if one[0] in {"Balayage", "Gloss", "Highlights"}] == [
        ("Balayage", "Color"),
        ("Gloss", "Color"),
        ("Highlights", "Color"),
    ]


def test_asked_again_after_one_that_failed_halfway_what_the_business_touched_since_stays_as_it_left_it(
    recoveries,  # noqa: F811 - the fixture
    every_app_on,
    monkeypatch,
):
    hub, ids, copy = failed_halfway(recoveries, every_app_on, monkeypatch)
    # Between the one that failed and the next, the business changes a service, files another and edits the subcategory.
    run_in(hub, "service.service.update", id=ids["gloss"], price=3600)
    run_in(hub, "service.service.update", id=ids["balayage"], category_id=ids["hair"])
    run_in(hub, "service.category.update", id=ids["toning"], color="#112233")

    # Only what it has not touched goes back into the category, and nothing else is said, as when it is asked again.
    assert whole.recovered(recoveries, copy) == [
        whole.CATEGORIES,
        whole.SERVICES,
        whole.SERVICE_LINKS | {"created": 1},
        whole.SUBCATEGORY_LINKS,
    ]
    assert [one for one in whole.in_categories(hub) if one[0] in {"Balayage", "Gloss", "Highlights"}] == [
        ("Balayage", "Hair"),
        ("Gloss", None),
        ("Highlights", "Color"),
    ]
    assert [one for one in whole.live_categories(hub) if one[0] == "Toning"] == [("Toning", None, "#112233", 0)]
