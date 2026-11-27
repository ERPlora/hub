"""The aliases of the tax categories (TAX-F13): the outside texts the inventory importer reads as a category, listed
and resolved."""


from django.utils import translation
from live.context import OperationContext
from live.operations import operation

from apps.tax.models import TaxAlias
from apps.tax.queries.naming import resolve_category_text
from apps.tax.schemas.aliases import AliasListIn, AliasPage, AliasResolveIn, AliasResolveOut
from base.ordering import list_order
from base.text_search import contains_text


def alias_row(alias: TaxAlias) -> dict:
    return {
        "id": alias.id,
        "alias": alias.alias,
        "tax_category_key": alias.category.key,
        "tax_category_name": alias.category.display_name,
        "source": alias.source,
        "is_active": alias.is_active,
    }


_ALIAS_COLUMNS = {"tax_category_key": "category__key"}


@operation(
    "tax.alias.list",
    kind="query",
    permission="tax.view",
    input=AliasListIn,
    output=AliasPage,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "list the tax aliases",
                "which aliases of tax categories does the importer know?",
                "what words of a spreadsheet does the importer read as a VAT category?",
            ),
            "es": (
                "lista los alias de las categorías fiscales",
                "¿qué alias de impuestos reconoce el importador de inventario?",
                "enséñame los alias que el importador traduce a una categoría de IVA",
            ),
        },
        "description": "List the active category aliases (an outside text such as «beer» or «IVA 10» → the key "
        "of a tax category) that the CSV importer of inventory recognises."
    },
)
def list_aliases(ctx: OperationContext, params: AliasListIn) -> dict:
    """Sorted by the column asked, ``alias`` and ``id`` as the tie-break."""
    with translation.override(ctx.language):
        aliases = TaxAlias.objects.select_related("category").filter(is_active=True)
        if params.search:
            search = params.search.strip()
            aliases = aliases.filter(contains_text(search, "alias", "category__key"))
        if params.alias:
            aliases = aliases.filter(contains_text(params.alias.strip(), "alias"))
        if params.tax_category_key:
            aliases = aliases.filter(category__key=params.tax_category_key)
        if params.source:
            aliases = aliases.filter(source=params.source)
        column = _ALIAS_COLUMNS.get(params.sort, params.sort)
        page = aliases.order_by(*list_order(column, "alias", descending=params.dir == "desc", nulls_last=True))[
            params.offset : params.offset + params.limit
        ]
        return {
            "rows": [alias_row(alias) for alias in page],
            "total": aliases.count(),
            "limit": params.limit,
            "offset": params.offset,
        }


@operation(
    "tax.alias.resolve",
    kind="query",
    permission="tax.view",
    input=AliasResolveIn,
    output=AliasResolveOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "which tax category does the text «IVA 10» mean?",
                "read «beer» as a tax category",
                "what VAT category would the importer give to «menú del día»?",
            ),
            "es": (
                "¿qué categoría de impuestos significa el texto «cerveza»?",
                "el importador ha leído «IVA 10»: ¿qué categoría fiscal es?",
                "traduce «licor» a una categoría de IVA",
            ),
        },
        "description": "Read an outside text (a CSV cell such as «IVA 10», «beer» or «comida») as a tax "
        "category: by its key, its name in any language, or a learned alias. Nothing when nothing matches."
    },
)
def resolve_alias(ctx: OperationContext, params: AliasResolveIn) -> dict:
    key, matched_by = resolve_category_text(params.text)
    return {"text": params.text, "tax_category_key": key, "matched_by": matched_by}
