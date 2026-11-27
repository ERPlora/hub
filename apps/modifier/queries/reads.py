"""Lookups the reads and the writes of the modifier app share: a group or an option by its id or by its name as a
person says it, and the rows and pages of the screen's lists.
"""

from uuid import UUID

from django.db.models import Count, Q
from django.db.models.functions import Lower
from django.utils.translation import gettext_lazy as _
from live.errors import Conflict, NotFound

from apps.modifier.models import ModifierGroup, ModifierLink, ModifierOption
from base.text_search import contains_text

GROUP_NOT_FOUND = _("This group does not exist.")
GROUP_AMBIGUOUS = _("«%(said)s» names several groups: %(names)s. Say which one.")
OPTION_NOT_FOUND = _("This option does not exist.")
LINK_NOT_FOUND = _("This group does not apply there.")
OPTION_AMBIGUOUS = _(
    "«%(said)s» names several options: %(names)s. Say which one, or its group."
)
_LIVE_LINKS_OF_GROUP = Q(
    links__product__isnull=False, links__product__is_deleted=False
) | Q(links__category__isnull=False, links__category__is_deleted=False)


def find_group(
    group_id: UUID | None, said: str | None, *, lock: bool = False, rows=None
) -> ModifierGroup:
    """The group named by its id, or by its name as a person says it: exact (whatever the case), else
    the only one that contains it. ``NotFound`` when none; 409 ``modifier.group_ambiguous`` when several.
    The group comes from ``rows`` when given (e.g. with its counts): one read, so a deletion committed
    meanwhile is either not seen yet or not found, never a row that vanished between two reads."""
    groups = ModifierGroup.objects.all()
    if group_id is None:
        candidates = _first_match(
            groups, (Q(name__iexact=said), contains_text(said, "name"))
        )
        if len(candidates) > 1:
            names = ", ".join(group.name for group in candidates[:5])
            raise Conflict(
                str(GROUP_AMBIGUOUS) % {"said": said, "names": names},
                code="modifier.group_ambiguous",
            )
        group_id = candidates[0].pk if candidates else None
    found = (groups if rows is None else rows).filter(pk=group_id)
    group = (found.select_for_update() if lock else found).first()
    if group is None:
        raise NotFound(str(GROUP_NOT_FOUND))
    return group


def find_option(
    option_id: UUID | None,
    said: str | None,
    group_id: UUID | None = None,
    group_said: str | None = None,
    *,
    lock: bool = False,
) -> ModifierOption:
    """The option named by its id, or by its name (exact, else the only one that contains it), within its
    group when one is said. 409 ``modifier.option_ambiguous`` lists «Option (Group)» when several match."""
    options = ModifierOption.objects.select_related("group")
    if group_id is not None or group_said is not None:
        options = options.filter(group=find_group(group_id, group_said))
    if option_id is None:
        candidates = _first_match(
            options, (Q(name__iexact=said), contains_text(said, "name"))
        )
        if len(candidates) > 1:
            names = ", ".join(_option_label(option) for option in candidates[:5])
            raise Conflict(
                str(OPTION_AMBIGUOUS) % {"said": said, "names": names},
                code="modifier.option_ambiguous",
            )
        option_id = candidates[0].pk if candidates else None
    found = options.filter(pk=option_id)
    option = (found.select_for_update(of=("self",)) if lock else found).first()
    if option is None:
        raise NotFound(str(OPTION_NOT_FOUND))
    return option


def _option_label(option: ModifierOption) -> str:
    return f"{option.name} ({option.group.name})"


def _first_match(queryset, lookups) -> list:
    """The rows of the first lookup that matches anything (in order of preference), at most six."""
    for lookup in lookups:
        rows = list(queryset.filter(lookup).order_by(Lower("name"), "id")[:6])
        if rows:
            return rows
    return []


def groups_with_counts():
    return ModifierGroup.objects.annotate(
        option_count=Count("options", distinct=True),
        default_count=Count(
            "options", filter=Q(options__is_default=True), distinct=True
        ),
        link_count=Count("links", filter=_LIVE_LINKS_OF_GROUP, distinct=True),
    )


def group_row(group: ModifierGroup) -> dict:
    return {
        "id": group.id,
        "name": group.name,
        "kitchen_name": group.kitchen_name,
        "min_choices": group.min_choices,
        "max_choices": group.max_choices,
        "allow_repeat": group.allow_repeat,
        "is_required": group.min_choices >= 1,
        "sort_order": group.sort_order,
        "option_count": group.option_count,
        "default_count": group.default_count,
        "link_count": group.link_count,
        "created_at": group.created_at,
        "updated_at": group.updated_at,
    }


def load_group(group_id: UUID) -> dict:
    return group_row(groups_with_counts().get(pk=group_id))


def option_row(option: ModifierOption) -> dict:
    tax = option.tax_category
    return {
        "id": option.id,
        "group_id": option.group_id,
        "group_name": option.group.name,
        "name": option.name,
        "kitchen_name": option.kitchen_name,
        "price_delta": option.price_delta,
        "tax_category_key": tax.key if tax else None,
        "tax_category_name": tax.display_name if tax else None,
        "is_default": option.is_default,
        "allergens": option.allergens,
        "sort_order": option.sort_order,
        "created_at": option.created_at,
        "updated_at": option.updated_at,
    }


def load_option(option_id: UUID) -> dict:
    return option_row(
        ModifierOption.objects.select_related("group", "tax_category").get(pk=option_id)
    )


def link_row(link: ModifierLink) -> dict:
    product, category = link.product, link.category
    return {
        "id": link.id,
        "group_id": link.group_id,
        "group_name": link.group.name,
        "target_kind": link.target_kind,
        "product_id": link.product_id,
        "product_name": product.name if product else None,
        "product_sku": product.sku if product else None,
        "category_id": link.category_id,
        "category_name": category.name if category else None,
        "created_at": link.created_at,
    }


def load_link(link_id: UUID) -> dict:
    return link_row(
        ModifierLink.objects.select_related("group", "product", "category").get(
            pk=link_id
        )
    )


def _page(queryset, params, row) -> dict:
    total = queryset.count()
    rows = [
        row(item) for item in queryset[params.offset : params.offset + params.limit]
    ]
    return {
        "rows": rows,
        "total": total,
        "limit": params.limit,
        "offset": params.offset,
    }
