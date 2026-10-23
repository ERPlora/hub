"""BASE-G52/G53: entering a hub with the erplora.com account (the SaaS's sign-in, or its panel: the same jump).

Every entry with the account makes this browser a device of the hub (``base.TrustedDevice``, the cookie
``hub_device``): from then on the PIN works on it. The session lasts what the device and the business allow, fixed
when it opens (12 h on a shared device, 30 days on a personal one, at most 1 h when the business always asks), and
its note (``base.SessionOwner``) says on which device and with which credential it was opened.
"""

import datetime as dt
from urllib.parse import parse_qs, urlsplit

import pytest
from django.test import Client
from django.utils import timezone

from base import access
from base.models import AccessSettings, SessionOwner, TrustedDevice
from base.tests.test_auth_views import a_code, callback, demo, host_of  # noqa: F401 (demo: a fixture)

pytestmark = pytest.mark.django_db

HOST = "a.localhost:8000"
ANDROID = "Mozilla/5.0 (Linux; Android 14; SM-T220) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0 Safari/537.36"


def enter(client, next_path="/", host=HOST, agent=ANDROID):
    """The jump to the SaaS and its auto-submitted form back, with this browser's state."""
    jump = client.get("/auth/login", {"next": next_path, "account": "1"}, HTTP_HOST=host)
    [state] = parse_qs(urlsplit(jump["Location"]).query)["state"]
    return client.post(
        "/auth/callback", {"code": "c1", "next": next_path, "state": state}, HTTP_HOST=host, HTTP_USER_AGENT=agent
    )


def device_cookie(response):
    return response.cookies[access.DEVICE_COOKIE]


class TestTheDevice:
    def test_entering_with_the_account_makes_this_browser_a_shared_device_of_the_hub(self, client, fake_saas):
        fake_saas()
        response = enter(client)
        cookie = device_cookie(response)
        assert cookie["httponly"] and cookie["samesite"] == "Lax" and cookie["path"] == "/"
        assert int(cookie["max-age"]) == access.DEVICE_COOKIE_MAX_AGE
        assert not cookie["domain"]  # this hub's host only: another hub never sees it
        device = TrustedDevice.objects.get()
        assert device.token_digest == access.token_digest(cookie.value)
        assert cookie.value not in device.token_digest
        assert (device.mode, device.agent) == (access.SHARED, "Chrome · Android")
        assert (device.last_username, device.last_user_label) == ("saas:42", "Ana")
        assert timezone.now() - device.last_entry_at < dt.timedelta(seconds=30)

    def test_entering_again_from_it_keeps_the_device_and_its_mode(self, client, fake_saas):
        fake_saas()
        enter(client)
        device = TrustedDevice.objects.get()
        TrustedDevice.objects.filter(pk=device.pk).update(mode=access.PERSONAL, name="Bar")
        again = enter(client)
        assert TrustedDevice.objects.count() == 1
        device.refresh_from_db()
        assert (device.mode, device.name) == (access.PERSONAL, "Bar")
        assert device.token_digest == access.token_digest(device_cookie(again).value)

    def test_a_browser_whose_device_was_removed_becomes_a_new_device(self, client, fake_saas):
        fake_saas()
        first = device_cookie(enter(client)).value
        TrustedDevice.objects.all().delete()
        second = device_cookie(enter(client)).value
        assert second != first
        assert TrustedDevice.objects.get().token_digest == access.token_digest(second)

    def test_another_browser_is_another_device(self, client, fake_saas):
        fake_saas()
        enter(client)
        enter(Client())
        assert TrustedDevice.objects.count() == 2

    def test_the_session_s_note_says_on_which_device_and_with_the_account(self, client, fake_saas):
        fake_saas()
        enter(client)
        owner = SessionOwner.objects.get()
        assert (owner.device_id, owner.credential) == (TrustedDevice.objects.get().pk, SessionOwner.Credential.ACCOUNT)

    def test_a_demo_s_visitor_is_no_device_of_it(self, client, fake_saas, demo):
        # A demo has no account behind it, nor a till to come back to with a PIN (plan 2026-10-17 §1.6).
        fake_saas()
        response = callback(client, {"code": a_code(demo), "next": "/"}, host=host_of(demo))
        assert response.status_code == 302
        assert access.DEVICE_COOKIE not in response.cookies
        assert not TrustedDevice.objects.exists()


class TestHowLongTheSessionLasts:
    def lasts(self, client):
        return client.session.get_expiry_date() - timezone.now()

    def test_a_shift_on_a_shared_device(self, client, fake_saas):
        fake_saas()
        enter(client)
        assert dt.timedelta(hours=11, minutes=59) < self.lasts(client) <= dt.timedelta(hours=12)

    def test_thirty_days_on_a_personal_device(self, client, fake_saas):
        fake_saas()
        enter(client)
        TrustedDevice.objects.update(mode=access.PERSONAL)
        enter(client)
        assert dt.timedelta(days=29, hours=23) < self.lasts(client) <= dt.timedelta(days=30)

    def test_at_most_an_hour_when_the_business_always_asks(self, client, fake_saas):
        fake_saas()
        AccessSettings.objects.create(pin_policy=access.ALWAYS)
        enter(client)
        TrustedDevice.objects.update(mode=access.PERSONAL)
        enter(client)
        assert dt.timedelta(minutes=59) < self.lasts(client) <= dt.timedelta(hours=1)

    def test_it_is_fixed_when_it_opens_and_using_it_does_not_make_it_longer(self, client, fake_saas):
        fake_saas()
        enter(client)
        until = client.session.get_expiry_date()
        session = client.session
        session["touched"] = True
        session.save()
        assert client.session.get_expiry_date() == until
