"""A card's birthday and anniversary (CUSTOMER-F01, F04): a day and a month are enough, the year only when it is known,
and the card keeps and gives back exactly what was written."""

from apps.customer.models import Customer
from apps.customer.schemas.cards import CustomerIn, CustomerPatchIn
from apps.customer.schemas.importing import ImportIn
from apps.customer.schemas.merging import MergeIn

from .conftest import HUB_DB, run

pytestmark = HUB_DB


def test_a_new_card_keeps_a_birthday_without_its_year():
    detail = run("customer.customer.create", CustomerIn(name="Lucía", birthday="--03-14", anniversary="2015-06-01"))
    assert (detail.birthday, detail.anniversary) == ("--03-14", "2015-06-01")
    assert Customer.objects.values_list("birthday", "anniversary").get(pk=detail.id) == ("--03-14", "2015-06-01")


def test_editing_a_card_sets_and_clears_a_day_without_its_year():
    lucia = Customer.objects.create(name="Lucía", birthday="1990-03-14")
    detail = run("customer.customer.update", CustomerPatchIn(id=lucia.id, birthday="--03-14", anniversary="--06-01"))
    assert (detail.birthday, detail.anniversary) == ("--03-14", "--06-01")
    detail = run("customer.customer.update", CustomerPatchIn(id=lucia.id, birthday=None, anniversary=""))
    assert (detail.birthday, detail.anniversary) == (None, None)
    lucia.refresh_from_db()
    assert (lucia.birthday, lucia.anniversary) == (None, None)


def test_an_import_takes_a_birthday_without_its_year_and_skips_a_day_that_does_not_exist():
    result = run(
        "customer.customer.import",
        ImportIn(rows=[{"name": "Lucía", "birthday": " --03-14 "}, {"name": "Marta", "anniversary": "--02-30"}]),
        "hub_employee",
    )
    assert [(row.id is not None, sorted(row.errors)) for row in result.rows] == [(True, []), (False, ["anniversary"])]
    assert Customer.objects.values_list("name", "birthday", "anniversary").get() == ("Lucía", "--03-14", None)


def test_merging_fills_an_empty_day_from_the_duplicate_and_keeps_its_own():
    lucia = Customer.objects.create(name="Lucía", anniversary="2015-06-01")
    twin = Customer.objects.create(name="Lucía M.", birthday="--03-14", anniversary="--09-09")
    detail = run("customer.customer.merge", MergeIn(id=lucia.id, absorbed_id=twin.id), "hub_owner")
    assert (detail.birthday, detail.anniversary) == ("--03-14", "2015-06-01")
