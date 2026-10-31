"""``manage.py demo_expire <slug>``: end a demo now and purge it at once (plan 2026-10-17, §1.7).

Support's tool and the e2e's clock: through its operations (``base.demo.expire``, then one pass of the reaper), in
every environment (not only ``DEBUG``), and it says how the demo was left.
"""

import hashlib
from io import StringIO

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import RequestFactory
from django.contrib.sessions.middleware import SessionMiddleware
from live.context import system_context

from base.models import DemoCode, Hub, Membership
from base.registry import REGISTRY_SCOPE
from base.schemas import DemoCodeIn, DemoCreateIn
from base.services import demo_code_create, demo_create, open_demo_session, redeem_demo_code

pytestmark = pytest.mark.django_db

OWNER = hashlib.sha256(b"ana's browser").hexdigest()


def entered_demo() -> str:
    """A demo its browser entered: made ready by the worker (``base.tenancy.provision``), a code spent and the
    owner's session open; its slug."""
    ctx = system_context(REGISTRY_SCOPE)
    slug = demo_create(ctx, DemoCreateIn(session_key=OWNER)).slug
    Hub.objects.filter(slug=slug).update(status="ready")
    redeemed = redeem_demo_code(slug, demo_code_create(ctx, DemoCodeIn(slug=slug, session_key=OWNER)).code)
    request = RequestFactory().post("/auth/callback")
    SessionMiddleware(lambda request: None).process_request(request)
    open_demo_session(request, redeemed.hub)
    return slug


def expire(slug: str) -> str:
    out = StringIO()
    call_command("demo_expire", slug, stdout=out)
    return out.getvalue()


@pytest.mark.parametrize("debug", [True, False])
def test_ends_the_demo_and_purges_it_at_once(settings, debug):
    settings.DEBUG = debug
    slug = entered_demo()
    output = expire(slug)
    hub = Hub.objects.get(slug=slug)
    assert (hub.status, hub.purged_at is not None) == ("purged", True)
    assert not Membership.objects.filter(host=slug).exists()
    assert not get_user_model().objects.filter(username=f"demo:{slug}").exists()
    assert not DemoCode.objects.filter(hub=hub).exists()
    assert output.strip() == f"{slug}: purged"


def test_a_demo_already_purged_says_so_again():
    slug = entered_demo()
    expire(slug)
    assert expire(slug).strip() == f"{slug}: purged"


@pytest.mark.parametrize("slug", ["demo-00000000", "a"])
def test_a_slug_that_names_no_demo_is_an_error_and_changes_nothing(slug):
    with pytest.raises(CommandError, match="no demo"):
        expire(slug)
    assert Hub.objects.get(slug="a").status == "ready"
