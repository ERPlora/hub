"""Writes of the service categories: create, edit and delete, keeping the tree they hang in free of loops."""

import pytest
from live.errors import Conflict, InvalidPayload, NotFound, PermissionDenied

from apps.service.models.catalog import Category

from .conftest import HUB_DB, events, make_category, make_service, run

pytestmark = HUB_DB


def test_create_a_category_inside_another_one():
    hair = make_category("Hair")
    out = run(
        "service.category.create", {"name": "Colour", "parent": "hair", "sort_order": 3}
    )
    assert (out.parent_id, out.parent_name, out.sort_order, out.service_count) == (
        hair.id,
        "Hair",
        3,
        0,
    )
    assert events() == ["service.category.created"]


def test_a_category_name_is_taken_ignoring_case_and_spaces():
    make_category("Hair")
    with pytest.raises(Conflict) as taken:
        run("service.category.create", {"name": "  HAIR "})
    assert taken.value.code == "service.category_name_taken"
    assert taken.value.fields == {
        "name": "There is already a category with that name. Pick another name."
    }


def test_a_deleted_parent_is_not_available():
    gone = make_category("Gone", is_deleted=True)
    with pytest.raises(InvalidPayload) as refused:
        run("service.category.create", {"name": "Colour", "parent_id": str(gone.id)})
    assert refused.value.code == "service.parent_category_unavailable"
    assert "parent_id" in refused.value.fields


def test_a_category_never_hangs_from_itself_or_from_one_of_its_children():
    hair = make_category("Hair")
    colour = make_category("Colour", parent=hair)
    blonde = make_category("Blonde", parent=colour)
    for parent in (hair, blonde):
        with pytest.raises(InvalidPayload) as refused:
            run(
                "service.category.update",
                {"id": str(hair.id), "parent_id": str(parent.id)},
            )
        assert refused.value.code == "service.category_cycle"
        assert refused.value.fields == {
            "parent_id": "A category cannot hang from itself or from one of its subcategories."
        }


def test_an_edit_changes_what_it_sends_and_null_makes_it_a_root():
    hair = make_category("Hair")
    colour = make_category("Colour", parent=hair, sort_order=1)
    out = run(
        "service.category.update",
        {"category": "colour", "parent_id": None, "name": "Colours"},
    )
    assert (out.name, out.parent_id, out.sort_order) == ("Colours", None, 1)
    assert events() == ["service.category.updated"]
    assert colour.id == out.id


def test_deleting_a_category_frees_its_services_and_lifts_its_children(tax):
    hair = make_category("Hair")
    colour = make_category("Colour", parent=hair)
    blonde = make_category("Blonde", parent=colour)
    cut = make_service("Cut", tax=tax, category=colour)
    run("service.category.delete", {"id": str(colour.id)})
    colour.refresh_from_db()
    blonde.refresh_from_db()
    cut.refresh_from_db()
    assert (
        colour.is_deleted,
        colour.deleted_at is not None,
        blonde.parent,
        cut.category,
    ) == (True, True, hair, None)
    assert events() == ["service.category.deleted"]
    with pytest.raises(NotFound) as gone:
        run("service.category.delete", {"id": str(colour.id)})
    assert gone.value.message == "That category does not exist in this business."
    assert run("service.category.create", {"name": "colour"}).name == "colour"


def test_only_the_owner_and_the_admin_delete_categories():
    hair = make_category("Hair")
    with pytest.raises(PermissionDenied):
        run("service.category.delete", {"id": str(hair.id)}, role="hub_manager")


def test_categories_that_already_loop_are_refused_and_deleted_without_crashing():
    # A loop left by a raw write (the database only forbids a category being its own parent).
    a, b, c = make_category("A"), make_category("B"), make_category("C")
    Category.objects.filter(pk=a.pk).update(parent=b)
    Category.objects.filter(pk=b.pk).update(parent=a)
    with pytest.raises(Conflict) as looped:
        run("service.category.update", {"id": str(c.id), "parent_id": str(a.id)})
    assert looped.value.code == "service.category_cycle"
    run("service.category.delete", {"id": str(a.id)})
    b.refresh_from_db()
    assert b.parent is None
