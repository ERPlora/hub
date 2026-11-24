"""Putting a menu on sale or taking it off the till (COMBO-F03): the gesture of every day that another one undoes, as
the menu form's «On sale» switch. It is the menu's change with that switch alone, so its rules and its event are the
same; only its card differs, one tap instead of the word the menu's change asks for because it may change how the
menu is billed."""

from live.context import OperationContext
from live.operations import get, operation

from apps.combo.schemas.menus import ComboDetailOut
from apps.combo.schemas.on_sale import ComboOnSaleIn


@operation(
    "combo.combo.set_active",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="combo.manage",
    input=ComboOnSaleIn,
    output=ComboDetailOut,
    expose_api=True,
    ai={
        "description": "Put a menu on sale or take it off the till for now, named by its id or its name: it stays on "
        "the list of menus and nothing else of it changes. Together with other changes of the menu, "
        "combo.combo.update.",
        "risk": "normal",
        "check": "combo.combo.get",
        "asks": {
            "en": (
                "take the summer menu off sale for now",
                "put the menu of the day back on sale",
                "stop selling the kids' menu tonight",
            ),
            "es": (
                "quita de la venta el menú de verano por ahora",
                "vuelve a poner a la venta el menú del día",
                "esta noche no vendas el menú infantil",
            ),
        },
    },
)
def set_active(ctx: OperationContext, data: ComboOnSaleIn) -> ComboDetailOut:
    change = get("combo.combo.update")
    return change(ctx, change.input.model_validate(data.model_dump(exclude_unset=True)))
