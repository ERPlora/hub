"""The categories a recovery from a separate copy gives back (hub#1323; SERVICE-F07, F08): those the business lacks come
back first, each by the screen's create, and what the business kept goes back into them apart, by links of its own.
"""

import threading
import uuid

import pytest
from django.db import connections
from django.utils import timezone, translation
from live.errors import Conflict
from live.operations import get

from apps.service import queries
from apps.service.models import Category, Service
from apps.service.schemas import CategoryRecoverIn
from apps.service.services.category_recovery import SERVICE_CHANGED_LEFT, SERVICE_MOVED_LEFT, SUBCATEGORY_CHANGED_LEFT
from base.recovery import actor_of, giving_back
from base.tenancy.context import current_alias

from .conftest import HUB_DB, ctx_for, make_category, make_service, make_tax
from .test_recovery import a_service_of_the_copy, create, direct

pytestmark = HUB_DB


#: A category of the copy with what a new one has, as ``categories_in_copy`` gives it.
NEW_CATEGORY = {
    "name": "",
    "description": "",
    "icon": "",
    "color": "",
    "sort_order": 0,
    "parent_id": None,
    "service_ids": [],
}


def a_category_of_the_copy(category: Category | None = None, **fields) -> dict:
    """A category as the copy gives it (``categories_in_copy``): ``category``'s, or a new one with ``fields``."""
    if category is not None:
        held = {field: getattr(category, field) for field in NEW_CATEGORY if field != "service_ids"}
        return {"id": category.pk, "service_ids": []} | held | fields
    return {"id": uuid.uuid7()} | NEW_CATEGORY | fields


def made_again(one: dict, *subcategories: dict, **parent) -> dict:
    """``one`` of the copy as ``categories_not_in_business`` gives it, to ``service.category.recover``: its parent here
    (``parent``), the one it stands for and what it had inside it there, its services and its ``subcategories``."""
    return (
        {key: value for key, value in one.items() if key != "parent_id"}
        | {"stands_for": one["id"], "subcategory_ids": [sub["id"] for sub in subcategories]}
        | parent
    )


def test_the_copy_gives_each_live_category_with_what_its_create_takes_and_the_services_in_it():
    tax = make_tax("test.service", "Service — test")
    hair = make_category("Hair", description="Cuts and styling", icon="ion:cut-outline", color="#aa3300", sort_order=2)
    kids = make_category("Kids", parent=hair)
    make_category("Old", is_deleted=True, deleted_at=timezone.now())
    cut = make_service("Haircut", tax=tax, category=hair)
    perm = make_service("Old perm", tax=tax, category=hair, is_active=False, archived_at=timezone.now())
    make_service("Gloss", tax=tax)

    read = sorted(queries.recovery.categories_in_copy(direct()), key=lambda one: one["name"])

    # One the copy had deleted already is not the moment's: it never comes back. Its services, archived ones too.
    assert read == [
        {
            "id": hair.pk,
            "name": "Hair",
            "description": "Cuts and styling",
            "icon": "ion:cut-outline",
            "color": "#aa3300",
            "sort_order": 2,
            "parent_id": None,
            "service_ids": sorted([cut.pk, perm.pk]),
        },
        {
            "id": kids.pk,
            "name": "Kids",
            "description": "",
            "icon": "",
            "color": "",
            "sort_order": 0,
            "parent_id": hair.pk,
            "service_ids": [],
        },
    ]


def test_a_copy_without_the_service_table_gives_its_categories_with_no_service():
    hair = make_category("Hair")
    with connections[current_alias()].cursor() as cursor:
        # Undone with the test's transaction.
        cursor.execute("DROP TABLE service_service CASCADE")

    assert [(one["id"], one["service_ids"]) for one in queries.recovery.categories_in_copy(direct())] == [(hair.pk, [])]


def test_a_copy_without_the_category_table_gives_no_category():
    with connections[current_alias()].cursor() as cursor:
        # Undone with the test's transaction.
        cursor.execute("DROP TABLE service_category CASCADE")

    assert queries.recovery.categories_in_copy(direct()) == []


def test_the_categories_the_business_lacks_come_parents_first_each_as_its_create_takes_it():
    hair = make_category("Hair")
    color = make_category("Color", color="#cc0066", sort_order=4, is_deleted=True, deleted_at=timezone.now())
    hands = a_category_of_the_copy(name="Hands", description="Manicure and more", icon="ion:hand-left-outline")
    copy = [
        # Its parent comes back too: listed after it in the copy, made before it.
        nails := a_category_of_the_copy(name="Nails", parent_id=hands["id"], sort_order=1),
        hands,
        in_color := a_category_of_the_copy(color),
        a_category_of_the_copy(hair),
        toning := a_category_of_the_copy(name="Toning", parent_id=color.pk),
        kids := a_category_of_the_copy(name="Kids", parent_id=hair.pk),
    ]

    lacking = queries.recovery.categories_not_in_business(copy)

    assert lacking == [
        made_again(hands, nails),
        made_again(in_color, toning),
        # Into a parent brought back just before, by its name (it has no id here yet); into one kept, by its id.
        made_again(nails, parent="Hands"),
        made_again(toning, parent="Color"),
        made_again(kids, parent_id=hair.pk),
    ]
    for record in lacking:
        CategoryRecoverIn.model_validate({key: value for key, value in record.items() if key != "id"})


def test_a_category_the_business_made_again_is_never_made_twice_and_its_children_go_into_it():
    gone = make_category("Color", is_deleted=True, deleted_at=timezone.now())
    # Made again by hand since: the same name, the case and the spaces aside (a live name is unique).
    again = make_category("color ")
    copy = [a_category_of_the_copy(gone), toning := a_category_of_the_copy(name="Toning", parent_id=gone.pk)]

    assert queries.recovery.categories_not_in_business(copy) == [made_again(toning, parent_id=again.pk)]


def test_a_loop_a_raw_write_left_in_the_copy_never_hangs_and_gives_each_category_once():
    hair, cuts = a_category_of_the_copy(name="Hair"), a_category_of_the_copy(name="Cuts")
    # No operation leaves one (SERVICE-F07 refuses it), a raw write may (``delete_category`` says so too).
    hair["parent_id"], cuts["parent_id"] = cuts["id"], hair["id"]
    by_id = {one["id"]: one for one in (hair, cuts)}
    depths: list[int] = []
    counting = threading.Thread(target=lambda: depths.extend(queries.recovery._depth(one, by_id) for one in (hair, cuts)))
    counting.daemon = True  # a loop that never ends must not keep the run alive

    counting.start()
    counting.join(timeout=5)

    assert depths == [1, 1]
    assert [(one["name"], one.get("parent")) for one in queries.recovery.categories_not_in_business([hair, cuts])] == [
        ("Hair", "Cuts"),
        ("Cuts", "Hair"),
    ]


def test_the_lacking_categories_are_created_as_the_screen_creates_them_and_asking_again_makes_none_twice():
    color = make_category("Color", is_deleted=True, deleted_at=timezone.now())
    copy = [
        a_category_of_the_copy(name="Toning", parent_id=color.pk, sort_order=2),
        a_category_of_the_copy(color),
    ]

    made = [create(record, "service.category.recover") for record in queries.recovery.categories_not_in_business(copy)]

    assert [(one.name, one.parent_name) for one in made] == [("Color", None), ("Toning", "Color")]
    assert color.pk not in {one.id for one in made}
    assert queries.recovery.categories_not_in_business(copy) == []


def a_recovery() -> str:
    """The actor a recovery runs as, a new one each time (``base.recovery.actor_of``)."""
    return actor_of(uuid.uuid7())


def brought_back(name: str, recovery: str, **fields) -> Category:
    """A category ``recovery`` made again with ``name``, as the categories' part leaves it in the business."""
    return make_category(name, created_by=recovery, **fields)


def put_back(services: list[dict], subcategories: list[dict], recovery: str) -> None:
    """Each link created as the platform does, as ``recovery``."""
    for one in services:
        create(one, "service.service.return_to_category", recovery)
    for one in subcategories:
        create(one, "service.category.return_to_parent", recovery)


def test_a_category_made_again_gets_back_what_the_business_kept_where_its_deletion_left_it_each_by_its_link():
    tax = make_tax("test.service", "Service — test")
    hair = make_category("Hair")
    gone = make_category("Color", parent=hair, is_deleted=True, deleted_at=timezone.now())
    # Where deleting it left them: its services without a category, its subcategory under its parent.
    gloss, perm = make_service("Gloss", tax=tax), make_service("Old perm", tax=tax, is_active=False)
    toning = make_category("Toning", parent=hair)
    copy = a_category_of_the_copy(gone, service_ids=[gloss.pk, perm.pk, uuid.uuid7()])
    # One the business deleted too comes back by Categories' own part, into it by its name: the deleted one stays.
    pastel = make_category("Pastel", parent=hair, is_deleted=True, deleted_at=timezone.now())
    in_copy = [
        a_category_of_the_copy(hair),
        copy,
        a_category_of_the_copy(toning, parent_id=gone.pk),
        a_category_of_the_copy(pastel, parent_id=gone.pk),
    ]
    [record, _pastel] = queries.recovery.categories_not_in_business(in_copy)
    recovery = a_recovery()

    made = create(record, "service.category.recover", recovery)

    # Made again, and nothing of the business's moved yet: that goes back by links of its own, counted apart.
    assert (made.name, made.parent_id, made.left_out) == ("Color", hair.pk, [])
    assert made.id != gone.pk
    assert set(Service.objects.filter(pk__in=[gloss.pk, perm.pk]).values_list("category", flat=True)) == {None}
    assert Category.objects.get(pk=toning.pk).parent_id == hair.pk

    services = queries.recovery.service_links_not_in_business(in_copy)
    subcategories = queries.recovery.subcategory_links_not_in_business(in_copy)

    assert services == [
        {"id": one, "service_id": one, "category_id": made.id} for one in sorted([gloss.pk, perm.pk])
    ]
    assert subcategories == [{"id": toning.pk, "category_id": toning.pk, "parent_id": made.id, "stands_for": gone.pk}]
    put_back(services, subcategories, recovery)
    assert dict(Service.objects.filter(pk__in=[gloss.pk, perm.pk]).values_list("pk", "category")) == {
        gloss.pk: made.id,
        perm.pk: made.id,
    }
    assert Category.objects.get(pk=toning.pk).parent_id == made.id
    assert Category.objects.get(pk=pastel.pk).parent_id == hair.pk
    # Who put each one back is written on it, as on any change of the screen.
    assert set(Service.objects.filter(pk__in=[gloss.pk, perm.pk]).values_list("updated_by", flat=True)) == {recovery}
    assert Category.objects.get(pk=toning.pk).updated_by == recovery
    # Asked again, nothing goes back twice.
    assert queries.recovery.service_links_not_in_business(in_copy) == []
    assert queries.recovery.subcategory_links_not_in_business(in_copy) == []


def test_a_lost_category_gets_back_the_subcategories_its_loss_left_at_the_root():
    toning = make_category("Toning")
    copy = a_category_of_the_copy(name="Color")
    in_copy = [copy, a_category_of_the_copy(toning, parent_id=copy["id"])]
    [record] = queries.recovery.categories_not_in_business(in_copy)
    recovery = a_recovery()
    made = create(record, "service.category.recover", recovery)

    [link] = queries.recovery.subcategory_links_not_in_business(in_copy)
    put_back([], [link], recovery)

    assert link == {"id": toning.pk, "category_id": toning.pk, "parent_id": made.id, "stands_for": copy["id"]}
    assert Category.objects.get(pk=toning.pk).parent_id == made.id


def test_what_the_business_moved_since_stays_where_it_is_and_the_category_says_it_came_back_without_it():
    tax = make_tax("test.service", "Service — test")
    hair = make_category("Hair")
    gone = make_category("Color", is_deleted=True, deleted_at=timezone.now())
    # Moved by hand since its deletion: a service into Hair, a subcategory from the root into Hair.
    balayage = make_service("Balayage", tax=tax, category=hair)
    toning = make_category("Toning", parent=hair)
    in_copy = [a_category_of_the_copy(gone, service_ids=[balayage.pk]), a_category_of_the_copy(toning, parent_id=gone.pk)]
    [record] = queries.recovery.categories_not_in_business(in_copy)

    made = create(record, "service.category.recover", a_recovery())

    assert [(one.code, str(subject) in one.message) for one, subject in zip(made.left_out, (balayage.pk, toning.pk))] == [
        ("service.service_moved", True),
        ("service.subcategory_moved", True),
    ]
    assert queries.recovery.service_links_not_in_business(in_copy) == []
    assert queries.recovery.subcategory_links_not_in_business(in_copy) == []
    assert Service.objects.get(pk=balayage.pk).category_id == hair.pk
    assert Category.objects.get(pk=toning.pk).parent_id == hair.pk


def test_a_subcategory_whose_return_would_close_a_loop_stays_where_it_is_and_is_said():
    gone = make_category("Color", is_deleted=True, deleted_at=timezone.now())
    # Left at the root by the deletion; since then the business hung Hair, Color's parent in the copy, from it.
    toning = make_category("Toning")
    hair = make_category("Hair", parent=toning)
    in_copy = [
        a_category_of_the_copy(hair, parent_id=None),
        a_category_of_the_copy(gone, parent_id=hair.pk),
        a_category_of_the_copy(toning, parent_id=gone.pk),
    ]
    [record] = queries.recovery.categories_not_in_business(in_copy)

    made = create(record, "service.category.recover", a_recovery())

    assert made.parent_id == hair.pk
    assert [(one.code, str(toning.pk) in one.message) for one in made.left_out] == [("service.subcategory_loop", True)]
    assert queries.recovery.subcategory_links_not_in_business(in_copy) == []
    assert Category.objects.get(pk=toning.pk).parent_id is None


@pytest.mark.parametrize("held", ["kept", "made_again_by_hand"])
def test_a_category_the_business_kept_or_made_again_by_hand_is_its_own_and_gets_nothing_back_by_links(held):
    tax = make_tax("test.service", "Service — test")
    # Untouched since before the category came to be, without a category and at the root.
    gloss, toning = make_service("Gloss", tax=tax), make_category("Toning")
    # Brought back by an earlier recovery and kept since: the copy's own, live under its id.
    color = brought_back("Color", a_recovery())
    if held == "made_again_by_hand":
        Category.objects.filter(pk=color.pk).update(is_deleted=True, deleted_at=timezone.now())
        make_category("COLOR", created_by="Ana Gil")
    in_copy = [a_category_of_the_copy(color, service_ids=[gloss.pk]), a_category_of_the_copy(toning, parent_id=color.pk)]

    assert queries.recovery.service_links_not_in_business(in_copy) == []
    assert queries.recovery.subcategory_links_not_in_business(in_copy) == []


def touched_since_it_came_back(recovery: str) -> tuple[list[dict], Category, Category, tuple]:
    """A deleted Color that had Cut and Gloss inside and Kids and Toning under it, brought back by ``recovery``, and then
    Gloss and Toning changed by hand, without a category or at the root still: the copy's categories, the one brought
    back, the deleted one, and Cut, Gloss, Kids and Toning."""
    tax = make_tax("test.service", "Service — test")
    gone = make_category("Color", is_deleted=True, deleted_at=timezone.now())
    cut, gloss = make_service("Cut", tax=tax), make_service("Gloss", tax=tax)
    kids, toning = make_category("Kids"), make_category("Toning")
    back = brought_back("Color", recovery)
    gloss.notes = "Ask about the shade"
    gloss.save()
    toning.icon = "ion:color-palette-outline"
    toning.save()
    in_copy = [
        a_category_of_the_copy(gone, service_ids=[cut.pk, gloss.pk]),
        a_category_of_the_copy(kids, parent_id=gone.pk),
        a_category_of_the_copy(toning, parent_id=gone.pk),
    ]
    return in_copy, back, gone, (cut, gloss, kids, toning)


def test_what_the_business_touched_after_the_category_came_back_stays_as_it_is():
    # Changed by hand after it came back, without a category or at the root still: as when it is asked again.
    in_copy, back, gone, (cut, _gloss, kids, _toning) = touched_since_it_came_back(a_recovery())

    assert queries.recovery.service_links_not_in_business(in_copy) == [{"id": cut.pk, "service_id": cut.pk, "category_id": back.pk}]
    assert queries.recovery.subcategory_links_not_in_business(in_copy) == [
        {"id": kids.pk, "category_id": kids.pk, "parent_id": back.pk, "stands_for": gone.pk}
    ]


def test_what_the_business_changed_while_the_recovery_that_brought_its_category_back_runs_goes_for_its_link_to_say_why():
    recovery = a_recovery()
    # Changed by hand while the same recovery goes on, without a category or at the root still.
    in_copy, back, gone, (cut, gloss, kids, toning) = touched_since_it_came_back(recovery)

    with giving_back(recovery):
        services = queries.recovery.service_links_not_in_business(in_copy)
        subcategories = queries.recovery.subcategory_links_not_in_business(in_copy)
    # Another recovery at work, asked again: what the business touched since stays out, and nothing says otherwise.
    with giving_back(a_recovery()):
        services_again = queries.recovery.service_links_not_in_business(in_copy)
        subcategories_again = queries.recovery.subcategory_links_not_in_business(in_copy)

    assert services == [{"id": one.pk, "service_id": one.pk, "category_id": back.pk} for one in (cut, gloss)]
    assert subcategories == [
        {"id": one.pk, "category_id": one.pk, "parent_id": back.pk, "stands_for": gone.pk} for one in (kids, toning)
    ]
    assert services_again == services[:1]
    assert subcategories_again == subcategories[:1]


def links_of(recovery: str, *, services=(), subcategories=()) -> tuple[list[dict], list[dict]]:
    """The links of a deleted Color with ``services`` and ``subcategories`` inside, read once ``recovery`` brought it
    back: each at the root still, untouched since."""
    gone = make_category("Color", is_deleted=True, deleted_at=timezone.now())
    brought_back("Color", recovery)
    in_copy = [a_category_of_the_copy(gone, service_ids=[one.pk for one in services])]
    in_copy += [a_category_of_the_copy(one, parent_id=gone.pk) for one in subcategories]
    return queries.recovery.service_links_not_in_business(in_copy), queries.recovery.subcategory_links_not_in_business(in_copy)


def changed_once_its_link_was_read() -> tuple[str, dict, dict, Service, Category]:
    """Gloss and Toning, read to go back into the Color a recovery brought back, then changed by hand, neither moved:
    the recovery, their links and the two."""
    tax = make_tax("test.service", "Service — test")
    gloss, toning = make_service("Gloss", tax=tax), make_category("Toning")
    recovery = a_recovery()
    [service], [subcategory] = links_of(recovery, services=[gloss], subcategories=[toning])
    Service.objects.filter(pk=gloss.pk).update(price=3600, updated_at=timezone.now())
    Category.objects.filter(pk=toning.pk).update(icon="ion:color-palette-outline", updated_at=timezone.now())
    return recovery, service, subcategory, gloss, toning


def test_one_the_business_changed_after_its_category_came_back_stays_as_it_is_and_says_why():
    recovery, service, subcategory, gloss, toning = changed_once_its_link_was_read()

    with pytest.raises(Conflict) as changed:
        create(service, "service.service.return_to_category", recovery)
    with pytest.raises(Conflict) as changed_too:
        create(subcategory, "service.category.return_to_parent", recovery)

    assert (changed.value.code, changed_too.value.code) == ("service.service_changed", "service.subcategory_changed")
    assert str(gloss.pk) in changed.value.message and str(toning.pk) in changed_too.value.message
    assert Service.objects.get(pk=gloss.pk).category_id is None
    assert Category.objects.get(pk=toning.pk).parent_id is None


def test_why_one_the_business_changed_stays_out_is_said_in_the_language_it_is_put_back_in():
    recovery, service, subcategory, gloss, toning = changed_once_its_link_was_read()

    with translation.override("es"):
        with pytest.raises(Conflict) as changed:
            create(service, "service.service.return_to_category", recovery)
        with pytest.raises(Conflict) as changed_too:
            create(subcategory, "service.category.return_to_parent", recovery)
        spanish = (SERVICE_CHANGED_LEFT % {"service": gloss.pk}, SUBCATEGORY_CHANGED_LEFT % {"category": toning.pk})

    assert (changed.value.message, changed_too.value.message) == spanish
    assert changed.value.message != SERVICE_CHANGED_LEFT % {"service": gloss.pk}
    assert changed_too.value.message != SUBCATEGORY_CHANGED_LEFT % {"category": toning.pk}


def test_one_the_business_moved_after_its_link_was_read_stays_where_it_put_it_and_says_why():
    tax = make_tax("test.service", "Service — test")
    hair = make_category("Hair")
    balayage, toning = make_service("Balayage", tax=tax), make_category("Toning")
    recovery = a_recovery()
    [service], [subcategory] = links_of(recovery, services=[balayage], subcategories=[toning])
    Service.objects.filter(pk=balayage.pk).update(category=hair)
    Category.objects.filter(pk=toning.pk).update(parent=hair)

    with pytest.raises(Conflict) as moved:
        create(service, "service.service.return_to_category", recovery)
    with pytest.raises(Conflict) as moved_too:
        create(subcategory, "service.category.return_to_parent", recovery)

    assert (moved.value.code, moved_too.value.code) == ("service.service_moved", "service.subcategory_moved")
    assert str(balayage.pk) in moved.value.message and str(toning.pk) in moved_too.value.message
    assert Service.objects.get(pk=balayage.pk).category_id == hair.pk
    assert Category.objects.get(pk=toning.pk).parent_id == hair.pk


def test_a_subcategory_hung_since_its_link_was_read_so_that_its_return_closes_a_loop_stays_where_it_is():
    toning = make_category("Toning")
    recovery = a_recovery()
    [], [subcategory] = links_of(recovery, subcategories=[toning])
    Category.objects.filter(pk=subcategory["parent_id"]).update(parent=toning)

    with pytest.raises(Conflict) as loop:
        create(subcategory, "service.category.return_to_parent", recovery)

    assert loop.value.code == "service.subcategory_loop"
    assert Category.objects.get(pk=toning.pk).parent_id is None


def test_a_category_an_earlier_recovery_brought_back_is_the_businesss_and_takes_nothing_back():
    tax = make_tax("test.service", "Service — test")
    gloss, toning = make_service("Gloss", tax=tax), make_category("Toning")
    [service], [subcategory] = links_of(a_recovery(), services=[gloss], subcategories=[toning])

    now = a_recovery()
    with pytest.raises(Conflict) as kept:
        create(service, "service.service.return_to_category", now)
    with pytest.raises(Conflict) as kept_too:
        create(subcategory, "service.category.return_to_parent", now)

    assert (kept.value.code, kept_too.value.code) == ("service.category_brought_earlier",) * 2
    assert Service.objects.get(pk=gloss.pk).category_id is None
    assert Category.objects.get(pk=toning.pk).parent_id is None


@pytest.mark.parametrize("name", ["service.service.return_to_category", "service.category.return_to_parent"])
def test_putting_back_what_a_category_had_inside_is_only_the_systems(name):
    op = get(name)

    assert op.permission == "service.system"
    assert not ctx_for("hub_owner").has(op.permission)


def test_what_a_category_came_back_without_is_said_in_the_language_it_is_made_in():
    tax = make_tax("test.service", "Service — test")
    gone = make_category("Color", is_deleted=True, deleted_at=timezone.now())
    balayage = make_service("Balayage", tax=tax, category=make_category("Hair"))
    [record] = queries.recovery.categories_not_in_business([a_category_of_the_copy(gone, service_ids=[balayage.pk])])

    with translation.override("es"):
        [said] = create(record, "service.category.recover").left_out
        spanish = SERVICE_MOVED_LEFT % {"service": balayage.pk}

    assert said.message == spanish
    assert said.message != SERVICE_MOVED_LEFT % {"service": balayage.pk}


def test_making_a_category_again_with_what_it_had_inside_is_only_the_systems():
    op = get("service.category.recover")

    assert op.permission == "service.system"
    assert not ctx_for("hub_owner").has(op.permission)


def test_a_service_whose_category_came_back_goes_into_it():
    tax = make_tax("test.service", "Service — test")
    gone = make_category("Color", is_deleted=True, deleted_at=timezone.now())
    # What the categories' part of the same recovery created just before, by its create: a new one, the same name.
    back = make_category("Color")
    services = [a_service_of_the_copy(name="Highlights", category_id=gone.pk, tax_category_id=tax.pk)]

    [record] = queries.recovery.services_not_in_business(services)

    assert record["category_id"] == back.pk
    made = create(record)
    # Asked again: the one brought back into it is the business's.
    assert queries.recovery.services_in_business(services) == {services[0]["id"]: made.id}


def test_a_category_the_business_renamed_since_is_the_same_one_whoever_took_its_old_name():
    tax = make_tax("test.service", "Service — test")
    hair = make_category("Hair")
    copy = [a_category_of_the_copy(hair), a_category_of_the_copy(name="Kids", parent_id=hair.pk)]
    services = [a_service_of_the_copy(name="Fringe trim", category_id=hair.pk, tax_category_id=tax.pk)]
    # Renamed since, and its old name taken by one made after: the copy's is the renamed one, by its id before any name.
    Category.objects.filter(pk=hair.pk).update(name="Styling")
    make_category("Hair")

    [kids] = queries.recovery.categories_not_in_business(copy)
    [record] = queries.recovery.services_not_in_business(services)

    assert kids["parent_id"] == hair.pk
    assert record["category_id"] == hair.pk
