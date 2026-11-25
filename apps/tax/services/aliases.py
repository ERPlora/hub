"""The writes of the other names of a tax category (TAX-F14)."""

from django.db import IntegrityError
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict
from live.operations import atomic, operation
from live.outbox import record_event

from apps.tax import events
from apps.tax.models import TaxAlias
from apps.tax.queries.aliases import alias_row
from apps.tax.schemas.aliases import AliasIn, AliasOut
from apps.tax.services.categories import _category

ALIAS_EXISTS = _("That alias already exists.")


@operation(
    "tax.alias.create",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="tax.manage",
    input=AliasIn,
    output=AliasOut,
    ai={
        "asks": {
            "en": (
                "teach the importer that «IVA 10» means the reduced food category",
                "learn that «cerveza» is the beer tax category",
                "add the tax alias «licores» for spirits",
            ),
            "es": (
                "que el importador entienda «cerveza» como la categoría del alcohol",
                "añade el alias «IVA reducido» para la categoría de comida",
                "guarda «menú» como otro nombre de la categoría fiscal de restauración",
            ),
        },
        "description": "Teach an outside text (a CSV cell such as «cerveza» or «IVA 10») to mean a tax category, "
        "so the next import of inventory recognises it. Kept lowercase with single spaces.",
        "risk": "normal",
    },
)
def create_alias(ctx: OperationContext, data: AliasIn) -> dict:
    category = _category(data.tax_category_key)
    try:
        with atomic():
            alias = TaxAlias.objects.create(
                alias=data.alias, category=category, source=data.source
            )
    except IntegrityError:  # the alias is the only unique field
        raise Conflict(
            ALIAS_EXISTS, code="tax.alias_exists", fields={"alias": str(ALIAS_EXISTS)}
        ) from None
    record_event(
        ctx,
        events.ALIAS_CREATED,
        {"id": str(alias.id), "alias": alias.alias, "tax_category_key": category.key},
    )
    return alias_row(alias)
