"""People of business A for the tests that check a colleague's email never shows where someone is named for what they
did (BASE-F119): erplora.com names an account without a name by its address, and an account may also have its email
and no name; a colleague's address only reaches whoever sees the team's contact details."""

from django.contrib.auth import get_user_model
from django.test import Client

from base.models import Membership
from base.services.sessions import ensure_hub_user
from base.tenancy.tests.business import A

ADDRESS = "zoe.ruiz@example.com"
#: How a colleague reads her: what goes before the «@».
SHOWN = "zoe.ruiz"

#: The two ways an account reaches the Hub without a name: named by its address, or with its email and no name.
NAMELESS = [{"first_name": ADDRESS, "email": ADDRESS}, {"email": ADDRESS}]
NAMELESS_IDS = ["named-by-address", "email-only"]


def signed_in(username: str, role: str = "hub_employee", **account):
    """A person of business A with ``role``, on their own device: ``(user, client)``."""
    user = get_user_model().objects.create_user(username=username, password="pw", **account)
    Membership.objects.create(user=user, host=A.key, role=role)
    ensure_hub_user(user)
    client = Client()
    client.force_login(user)
    return user, client
