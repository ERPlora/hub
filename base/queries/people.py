"""The business's people and roles (``base.person.*``, ``base.role.list``, ``base.hub_user.get``) and how a person is
named in this hub."""

from typing import Any

from django.utils import translation
from django.utils.translation import gettext
from live.context import OperationContext
from live.errors import NotFound
from live.operations import AI, INTERNAL, operation

from base import access, people as people_rules
from base.models.access import Credential
from base.models import Hub, HubUser, Membership
from base.models.profile import Profile
from base.permissions import ADMINISTER_HUB, VIEW_HOME, permissions_of_role
from base.schemas.people import PersonDetailOut, PersonIn, PersonListIn, PersonListOut, RoleListIn, RoleListOut
from base.schemas.sessions import HubUserGetIn, HubUserOut

from .usage import _is_count


# ── People and permissions: people, roles ───────────────────────────────────────────────────────────────────────────


def people_of(slug: str) -> list[dict[str, Any]]:
    """The people of the business of ``slug``, owner first: those who entered (their ``Membership``, control's) and
    those the SaaS's last photo names that have not entered yet (``members``: erplora.com's accepted ones), each once,
    with what the hub keeps of their way in (``Credential``) and their name in it (``Profile``). Two reads per side,
    never a join: who is a member is control's and the ways in are the hub's."""
    found: dict[str, dict[str, Any]] = {}
    memberships = Membership.objects.filter(host=slug, user__is_active=True).select_related("user")
    for membership in memberships:
        user = membership.user
        found[user.get_username()] = {
            "user": user,
            "role": membership.role,
            "email": user.email,
            "name": user.get_full_name(),
            "entered": True,
        }
    for member in _photo_members(slug):
        username = f"{people_rules.SAAS_PREFIX}{member['user_id']}"
        if username not in found:
            found[username] = {
                "user": None,
                "role": member["role"],
                "email": member.get("email") or "",
                "name": member.get("name") or "",
                "entered": False,
            }
    credentials = {row.username: row for row in Credential.objects.filter(username__in=list(found))}
    profiles = {row.username: row for row in Profile.objects.filter(username__in=list(found))}
    people = []
    for username, person in found.items():
        credential = credentials.get(username)
        profile = profiles.get(username)
        own = f"{profile.first_name} {profile.last_name}".strip() if profile is not None else ""
        name = own or without_address(person["name"]) or without_address(person["email"]) or username
        people.append(
            {
                **person,
                "id": username,
                "name": name,
                "initials": access.initials(name),
                "credential": credential,
                "ways": people_rules.ways(
                    pin=bool(credential and credential.pin_hash), badge=bool(credential and credential.badge_digest)
                ),
            }
        )
    return sorted(people, key=lambda person: (people_rules.role_rank(person["role"]), person["name"].casefold()))


#: The roles the photo's ``members`` may carry: erplora.com's.
PHOTO_ROLES = frozenset(people_rules.ROLE_ORDER)


def _photo_members(slug: str) -> list[dict[str, Any]]:
    """The ``members`` of the SaaS's last photo of ``slug`` that are well formed; none without a photo."""
    state = Hub.objects.filter(slug=slug).values_list("state", flat=True).first()
    members = state.get("members") if isinstance(state, dict) else None
    if not isinstance(members, list):
        return []
    return [
        member
        for member in members
        if isinstance(member, dict) and str(member.get("user_id") or "") and member.get("role") in PHOTO_ROLES
    ]


def seats_of(slug: str, used: int) -> dict[str, Any]:
    """The places of the plan of the SaaS's last photo (``plan.max_users``; 0 is none) against ``used``."""
    state = Hub.objects.filter(slug=slug).values_list("state", flat=True).first()
    plan = state.get("plan") if isinstance(state, dict) and isinstance(state.get("plan"), dict) else None
    known = plan is not None and _is_count(plan.get("max_users"))
    limit = plan["max_users"] or None if known else None
    return {"known": known, "used": used, "limit": limit, "full": limit is not None and used >= limit}


def person_out(ctx: OperationContext, person: dict[str, Any]) -> dict[str, Any]:
    """A person as Employees shows them; their address only reaches whoever sees the team's contact details (the
    mark of ``PersonOut.email``)."""
    return {
        "id": person["id"],
        "name": person["name"],
        "initials": person["initials"],
        "email": person["email"],
        "role": person["role"],
        "ways": person["ways"],
        "entered": person["entered"],
        "me": signed_in_username(ctx) == person["id"],
    }


def is_a_person(actor: Any) -> bool:
    """Whether ``actor`` is a signed-in person (a control user), not the platform, an API key or nobody."""
    return hasattr(actor, "get_username") and bool(getattr(actor, "is_authenticated", False))


def hub_user_of(ctx: OperationContext) -> HubUser | None:
    """The caller's ``HubUser`` in the active hub's database, read only (``base.services.sessions.acting_hub_user``
    makes it); ``None`` for the platform, an API key, nobody, or a person who has none there yet."""
    if not is_a_person(ctx.actor):
        return None
    return HubUser.objects.filter(username=ctx.actor.get_username()).first()


# Not an assistant tool: what the cards of the writes that link a person read to name them (``REFERS``).
@operation("base.hub_user.get", kind="query", permission=VIEW_HOME, input=HubUserGetIn, output=HubUserOut, ai=INTERNAL)
def hub_user_get(ctx: OperationContext, data: HubUserGetIn) -> dict[str, Any]:
    """A person of this business by their id in its database (``base.HubUser``), with access to it (a ``Membership``
    on the scope's host, control's): how a staff record's user or a conversation's assignee is named on the
    assistant's card. Anyone else, here or in another business, is ``NotFound``."""
    person = HubUser.objects.filter(pk=data.id).first()
    if person is None or not Membership.objects.filter(host=ctx.scope.key, user__username=person.username).exists():
        raise NotFound(gettext("That person is not in this business."), code="base.person_not_found")
    return {"id": person.pk, "name": person.display_name}


def signed_in_username(ctx: OperationContext) -> str:
    return ctx.actor.get_username() if hasattr(ctx.actor, "get_username") else ""


def person_of(ctx: OperationContext, person_id: str) -> dict[str, Any]:
    """The person ``person_id`` of this business; ``NotFound`` for anyone else (another business's, nobody)."""
    for person in people_of(ctx.scope.key):
        if person["id"] == person_id:
            return person
    raise NotFound(gettext("That person is not in this business."), code="base.person_not_found")


def signed_in_role(ctx: OperationContext) -> str:
    username = signed_in_username(ctx)
    role = Membership.objects.filter(host=ctx.scope.key, user__username=username).values_list("role", flat=True).first()
    return role or ""


def person_detail_out(ctx: OperationContext, person: dict[str, Any]) -> dict[str, Any]:
    """A person's page: what the hub keeps of their way in and what who asks may change of it."""
    actor, actor_role = signed_in_username(ctx), signed_in_role(ctx)
    credential = person["credential"]

    def may(badge: bool) -> bool:
        return people_rules.refusal(
            actor=actor, actor_role=actor_role, target=person["id"], target_role=person["role"], badge=badge
        ) is None

    return {
        **person_out(ctx, person),
        "pin_set_at": credential.pin_set_at if credential and credential.pin_hash else None,
        "badge_set_at": credential.badge_set_at if credential and credential.badge_digest else None,
        "may": {"remove_pin": may(False), "set_badge": may(True)},
    }


@operation(
    "base.person.list",
    kind="query",
    permission=VIEW_HOME,
    input=PersonListIn,
    output=PersonListOut,
    ai=AI(
        description=(
            "Lists the people of this business: name, role (owner, admin, manager, employee), how each one gets in "
            "(their erplora.com account, and a PIN or a badge at the shared tills) and whether they entered yet; and "
            "the places of the plan taken. Inviting, changing a role or removing someone is done on erplora.com."
        ),
        asks={
            "en": ("who has access to the business?", "list everyone and their role", "who still hasn't signed in?"),
            "es": ("¿quién tiene acceso al negocio?", "¿quién puede entrar en el negocio y con qué rol?"),
        },
    ),
)
def person_list(ctx: OperationContext, data: PersonListIn) -> dict:
    """Employees › Personal: every person once, owner first, with the plan's places."""
    found = people_of(ctx.scope.key)
    taking_a_place = sum(1 for person in found if person["role"] not in people_rules.FREE_ROLES)
    return {"people": [person_out(ctx, person) for person in found], "seats": seats_of(ctx.scope.key, taking_a_place)}


@operation(
    "base.person.detail",
    kind="query",
    permission=ADMINISTER_HUB,
    input=PersonIn,
    output=PersonDetailOut,
    ai=AI(
        description=(
            "Reads one person of this business by their id: role, how they get in (PIN, badge), since when, and "
            "whether who asks may take their PIN away or give them a badge."
        ),
        asks={
            "en": ("how does Luis get in, PIN or badge?", "can Ana still use her PIN?"),
            "es": ("¿cómo entra Luis, con PIN o con placa?", "¿Ana tiene placa?"),
        },
    ),
)
def person_detail(ctx: OperationContext, data: PersonIn) -> dict:
    """A person's page, for who runs the business."""
    return person_detail_out(ctx, person_of(ctx, data.person))


@operation(
    "base.role.list",
    kind="query",
    permission=VIEW_HOME,
    input=RoleListIn,
    output=RoleListOut,
    ai=AI(
        description=(
            "Lists the roles of this business (owner, admin, manager, employee): how many people have each one and how "
            "many permissions of the apps it gives. Roles are given on erplora.com."
        ),
        asks={
            "en": ("how many managers do we have?", "what can a manager do here?"),
            "es": ("¿qué roles hay en el negocio?", "¿cuántos encargados tenemos?"),
        },
    ),
)
def role_list(ctx: OperationContext, data: RoleListIn) -> dict:
    """Employees › Roles: erplora.com's, from the top, with their people and permissions."""
    found = people_of(ctx.scope.key)
    with translation.override(ctx.language):
        return {
            "roles": [
                {
                    "key": role.value,
                    "label": str(role.label),
                    "origin": "basic",
                    "members": sum(1 for person in found if person["role"] == role),
                    "permissions": len(permissions_of_role(role.value)),
                }
                for role in people_rules.ROLE_ORDER
            ]
        }


def person_label(user) -> str:
    """How ``user`` is named in this hub: its «My profile» name, else its erplora.com account's, else its username."""
    profile = Profile.objects.filter(username=user.get_username()).only("first_name", "last_name").first()
    if profile is not None and (name := f"{profile.first_name} {profile.last_name}".strip()):
        return name
    return user.get_full_name() or user.get_username()


def face_name(user) -> str:
    """How ``user`` shows on the grid of a till, seen by anyone at it: their name, never an email."""
    return without_address(person_label(user))


def actor_name(who) -> str:
    """Whoever acts as a colleague reads them, kept on what they do (a kitchen ticket, a table's check): their account's
    name, else what goes before the «@» of their e-mail, never the address; their username only as the last resort;
    anything else (the platform, an API key) as it is."""
    if who is None:
        return ""
    if hasattr(who, "get_username"):
        return without_address(who.get_full_name() or getattr(who, "email", "")) or who.get_username()
    return str(who)


def without_address(name: str) -> str:
    """``name`` without an email address in it: erplora.com names an account without a name by its address, and a
    colleague's address only reaches whoever sees the team's contact details. Then the part before the «@»."""
    return name.split("@", 1)[0]
