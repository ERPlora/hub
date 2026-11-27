"""Who takes a reservation or saves its rules is kept by the name a colleague reads, never their whole address."""

import pytest
from django.contrib.auth import get_user_model

from apps.reservation.models import Reservation, Settings
from base.models.profile import Profile

from .conftest import HUB_DB, book, ctx_for, open_week, run

pytestmark = HUB_DB

ADDRESS = "luis.qa@example.com"


@pytest.fixture
def invited():
    """A colleague invited from erplora.com: the account has no name of its own, only its address."""
    return get_user_model().objects.create_user(username="saas:0199-qa", first_name=ADDRESS, email=ADDRESS)


def test_without_a_name_anywhere_what_goes_before_the_at_is_kept(invited):
    open_week()

    taken = book(ctx_for(actor=invited))
    run("reservation.settings.update", {"default_duration_minutes": 60}, ctx_for(actor=invited))

    reservation = Reservation.objects.get(pk=taken.id)
    assert (reservation.created_by, reservation.updated_by, Settings.objects.get().updated_by) == ("luis.qa",) * 3


def test_their_my_profile_name_is_kept_when_they_have_one(invited):
    Profile.objects.create(username=invited.username, first_name="QA", last_name="Encargado")
    open_week()

    taken = book(ctx_for(actor=invited))

    assert Reservation.objects.get(pk=taken.id).created_by == "QA Encargado"
