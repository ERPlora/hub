"""Writes of the book's rules (``reservation.settings.update``)."""

import pytest
from live.errors import InvalidPayload, PermissionDenied

from apps.reservation.models import Settings

from .conftest import EMPLOYEE, HUB_DB, MANAGER, ctx_for, payload, run

pytestmark = HUB_DB


def test_the_settings_change_only_what_is_sent():
    saved = run(
        "reservation.settings.update",
        {"auto_confirm": True, "max_party_size": 12},
        ctx_for(MANAGER),
    )
    assert (saved.auto_confirm, saved.max_party_size, saved.require_phone) == (
        True,
        12,
        True,
    )
    assert Settings.objects.get().auto_confirm is True
    assert payload("reservation.settings.updated") == {
        "fields": ["auto_confirm", "max_party_size"]
    }
    with pytest.raises(PermissionDenied):
        run("reservation.settings.update", {"auto_confirm": False}, ctx_for(EMPLOYEE))


def test_the_minimum_guests_cannot_pass_the_maximum():
    # A 422 on its field: it is the form's mistake, not a state of the book.
    with pytest.raises(InvalidPayload) as caught:
        run("reservation.settings.update", {"min_party_size": 10, "max_party_size": 4})
    assert caught.value.fields == {"min_party_size": "The minimum guests cannot be more than the maximum."}
    assert not Settings.objects.exists()  # a refusal writes nothing, not even the factory row
