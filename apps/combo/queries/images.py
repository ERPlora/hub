"""The images of the shared library proposed for a menu's photo (COMBO-F14)."""

from live.context import OperationContext
from live.operations import operation

from apps.combo.schemas.images import ComboImageSuggestIn, ComboImageSuggestOut
from base.queries.catalog_images import image_suggestion, titled_search

from .reads import find_combo


@operation(
    "combo.combo.suggest_image",
    kind="query",
    permission="combo.view",
    input=ComboImageSuggestIn,
    output=ComboImageSuggestOut,
    expose_api=True,
    ai={
        "description": "Propose images of ERPlora's shared image library for a menu's photo («ponle foto al menú del "
        "día»), the menu named by its id or its name: " + image_suggestion("combo.combo.set_image"),
        "asks": {
            "en": (
                "suggest a picture for the kids' menu",
                "which library images would suit the summer menu?",
            ),
            "es": (
                "sugiéreme una foto para el menú infantil",
                "¿qué imágenes de la biblioteca le pegan al menú de verano?",
            ),
        },
    },
)
def suggest_image(ctx: OperationContext, data: ComboImageSuggestIn) -> dict:
    """COMBO-F14: the library searched by the menu's name in either of its languages, titled in the person's."""
    combo = find_combo(data.id, data.combo)
    return {
        "combo_id": combo.id,
        "query": combo.name,
        "rows": titled_search(ctx, combo.name)[: data.limit],
    }
