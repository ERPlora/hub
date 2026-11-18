"""People and permissions: a person's way in, their PIN and their badge (``base.person.*``).
"""

from django.db import IntegrityError
from django.utils import timezone
from django.utils.translation import gettext
from live.context import OperationContext
from live.errors import Conflict, InvalidPayload, OperationError, PermissionDenied
from live.operations import AI, atomic, operation
from live.outbox import record_event

from base import access, events, queries
from base import people as people_rules
from base.models import Credential
from base.permissions import ADMINISTER_HUB
from base.schemas import BadgeSetIn, PersonDetailOut, PersonIn
from base.services.devices import badge_key, too_many_message

_PERSON_REFUSALS = {people_rules.OWNER_ONLY: people_rules.OWNER_ONLY_MESSAGE, people_rules.OWN_BADGE: people_rules.OWN_BADGE_MESSAGE}


def _changeable_person(ctx: OperationContext, person_id: str, *, badge: bool) -> dict:
    """The person ``person_id`` of this business, if who asks may change their way in (``base.people.refusal``)."""
    person = queries.people.person_of(ctx, person_id)
    why = people_rules.refusal(
        actor=queries.people.signed_in_username(ctx),
        actor_role=queries.people.signed_in_role(ctx),
        target=person["id"],
        target_role=person["role"],
        badge=badge,
    )
    if why is not None:
        raise PermissionDenied(str(_PERSON_REFUSALS[why]), code=why)
    return person


def _person_answer(ctx: OperationContext, person_id: str) -> dict:
    return queries.people.person_detail_out(ctx, queries.people.person_of(ctx, person_id))


@operation(
    "base.person.pin_remove",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission=ADMINISTER_HUB,
    input=PersonIn,
    output=PersonDetailOut,
    ai=AI(
        description=(
            "Takes a person's PIN away (a forgotten or shared one): they stop entering with it at the shared tills and "
            "keep entering with their erplora.com account. The owner's, only the owner."
        ),
        risk="high",
        preview={"operation": "base.person.detail", "fields": ["name", "email"]},
        asks={
            "en": ("Ana forgot her PIN, remove it", "take away Luis's PIN, he shared it"),
            "es": ("quítale el PIN a Luis, lo ha compartido", "Ana ha olvidado su PIN, bórraselo"),
        },
    ),
)
def person_pin_remove(ctx: OperationContext, data: PersonIn) -> dict:
    """«Remove the PIN»: the PIN goes at once, the badge and the account stay."""
    _changeable_person(ctx, data.person, badge=False)
    credential = Credential.objects.select_for_update().filter(username=data.person).exclude(pin_hash="").first()
    if credential is None:
        raise Conflict(gettext("This person has no PIN to remove."), code="base.person_no_pin")
    credential.pin_hash, credential.pin_set_at = "", None
    credential.save(update_fields=["pin_hash", "pin_set_at"])
    record_event(ctx, events.PERSON_PIN_REMOVED, {"person": data.person})
    return _person_answer(ctx, data.person)


@operation(
    "base.person.badge_set",
    kind="command",
    permission=ADMINISTER_HUB,
    input=BadgeSetIn,
    output=PersonDetailOut,
    ai={
        "description": "Not an assistant tool (a badge is a card passed through the reader): gives a person the badge "
        "they will enter with at the shared tills.",
        "risk": "high",
    },
)
def person_badge_set(ctx: OperationContext, data: BadgeSetIn) -> dict:
    """«Badge»: the card, kept as its digest; never one's own, never one somebody else carries. Every try
    counts against who gives it (``people.BADGE_CHANGE_LIMIT``): «already taken» tells something."""
    _changeable_person(ctx, data.person, badge=True)
    editor = queries.people.signed_in_username(ctx)
    wait = people_rules.BADGE_CHANGE_LIMIT.wait(ctx.scope.key, editor)
    if wait:
        raise OperationError(
            too_many_message(wait, gettext("Too many badges tried.")), code="base.too_many_badge_changes", status=429
        )
    people_rules.BADGE_CHANGE_LIMIT.failed(ctx.scope.key, editor)
    card = access.clean_badge(data.badge)
    if card is None:
        raise InvalidPayload(
            gettext("A badge has 4 to 64 characters: letters, digits, «-» and «_»."),
            code="base.badge_invalid",
            fields={"badge": "invalid"},
        )
    digest = access.badge_digest(card, key=badge_key())
    if Credential.objects.filter(badge_digest=digest).exclude(username=data.person).exists():
        raise Conflict(
            gettext("Somebody else already carries that badge. A badge says who is at the till: two people cannot share it."),
            code="base.badge_taken",
        )
    credential, _ = Credential.objects.select_for_update().get_or_create(username=data.person)
    credential.badge_digest, credential.badge_set_at = digest, timezone.now()
    try:
        with atomic():
            credential.save(update_fields=["badge_digest", "badge_set_at"])
    except IntegrityError:
        # Given to somebody else at this same moment: the unique digest keeps one.
        raise Conflict(
            gettext("Somebody else already carries that badge. A badge says who is at the till: two people cannot share it."),
            code="base.badge_taken",
        ) from None
    record_event(ctx, events.PERSON_BADGE_SET, {"person": data.person})
    return _person_answer(ctx, data.person)


@operation(
    "base.person.badge_remove",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission=ADMINISTER_HUB,
    input=PersonIn,
    output=PersonDetailOut,
    ai=AI(
        description=(
            "Takes a person's badge away (a lost card): it stops opening the till; their PIN and account stay. For a "
            "person named in the chat, find their person id with person.list and then use this; do not ask for an id."
        ),
        asks={
            "en": (
                "Luis lost his card, take his badge away",
                "remove Marta's badge",
                "cancel Pedro's card, he lost it",
            ),
            "es": (
                "Luis ha perdido la tarjeta, quítale la placa",
                "quita la placa de Marta",
                "anula la tarjeta de Pedro, que se le ha perdido",
            ),
        },
    ),
)
def person_badge_remove(ctx: OperationContext, data: PersonIn) -> dict:
    """«Remove the badge»: the card stops opening anything; a lost one never leaves anybody out."""
    _changeable_person(ctx, data.person, badge=False)
    credential = Credential.objects.select_for_update().filter(username=data.person).exclude(badge_digest="").first()
    if credential is None:
        raise Conflict(gettext("This person has no badge to remove."), code="base.person_no_badge")
    credential.badge_digest, credential.badge_set_at = "", None
    credential.save(update_fields=["badge_digest", "badge_set_at"])
    record_event(ctx, events.PERSON_BADGE_REMOVED, {"person": data.person})
    return _person_answer(ctx, data.person)
