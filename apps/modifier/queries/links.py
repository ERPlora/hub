"""What the groups apply to (MODIFIER-F05): the links of a group, a product or a category, and one link. A link to
a product or a category Inventory deleted is left out.
"""

from django.db.models import Q
from django.db.models.functions import Coalesce, Lower
from live.context import OperationContext
from live.errors import NotFound
from live.operations import operation

from apps.inventory.queries.reads import find_category, find_product
from apps.modifier.models import ModifierLink
from apps.modifier.schemas.fields import Page
from apps.modifier.schemas.links import LinkDetailOut, LinkListIn, LinkOut, LinkRefIn

from .reads import LINK_NOT_FOUND, _page, find_group, link_row

#: A link whose product or category is still alive in Inventory.
LIVE_LINK = Q(product__isnull=False, product__is_deleted=False) | Q(
    category__isnull=False, category__is_deleted=False
)


@operation(
    "modifier.link.list",
    kind="query",
    permission="modifier.view",
    input=LinkListIn,
    output=Page[LinkOut],
    expose_api=True,
    ai={
        "description": "List what modifier groups apply to: the products and categories of a group, or the groups "
        "of a product or of a category.",
        "asks": {
            "en": (
                "which dishes ask for the doneness?",
                "what products is the Sauces group on?",
            ),
            "es": (
                "¿a qué platos se les pregunta el punto de la carne?",
                "¿qué productos llevan el grupo Salsas?",
            ),
        },
    },
)
def list_links(ctx: OperationContext, params: LinkListIn) -> dict:
    links = ModifierLink.objects.filter(LIVE_LINK).select_related(
        "group", "product", "category"
    )
    if params.group_id is not None or params.group is not None:
        links = links.filter(group=find_group(params.group_id, params.group))
    if params.product_id is not None:
        links = links.filter(product_id=params.product_id)
    if params.category_id is not None:
        links = links.filter(category_id=params.category_id)
    links = links.annotate(
        target_name=Lower(Coalesce("product__name", "category__name"))
    ).order_by("target_name", "id")
    return _page(links, params, link_row)


@operation(
    "modifier.link.get",
    kind="query",
    permission="modifier.view",
    input=LinkRefIn,
    output=LinkDetailOut,
    expose_api=True,
    ai={
        "description": "Get one link between a modifier group and what it applies to: by the link's id, or by the "
        "group and the product (id, SKU or name) or category (id or name). One to something deleted is not there.",
        "asks": {
            "en": (
                "does the Margherita pizza carry the Sauces group?",
                "is Extras attached to the fries?",
            ),
            "es": (
                "¿tiene la Pizza margarita enganchado el grupo Salsas?",
                "¿qué asignación hay entre el grupo Extras y las patatas bravas?",
            ),
        },
    },
)
def get_link(ctx: OperationContext, data: LinkRefIn) -> dict:
    links = ModifierLink.objects.filter(LIVE_LINK).select_related("group", "product", "category")
    if data.id is not None:
        link = links.filter(pk=data.id).first()
    else:
        group = find_group(data.group_id, data.group)
        if data.product_id is not None or data.product is not None:
            link = links.filter(group=group, product=find_product(data.product_id, data.product)).first()
        else:
            link = links.filter(group=group, category=find_category(data.category_id, data.category)).first()
    if link is None:
        raise NotFound(str(LINK_NOT_FOUND))
    row = link_row(link)
    return {**row, "label": f"{row['group_name']} · {row['product_name'] or row['category_name']}"}
