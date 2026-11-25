"""What changes an appointment that exists: a move, an edit or a bulk delete says what it needs."""

import uuid

from apps.appointment.schemas.changes import BulkDeleteIn, RescheduleIn, UpdateIn

from .schema_checks import ID, MONDAY, errors


def test_a_move_says_what_changes():
    assert not errors(RescheduleIn, number="APT-1", start=f"{MONDAY}T11:00")
    assert not errors(RescheduleIn, number="APT-1", staff="Bea")
    assert "__all__" in errors(RescheduleIn, number="APT-1")
    assert "services" in errors(RescheduleIn, number="APT-1", services=[])


def test_an_edit_sends_only_what_changes():
    edit = UpdateIn.model_validate({"id": ID, "notes": "Formula 7/1"})
    assert edit.model_fields_set == {"id", "notes"}
    assert "__all__" in errors(UpdateIn, id=ID)


def test_a_bulk_delete_names_one_to_a_hundred_appointments():
    assert not errors(BulkDeleteIn, ids=[ID])
    assert "ids" in errors(BulkDeleteIn, ids=[])
    assert "ids" in errors(BulkDeleteIn, ids=[str(uuid.uuid7()) for _ in range(101)])
