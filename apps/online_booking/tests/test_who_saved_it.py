"""Who saves the booking page's settings is kept by the name a colleague reads, never their whole address."""

import pytest
from django.contrib.auth import get_user_model

from apps.online_booking.models import Settings
from base.models.profile import Profile

from .conftest import HUB_DB, run

pytestmark = HUB_DB

ADDRESS = "luis.qa@example.com"


@pytest.fixture
def invited():
    """A colleague invited from erplora.com: the account has no name of its own, only its address."""
    return get_user_model().objects.create_user(username="saas:0199-qa", first_name=ADDRESS, email=ADDRESS)


def test_without_a_name_anywhere_what_goes_before_the_at_is_kept(invited):
    run("online_booking.settings.update", {"page_title": "Salón Lucía"}, actor=invited)

    assert Settings.objects.get().updated_by == "luis.qa"


def test_their_my_profile_name_is_kept_when_they_have_one(invited):
    Profile.objects.create(username=invited.username, first_name="QA", last_name="Encargado")

    run("online_booking.settings.update", {"page_title": "Salón Lucía"}, actor=invited)

    assert Settings.objects.get().updated_by == "QA Encargado"
