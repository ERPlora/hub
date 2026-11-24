"""Support access: whether ERPlora's support staff may come into this business to help set it up (BASE-F126).

It comes off. Whoever runs the business (``base.administer_hub``: the owner and the administrators) turns it on and
off, and each change leaves ``base.support_access.changed`` in the outbox with the row it saved. Anyone of the
business reads it, with who changed it last, whether they may change it and the latest entries of support, the most
recent first. One business's setting is not another's.
"""

import datetime as dt
import json

import pytest
from django.db import IntegrityError
from django.utils import timezone
from live.models import OutboxEvent
from live.operations import atomic

from base.models import Membership
from base.models.support_access import SupportAccess, SupportVisit
from base.tenancy.context import use_hub
from base.tenancy.tests.business import HOST, HUB_DB, A, B, in_business_a

__all__ = ["in_business_a"]

pytestmark = HUB_DB

HOST_B = f"{B.key}.localhost"
OFF = {"enabled": False, "can_change": True, "updated_by": "", "updated_at": None, "visits": []}


def get(client, host=HOST):
    return client.get("/api/support-access", HTTP_HOST=host)


def update(client, enabled: bool, host=HOST):
    body = json.dumps({"enabled": enabled})
    return client.post("/api/support-access/update", body, content_type="application/json", HTTP_HOST=host)


def changes() -> list[dict]:
    return [event.payload for event in OutboxEvent.objects.filter(name="base.support_access.changed").order_by("id")]


@pytest.fixture
def olga(make_user, client):
    user = make_user("saas:1", host=A.key, role=Membership.Role.OWNER, first_name="Olga")
    client.force_login(user)
    return user


class TestTheSetting:
    def test_it_comes_off_with_no_entries(self, client, olga):
        response = get(client)
        assert response.status_code == 200, response.content
        assert response.json() == OFF

    def test_the_owner_turns_it_on_and_off_and_each_change_is_in_the_outbox(self, client, olga):
        on = update(client, True)
        assert on.status_code == 200, on.content
        assert on.json()["enabled"] is True and on.json()["updated_by"] == "Olga"
        assert on.json()["updated_at"] is not None
        assert get(client).json()["enabled"] is True
        off = update(client, False)
        assert off.status_code == 200, off.content
        assert off.json()["enabled"] is False
        assert changes() == [{"enabled": True}, {"enabled": False}]
        assert SupportAccess.objects.count() == 1

    def test_an_administrator_changes_it_too(self, client, make_user, olga):
        client.force_login(make_user("saas:2", host=A.key, role=Membership.Role.ADMIN, first_name="Adri"))
        on = update(client, True)
        assert on.status_code == 200, on.content
        assert on.json()["updated_by"] == "Adri"

    @pytest.mark.parametrize("role", [Membership.Role.MANAGER, Membership.Role.EMPLOYEE])
    def test_anyone_else_reads_it_and_cannot_change_it(self, client, make_user, olga, role):
        update(client, True)
        client.force_login(make_user("saas:3", host=A.key, role=role, first_name="Eva"))
        read = get(client).json()
        assert (read["enabled"], read["can_change"], read["updated_by"]) == (True, False, "Olga")
        refused = update(client, False)
        assert refused.status_code == 403
        assert refused.json()["error"]["code"] == "permission_denied"
        assert get(client).json()["enabled"] is True
        assert changes() == [{"enabled": True}]

    def test_nobody_without_a_session(self, client, olga):
        client.logout()
        assert get(client).status_code == 401
        assert update(client, True).status_code == 401
        assert not SupportAccess.objects.exists()

    def test_one_business_setting_is_not_anothers(self, client, make_user, olga, hub_b):
        client.force_login(make_user("saas:4", host=B.key, role=Membership.Role.OWNER, first_name="Bea"))
        assert update(client, True, host=HOST_B).json()["enabled"] is True
        client.force_login(olga)
        assert get(client).json() == OFF
        with use_hub(hub_b):
            assert SupportAccess.objects.get().enabled is True

    def test_a_business_keeps_one_row(self, olga):
        SupportAccess.objects.create()
        with pytest.raises(IntegrityError), atomic():
            SupportAccess.objects.create()


class TestTheEntries:
    def test_the_last_ten_the_most_recent_first(self, client, olga):
        now = timezone.now()
        for minutes in (11, 0, 5, 1, 9, 2, 8, 3, 7, 4, 10, 6):
            SupportVisit.objects.create(
                username=f"saas-support:{minutes}",
                name=f"Support {minutes}",
                entered_at=now - dt.timedelta(minutes=minutes),
            )
        visits = get(client).json()["visits"]
        assert [visit["person"] for visit in visits] == [f"Support {minutes}" for minutes in range(10)]
        assert set(visits[0]) == {"person", "entered_at"}

    def test_an_entry_without_a_name_says_its_email(self, client, olga):
        SupportVisit.objects.create(username="saas-support:7", email="sam@erplora.com")
        assert [visit["person"] for visit in get(client).json()["visits"]] == ["sam@erplora.com"]
