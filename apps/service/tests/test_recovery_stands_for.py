"""The service that stands for one of the copy's (hub#1459): what a recovery from a separate copy made again keeps of
the one it replaces, for an app whose records hang from a service.
"""

import uuid

from live.operations import get

from apps.service import queries
from apps.service.models import Service
from base.recovery import actor_of

from .conftest import HUB_DB, ctx_for, make_service, make_tax
from .test_recovery import a_service_of_the_copy, create

pytestmark = HUB_DB


def made_again_for(there: uuid.UUID, name: str = "Haircut", **fields) -> Service:
    """A service a recovery from a separate copy made again for the copy's ``there``, as ``service.service.recover``
    leaves it."""
    return make_service(name, created_by=actor_of(uuid.uuid7()), stands_for=there, **fields)


def test_a_lost_service_made_again_keeps_which_of_the_copys_it_stands_for():
    tax = make_tax("test.service", "Service — test")
    lost = a_service_of_the_copy(name="Keratin treatment", tax_category_id=tax.pk)

    [record] = queries.recovery.services_not_in_business([lost])
    made = create(record, actor=actor_of(uuid.uuid7()))

    assert record["stands_for"] == lost["id"]
    assert Service.objects.get(pk=made.id).stands_for == lost["id"]


def test_one_made_by_the_screen_stands_for_none():
    tax = make_tax("test.service", "Service — test")
    made = create({"name": "Haircut", "price": 2000, "tax_category_key": tax.key}, "service.service.create")

    assert Service.objects.get(pk=made.id).stands_for is None


def test_a_service_no_longer_held_is_the_one_a_recovery_made_again_for_it():
    gone, archived_since, renamed_since = uuid.uuid7(), uuid.uuid7(), uuid.uuid7()
    haircut = made_again_for(gone)
    colour = made_again_for(archived_since, "Colour", is_active=False)
    perm = made_again_for(renamed_since, "Curly perm")

    assert queries.recovery.services_standing_for([gone, archived_since, renamed_since]) == {
        gone: haircut.pk,
        archived_since: colour.pk,
        renamed_since: perm.pk,
    }


def test_a_service_still_held_is_itself_and_not_in_the_result():
    offered = make_service("Haircut")
    archived = make_service("Colour", is_active=False)
    made_again_for(offered.pk)
    made_again_for(archived.pk, "Colour")

    assert queries.recovery.services_standing_for([offered.pk, archived.pk]) == {}


def test_one_made_again_by_hand_with_its_name_stands_for_none():
    make_service("Haircut", created_by="ana")

    assert queries.recovery.services_standing_for([uuid.uuid7()]) == {}


def test_made_again_twice_for_one_the_oldest_stands_for_it():
    gone = uuid.uuid7()
    first = made_again_for(gone)
    made_again_for(gone, "Haircut, renamed")

    assert queries.recovery.services_standing_for([gone]) == {gone: first.pk}


def test_with_nothing_asked_none_stands_for_anything():
    made_again_for(uuid.uuid7())

    assert queries.recovery.services_standing_for([]) == {}


def test_another_app_asks_it_by_its_operation_and_only_as_the_platform():
    gone = uuid.uuid7()
    haircut = made_again_for(gone)
    op = get("service.service.standing_for")

    answer = op(ctx_for(actor="system", permissions={"*"}), op.input(ids=[gone, uuid.uuid7()]))

    assert answer.standing_for == {gone: haircut.pk}
    assert (op.kind, op.permission) == ("query", "service.system")
    assert not ctx_for("hub_owner").has(op.permission)
