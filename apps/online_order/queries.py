"""Read operations of Online orders (``READ ONLY``): the tables with the code each one's QR carries, and the row of a
table and its code that a regeneration answers with too; and the table's page, which its QR opens without a session.

The tables are Tables' own, read by its operations' names (``base.operations.call``) with the permission of whoever
asks: whoever may not see the tables does not see their codes either.

The page's reads (``online_order.public``, the one permission base's public door holds) name the table by its code and
read the other apps with ``menu_reader(ctx)``: the same context able to read the table and the menu, and nothing that
changes anything. A code that is no table's (regenerated, of a deleted table) is refused alike, saying nothing of the
business.
"""

from dataclasses import replace
from typing import Any

from django.db.models import QuerySet
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import NotFound
from live.operations import INTERNAL, operation

from apps.online_order.models import TableCode
from apps.online_order.schemas import (
    PublicCodeIn,
    PublicMenuOut,
    PublicOptionsIn,
    PublicOptionsOut,
    TableCodeListIn,
    TableCodePage,
)
from base.apps_on import active_apps
from base.catalog_groups import every_row, product_groups
from base.operations import business_name, call
from base.qr import public_url

PUBLIC = "online_order.public"
#: What the page's reads add to the visitor's: its table and the menu, each a read.
MENU_READS = frozenset(
    {"table.view_table", "inventory.view_product", "inventory.view_category", "modifier.view", "combo.view"}
)
QR_NOT_ACTIVE = _("This QR is no longer active; ask the staff for help.")
QR_NOT_ACTIVE_CODE = "online_order.qr_not_active"
NOT_ON_MENU = _("This dish is not on the menu.")
#: The most menus a page of ``combo.combo.for_sale`` gives.
COMBO_PAGE = 50


def page_url(ctx: OperationContext, code: str) -> str:
    """The address of the table's page that ``code`` opens: ``/p/<slug>/order/<code>`` on the hub's public address."""
    slug = ctx.scope.key
    return f"{public_url(slug, ctx.request)}p/{slug}/order/{code}"


def code_row(ctx: OperationContext, table, code: TableCode | None) -> dict:
    """A table as Tables answers it, with its code (or none yet)."""
    return {
        "table_id": table.id,
        "table": table.label,
        "number": table.number,
        "zone_name": table.zone_name,
        "code": code.code if code else None,
        "url": page_url(ctx, code.code) if code else None,
        "issued_at": code.issued_at if code else None,
    }


@operation(
    "online_order.qr_code.list",
    kind="query",
    permission="online_order.view_qr_code",
    input=TableCodeListIn,
    output=TableCodePage,
    expose_api=True,
    ai={
        "description": "Lists the tables in the floor plan's order (2 before 10), each with its zone and, once its "
        "QR has been generated, the code its QR carries, the address of the table's ordering page and when the code "
        "was generated; a table without a code has none yet. A page at a time.",
        "asks": {
            "en": (
                "which tables already have their ordering QR code?",
                "give me the address of the QR code of each table",
            ),
            "es": (
                "¿qué mesas tienen ya su código QR para pedir?",
                "dame la dirección del código QR de cada mesa",
            ),
        },
    },
)
def list_qr_codes(ctx: OperationContext, params: TableCodeListIn) -> dict:
    tables = call(ctx, "table.table.list", {"limit": params.limit, "offset": params.offset})
    codes = TableCode.objects.in_bulk([table.id for table in tables.rows], field_name="table_id")
    return {
        "rows": [code_row(ctx, table, codes.get(table.id)) for table in tables.rows],
        "total": tables.total,
        "limit": params.limit,
        "offset": params.offset,
    }


def menu_reader(ctx: OperationContext) -> OperationContext:
    """``ctx`` able to read the table and the menu in the other apps (and only that)."""
    return replace(ctx, permissions=ctx.permissions | MENU_READS)


def table_of(reader: OperationContext, code: str, *, codes: QuerySet[TableCode] | None = None):
    """The table whose QR carries ``code``, as Tables answers it; a code that opens no table's page is not found.
    ``codes`` is where the code is looked for: a write passes its rows locked."""
    found = (TableCode.objects.all() if codes is None else codes).filter(code=code).first()
    if found is None:
        raise NotFound(str(QR_NOT_ACTIVE), code=QR_NOT_ACTIVE_CODE)
    try:
        return call(reader, "table.table.get", {"id": found.table_id})
    except NotFound as gone:
        # A deleted table's code opens nothing, as an unknown code.
        raise NotFound(str(QR_NOT_ACTIVE), code=QR_NOT_ACTIVE_CODE) from gone


def _dish(row: Any) -> dict:
    """A row of ``inventory.product.list_for_sale``, as the customer sees it."""
    fields = ("id", "name", "description", "price", "image_url", "allergens")
    return {field: getattr(row, field) for field in fields}


def _combos(reader: OperationContext) -> list[dict]:
    """The menus on sale with their courses, each dish with its allergens; none while Menus and combos is off."""
    if "combo" not in active_apps(reader.scope):
        return []
    return [
        {
            "id": combo.id,
            "name": combo.name,
            "price": combo.price,
            "image_url": combo.image_url,
            "courses": [
                {
                    "name": course.name,
                    "min_choices": course.min_choices,
                    "max_choices": course.max_choices,
                    "choices": [
                        {
                            "name": choice.product_name,
                            "price_delta": choice.price_delta,
                            "allergens": choice.allergens,
                        }
                        for choice in course.options
                    ],
                }
                for course in combo.groups
            ],
        }
        for combo in every_row(reader, "combo.combo.for_sale", page_size=COMBO_PAGE)
    ]


@operation(
    "online_order.public.menu",
    kind="query",
    permission=PUBLIC,
    input=PublicCodeIn,
    output=PublicMenuOut,
    ai=INTERNAL,
)
def public_menu(ctx: OperationContext, data: PublicCodeIn) -> dict:
    reader = menu_reader(ctx)
    table = table_of(reader, data.code)
    shown = every_row(reader, "inventory.product.list_for_sale", show_on_website=True)
    return {
        "business_name": business_name(ctx.scope),
        "table_number": table.number,
        "zone_name": table.zone_name,
        "groups": [{"name": name, "items": items} for _id, name, items in product_groups(reader, shown, _dish)],
        "combos": _combos(reader),
    }


@operation(
    "online_order.public.options",
    kind="query",
    permission=PUBLIC,
    input=PublicOptionsIn,
    output=PublicOptionsOut,
    ai=INTERNAL,
)
def public_options(ctx: OperationContext, data: PublicOptionsIn) -> dict:
    reader = menu_reader(ctx)
    table_of(reader, data.code)
    shown = every_row(reader, "inventory.product.list_for_sale", show_on_website=True)
    if not any(row.id == data.product_id for row in shown):
        raise NotFound(str(NOT_ON_MENU), code="online_order.not_on_menu")
    groups = []
    if "modifier" in active_apps(reader.scope):
        groups = call(reader, "modifier.group.for_target", {"product_id": data.product_id}).groups
    return {
        "product_id": data.product_id,
        "groups": [
            {
                "name": group.name,
                "min_choices": group.min_choices,
                "max_choices": group.max_choices,
                "options": [
                    {"name": option.name, "price_delta": option.price_delta, "allergens": option.allergens}
                    for option in group.options
                ],
            }
            for group in groups
        ],
    }
