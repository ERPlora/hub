"""Writes of base that are not operations: opening the Hub's session for the person the SaaS vouched for.

Not an ``@operation``: it runs before there is an actor, for ``/auth/callback`` only, and needs the
request to log in. Phase 1 keeps it on ``django.contrib.auth`` + ``Membership``; phase 2 replaces
it with the hub's ``DeviceSession`` (PLAN-SAAS §2.1).

Two doors, each with its own local copy of the SaaS account: a customer entering their hub
(:func:`open_session_from_saas`, ``saas:<id>``, never staff) and the platform's staff entering the
Hub admin on the platform host (:func:`open_admin_session_from_saas`, ``saas-staff:<id>``, round 13,
PLAN §18.1). Separate copies, so an account that is both staff and a hub member neither loses
``is_staff`` in the admin nor gains it on its hub when it enters by the other door.
"""

from django.contrib.auth import get_user_model, login
from django.contrib.auth.hashers import make_password
from django.contrib.auth.models import Group, Permission
from django.db import transaction
from django.http import HttpRequest

from base.auth import PLATFORM_ADMIN, PLATFORM_SUPPORT, RedeemedUser
from base.models import Membership

MODEL_BACKEND = "django.contrib.auth.backends.ModelBackend"
#: The SaaS account the session belongs to, for /internal/sessions/revoke (phase 2).
SAAS_USER_ID_SESSION_KEY = "saas_user_id"
#: Read-only group of ``platform_support`` in the Hub admin (the SaaS's ``support``). Phase 2
#: replaces it with the ``StaffUser`` mark (PLAN §17).
SUPPORT_GROUP = "support"


class InactiveUser(Exception):
    """The Hub's copy of the user was deactivated (in the admin): no session, whatever the SaaS says."""


def username_for(saas_user_id: str) -> str:
    """The customer copy of a SaaS account (hub door)."""
    return f"saas:{saas_user_id}"


def staff_username_for(saas_user_id: str) -> str:
    """The staff copy of a SaaS account (Hub admin door); never has a ``Membership``."""
    return f"saas-staff:{saas_user_id}"


def _local_copy(redeemed: RedeemedUser, *, username: str, is_staff: bool, is_superuser: bool):
    """Get or create ``username`` and make it say what the SaaS says; ``InactiveUser`` if deactivated."""
    user_model = get_user_model()
    first_name = redeemed.name[: user_model._meta.get_field("first_name").max_length]
    wanted = {"email": redeemed.email, "first_name": first_name, "is_staff": is_staff, "is_superuser": is_superuser}
    # get_or_create: two first entries at once end in one user, not an IntegrityError.
    user, _ = user_model.objects.get_or_create(
        username=username,
        defaults={**wanted, "password": make_password(None)},
    )
    if not user.is_active:
        raise InactiveUser(user.username)
    changed = [field for field, value in wanted.items() if getattr(user, field) != value]
    if changed:
        for field in changed:
            setattr(user, field, wanted[field])
        user.save(update_fields=changed)
    return user


def _log_in(request: HttpRequest, user, redeemed: RedeemedUser) -> None:
    login(request, user, backend=MODEL_BACKEND)
    request.session[SAAS_USER_ID_SESSION_KEY] = redeemed.user_id


@transaction.atomic
def open_session_from_saas(request: HttpRequest, redeemed: RedeemedUser, slug: str):
    """Get or create the customer copy, set its role on ``slug`` and log it in (a new session key).

    The local user is a copy of a customer of the SaaS: never staff nor superuser, so a hub role
    never opens the Hub's ``/admin/`` (that one belongs to the platform's staff). A copy raised to
    staff by hand is lowered again here.
    """
    user = _local_copy(redeemed, username=username_for(redeemed.user_id), is_staff=False, is_superuser=False)
    Membership.objects.update_or_create(user=user, host=slug, defaults={"role": redeemed.role})
    _log_in(request, user, redeemed)
    return user


@transaction.atomic
def open_admin_session_from_saas(request: HttpRequest, redeemed: RedeemedUser):
    """Log the platform's staff into the Hub admin (a new session key), as the SaaS vouched.

    ``platform_admin`` is staff and superuser; ``platform_support`` is staff in the read-only
    ``support`` group. Any other role is a programming error: ``base.auth`` refuses it first. The
    session is for the account's staff copy, never for its customer copy.
    """
    if redeemed.role not in (PLATFORM_ADMIN, PLATFORM_SUPPORT):
        raise ValueError(f"The Hub admin takes only a platform role, not {redeemed.role!r}.")
    superuser = redeemed.role == PLATFORM_ADMIN
    user = _local_copy(
        redeemed, username=staff_username_for(redeemed.user_id), is_staff=True, is_superuser=superuser
    )
    support = _support_group()
    if superuser:
        user.groups.remove(support)
    else:
        user.groups.add(support)
    _log_in(request, user, redeemed)
    return user


def _support_group() -> Group:
    """The ``support`` group with every ``view_*`` permission and nothing else (created on first use)."""
    group, _ = Group.objects.get_or_create(name=SUPPORT_GROUP)
    group.permissions.set(Permission.objects.filter(codename__startswith="view_"))
    return group
