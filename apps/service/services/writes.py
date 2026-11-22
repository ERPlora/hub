"""What every write of the service app shares: who acts, a refusal under its field, the changes an edit makes, the
active tax category it names and a save that turns a name another write took meanwhile into the check's 409.
"""

from django.db import IntegrityError
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict, InvalidPayload
from live.operations import atomic

from apps.service.models import ACTOR_MAX_LENGTH
from apps.tax.models import TaxCategory
from apps.tax.queries import held_categories

TAX_UNKNOWN = _("That tax category does not exist in Taxes or is deactivated.")


def _actor(ctx: OperationContext) -> str:
    """Who acted, as a person reads it («Voided by …»): an account's full name, else its email, else
    its username; the platform or an API key as they name themselves."""
    actor = ctx.actor
    if actor is None:
        return ""
    if hasattr(actor, "get_username"):
        name = actor.get_full_name() or actor.email or actor.get_username()
    else:
        name = str(actor)
    return name[:ACTOR_MAX_LENGTH]


def _tidy(name: str) -> str:
    """A name as it is kept: single spaces (two names that differ only in spaces are the same name)."""
    return " ".join(name.split())


def _refuse(message, code: str, field: str):
    return InvalidPayload(str(message), code=code, fields={field: str(message)})


def _tax_category(key: str, field: str, *, hold: bool = False) -> TaxCategory:
    """The active tax category ``key``; with ``hold``, held until the command commits (Taxes' read)."""
    if hold:
        tax = held_categories([key]).get(key)
    else:
        tax = TaxCategory.objects.filter(key=key, is_active=True).first()
    if tax is None:
        raise _refuse(TAX_UNKNOWN, "service.tax_category_unknown", field)
    return tax


def _changes(instance, values: dict) -> dict:
    return {
        field: value
        for field, value in values.items()
        if getattr(instance, field) != value
    }


def _apply(instance, changes: dict, ctx: OperationContext) -> None:
    for field, value in changes.items():
        setattr(instance, field, value)
    instance.updated_by = _actor(ctx)


def _save_unique(instance, constraint: str, message, code: str) -> None:
    """Save in a savepoint: a name another write took meanwhile says so with the check's 409."""
    try:
        with atomic():
            instance.save()
    except IntegrityError as exc:
        if constraint in str(exc):
            raise Conflict(
                str(message), code=code, fields={"name": str(message)}
            ) from exc
        raise
