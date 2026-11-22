"""Whose a staff record is, for the apps that count a person's own: the live record linked to the person the business
knows by a username, which an API key's maker is known by too (BASE-F125)."""

from apps.staff.models import Member
from apps.staff.queries.records import records_of
from base.models import HubUser

from .conftest import HUB_DB, make_member

pytestmark = HUB_DB


def test_a_person_s_live_record_is_theirs():
    make_member(first_name="Bea", user=HubUser.objects.create(username="saas:bea"))
    record = make_member(user=HubUser.objects.create(username="saas:ana"))

    assert records_of("saas:ana") == frozenset({record.pk})


def test_a_colleague_s_record_is_never_theirs():
    make_member(first_name="Bea", user=HubUser.objects.create(username="saas:bea"))
    make_member(first_name="Nobody's")
    HubUser.objects.create(username="saas:carla")

    assert (records_of("saas:carla"), records_of("saas:nobody")) == (frozenset(), frozenset())


def test_a_terminated_record_or_none_at_all_is_nothing():
    make_member(user=HubUser.objects.create(username="saas:ana"), status=Member.Status.TERMINATED)
    HubUser.objects.create(username="saas:carla")

    assert (records_of("saas:ana"), records_of("saas:carla"), records_of("saas:nobody")) == (frozenset(),) * 3
