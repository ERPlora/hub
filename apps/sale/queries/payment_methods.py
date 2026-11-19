"""The payment methods a customer can pay with, and which of them the settings let charge."""

from collections.abc import Iterable
from uuid import UUID

from django.conf import settings as django_settings
from django.utils import translation
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict
from live.operations import AI, operation

from apps.sale.models import FACTORY_METHOD_NAMES, PaymentMethod, Settings
from apps.sale.queries.rows import held
from apps.sale.queries.settings import current_settings
from apps.sale.schemas.settings import PaymentMethodListIn, PaymentMethodPage

METHOD_NOT_AVAILABLE = _("That payment method is not available in this business.")
METHOD_AMBIGUOUS = _(
    "Several payment methods match «%(said)s»: %(names)s. Say which one."
)

#: The settings each method type depends on; «other» is always allowed.
TYPE_SETTING = {
    "cash": "allow_cash",
    "card": "allow_card",
    "transfer": "allow_transfer",
}


def method_display_name(name: str) -> str:
    """A factory method's name in the active language (stored canonical English)."""
    label = FACTORY_METHOD_NAMES.get(name)
    return str(label) if label else name


def allowed_types(settings: Settings, methods: Iterable[PaymentMethod]) -> set[str]:
    """The method types the settings let charge; if they leave no active method, every type."""
    allowed = {"other"} | {
        kind for kind, field in TYPE_SETTING.items() if getattr(settings, field)
    }
    if not any(method.type in allowed for method in methods):
        return {"cash", "card", "transfer", "other"}
    return allowed


def payment_method_row(method: PaymentMethod, allowed: set[str]) -> dict:
    return {
        "id": method.id,
        "name": method.name,
        "display_name": method.display_name,
        "type": method.type,
        "sort_order": method.sort_order,
        "requires_change": method.requires_change,
        "allowed": method.type in allowed,
    }


def _said(text: str) -> str:
    return " ".join(text.split()).casefold()


def _names_in_every_language(label) -> set[str]:
    names = set()
    for language, _name in django_settings.LANGUAGES:
        with translation.override(language):
            names.add(_said(str(label)))
    return names


def find_method(method_id: UUID | None, said: str | None) -> PaymentMethod:
    """An active payment method by its id, its name (a factory one in any language) or its type."""
    active = PaymentMethod.objects.filter(is_active=True)
    if method_id is not None:
        method = active.filter(pk=method_id).first()
        if method is None:
            raise Conflict(
                str(METHOD_NOT_AVAILABLE), code="sale.payment_method_not_available"
            )
        return method
    wanted = _said(said or "")
    methods = list(active.order_by("sort_order", "name", "id"))
    by_name = [
        m
        for m in methods
        if _said(m.name) == wanted
        or (
            m.is_system
            and wanted
            in _names_in_every_language(FACTORY_METHOD_NAMES.get(m.name, m.name))
        )
    ]
    if not by_name:
        types = {
            kind
            for kind, label in PaymentMethod.Type.choices
            if wanted == kind or wanted in _names_in_every_language(label)
        }
        by_name = [m for m in methods if m.type in types]
    if not by_name:
        raise Conflict(
            str(METHOD_NOT_AVAILABLE), code="sale.payment_method_not_available"
        )
    if len(by_name) > 1:
        names = ", ".join(m.display_name for m in by_name[:5])
        raise Conflict(
            str(METHOD_AMBIGUOUS) % {"said": said, "names": names},
            code="sale.payment_method_ambiguous",
        )
    return by_name[0]


def held_methods(ids: Iterable[UUID]) -> set[UUID]:
    """The payment methods ``ids`` still there, each held (``held``) in id order until the write that records a
    tender of them ends; a write that names several takes them in the order the admin's «Delete selected» does."""
    ids = set(ids)
    if not ids:
        return set()
    return {method.pk for method in held(PaymentMethod.objects.filter(pk__in=ids).order_by("id"))}


@operation(
    "sale.payment_method.list",
    kind="query",
    permission="sale.view_paymentmethod",
    input=PaymentMethodListIn,
    output=PaymentMethodPage,
    expose_api=True,
    ai=AI(
        description="List the active payment methods customers can pay with, in the order of the charge sheet, with "
        "their type (cash, card, transfer, other) and whether the till settings let them charge today.",
        asks={
            "en": (
                "which payment methods do we take?",
                "do we accept Bizum?",
                "what can they pay with here?",
                "which ways of settling up do we offer?",
            ),
            "es": (
                "¿qué formas de pago aceptamos?",
                "¿se puede pagar con Bizum?",
                "¿con qué me pueden pagar?",
                "¿de cuántas maneras distintas se puede pagar aquí?",
                "¿con qué medios de pago abonan los clientes aquí?",
            ),
        },
    ),
)
def list_payment_methods(ctx: OperationContext, params: PaymentMethodListIn) -> dict:
    with translation.override(ctx.language):
        methods = PaymentMethod.objects.filter(is_active=True).order_by(
            "sort_order", "name", "id"
        )
        allowed = allowed_types(current_settings(), methods)
        if params.search:
            methods = methods.filter(name__icontains=params.search.strip())
        page = methods[params.offset : params.offset + params.limit]
        return {
            "rows": [payment_method_row(method, allowed) for method in page],
            "total": methods.count(),
            "limit": params.limit,
            "offset": params.offset,
        }
