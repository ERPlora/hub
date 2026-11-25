"""Who acted on a method or a payment, kept as a colleague reads them and cut to fit the column it is kept in."""

from apps.payment.models import ACTOR_MAX_LENGTH
from apps.payment.services import actor

from .conftest import ctx_for


def test_the_platform_or_an_api_key_is_kept_as_it_names_itself():
    assert actor._actor(ctx_for(actor="tester")) == "tester"


def test_a_name_longer_than_its_column_is_cut_to_fit():
    assert actor._actor(ctx_for(actor="x" * 200)) == "x" * ACTOR_MAX_LENGTH
