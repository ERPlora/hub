"""A colleague whose account has no name of its own, for the apps' tests of who acted (BASE-F119).

erplora.com names an account without a name by its address, and an account may also reach the Hub with its email and
no name. A colleague's address only reaches whoever sees the team's contact details, so an app names whoever acts by
the part before the «@» (``base.queries.people.actor_name``)."""

from django.contrib.auth import get_user_model
from django.test import Client

from base.models import Membership
from base.services.sessions import ensure_hub_user
from base.tenancy.tests.business import A

ADDRESS = "zoe.ruiz@example.com"
#: How an app names her: what goes before the «@».
SHOWN = "zoe.ruiz"
#: The two ways an account reaches the Hub without a name, by the id of each case.
NAMELESS = {"named-by-address": {"first_name": ADDRESS, "email": ADDRESS}, "email-only": {"email": ADDRESS}}


def signed_in(username: str, role: str = "hub_employee", **account) -> Client:
    """A person of business A with ``role``, signed in on their own device."""
    user = get_user_model().objects.create_user(username=username, password="pw", **account)
    Membership.objects.create(user=user, host=A.key, role=role)
    ensure_hub_user(user)
    client = Client()
    client.force_login(user)
    return client


#: Who acted, as a migration that names them without their address finds it kept: an account without a name (by its
#: address), a person, an API key whose name holds an «@», and nobody.
SAVED = (ADDRESS, "Luis García", "API · orders@shop.example", "")
#: The same once the migration ran, sorted: only the address lost what goes after its «@».
KEPT = sorted([SHOWN, "Luis García", "API · orders@shop.example", ""])


def written_by(apps, database, app: str, where) -> dict[tuple[str, str], list[str]]:
    """Who acted, sorted, on each ``(model, field)`` of ``where`` in ``app``, as the migration state ``apps`` reads
    ``database``."""
    rows = {model: apps.get_model(app, model).objects.using(database.alias) for model, _ in where}
    return {(model, field): sorted(rows[model].values_list(field, flat=True)) for model, field in where}
