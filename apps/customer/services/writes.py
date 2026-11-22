"""What every write of the customer app shares: who acts, a phone as kept, what a write changes, when a consent
fact happened, the locks on cards, groups, tags and fields, and a name already taken among the active ones."""

from datetime import datetime, timedelta
from uuid import UUID

from django.db import IntegrityError
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict, InvalidPayload
from live.operations import atomic

from apps.customer.models import Customer
from apps.customer.phones import InvalidPhone, to_e164
from apps.customer.queries import business_country

PHONE_INVALID = _(
    "This is not a valid phone number of its country: check the digits or write it with its "
    "international prefix (+44…)."
)
DATE_IN_FUTURE = _("This date is in the future.")
#: A consent may be dated a little ahead of the server's clock (a tablet's clock), not more.
CLOCK_SKEW = timedelta(minutes=5)


def _actor(ctx: OperationContext) -> str:
    """Who writes, as people read it: the user's name (or email), never their account id; the
    platform itself (``system_context``) by its own mark."""
    actor = ctx.actor
    if actor is None:
        return ""
    if not hasattr(actor, "get_username"):
        return str(actor)[:128]
    return (actor.get_full_name() or actor.email or actor.get_username())[:128]


def _e164(raw: str, ctx: OperationContext, field: str = "phone") -> str:
    try:
        return to_e164(raw, business_country(ctx))
    except InvalidPhone:
        raise InvalidPayload(
            PHONE_INVALID, code="customer.phone_invalid", fields={field: PHONE_INVALID}
        ) from None


def _changes(instance, sent: dict) -> dict:
    """The sent values that differ from ``instance``'s."""
    return {
        field: value
        for field, value in sent.items()
        if getattr(instance, field) != value
    }


def _occurred_at(sent: datetime | None, now: datetime) -> datetime:
    """When a consent fact happened: the moment sent or, without one, ``now``; one further ahead of ``now`` than
    ``CLOCK_SKEW`` is refused."""
    occurred_at = sent or now
    if occurred_at > now + CLOCK_SKEW:
        raise InvalidPayload(
            DATE_IN_FUTURE,
            code="customer.date_in_future",
            fields={"occurred_at": DATE_IN_FUTURE},
        )
    return occurred_at


def _save_named(instance, message, code: str) -> None:
    """Saves a group, tag or field; a name already taken among the active ones is a 409 under «name»."""
    try:
        with atomic():
            instance.save()
    except IntegrityError as exc:
        if "_name_unique" not in str(exc):
            raise
        raise Conflict(message, code=code, fields={"name": message}) from None


def lock_rows(model, ids) -> list[UUID]:
    """Locks the cards, groups, tags or custom fields ``ids`` (deleted cards too) in id order; the ids of those
    still there.

    Every write on a card locks it before what hangs from it (its activity, purchases, consents, values,
    groups, tags, health data and orders), and then the groups, tags or fields it points at; the Hub admin's
    «Delete» (admin.py) locks them too before Django gathers what hangs from them and deletes it, as the
    business's own «Delete» of a group, a tag or a field does. Whichever comes second waits for the other:
    the deletion takes what the write added, or the write finds the row gone, instead of failing at its
    COMMIT. Several rows are taken in id order, as a merge takes its two cards.
    """
    rows = model.objects.select_for_update().filter(pk__in=ids).order_by("id")
    return list(rows.values_list("id", flat=True))


def lock_customers(ids) -> list[UUID]:
    """Locks the cards ``ids`` as an erasure and a merge take them: a card before the duplicates merged into it
    (each wave in id order); the ids of those still there.

    The Hub admin's «Delete selected» of a card and its duplicate, in plain id order, could hold the duplicate
    while an erasure of the card held the card and went for the duplicate: each waited for the other.
    """
    pending, locked = set(ids), []
    while pending:
        # The cards not merged into another pending one (all of them if they point at each other).
        wave = set(
            Customer.objects.filter(pk__in=pending)
            .exclude(merged_into_id__in=pending)
            .values_list("id", flat=True)
        ) or set(pending)
        locked += lock_rows(Customer, wave)
        pending -= wave
    return locked


def _patched(instance, data, exclude: set[str]) -> dict:
    sent = {
        field: value
        for field, value in data.model_dump(exclude_unset=True, exclude=exclude).items()
        if value is not None
    }
    changes = _changes(instance, sent)
    for field, value in changes.items():
        setattr(instance, field, value)
    return changes


def _with_count(instance):
    """A group or tag with how many live cards have it, as its list row shows it."""
    instance.customer_count = instance.customers.filter(deleted_at__isnull=True).count()
    return instance
