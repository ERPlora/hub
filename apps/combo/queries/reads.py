"""How a menu, a course and a choice are found: by the id, or as a person says it."""

from uuid import UUID

from django.db.models import Q, QuerySet
from django.utils.translation import gettext_lazy as _
from live.errors import Conflict, NotFound

from apps.combo.models import ChoiceGroup, ChoiceOption, Combo
from base.text_search import contains_text

COMBO_NOT_FOUND = _("That menu does not exist in this business.")
GROUP_NOT_FOUND = _("That course does not exist in this menu.")
OPTION_NOT_FOUND = _("That choice does not exist in this menu.")
AMBIGUOUS_COMBO = _(
    "There are several menus called “%(said)s”: %(names)s. Say which one."
)
AMBIGUOUS_GROUP = _(
    "There are several courses called “%(said)s”: %(names)s. Say which one."
)
AMBIGUOUS_OPTION = _(
    "“%(said)s” is a choice of several courses: %(names)s. Say which course."
)

#: How many candidates an ambiguous reference lists.
MAX_CANDIDATES = 5


def _first_match(queryset: QuerySet, lookups) -> list:
    """The rows of the first lookup that matches anything, in order of preference (at most six)."""
    for lookup in lookups:
        rows = list(queryset.filter(lookup)[: MAX_CANDIDATES + 1])
        if rows:
            return rows
    return []


def _names(rows, label) -> str:
    return ", ".join(label(row) for row in rows[:MAX_CANDIDATES])


def find_combo(
    combo_id: UUID | None, said: str | None, *, lock: bool = False, rows: QuerySet[Combo] | None = None
) -> Combo:
    """The menu named by its id, or by its name as a person says it. It comes from ``rows`` when given
    (e.g. with its tree): one read, so a deletion committed meanwhile is either not seen yet or not
    found, never a row that vanished between two reads."""
    combos = Combo.objects.order_by("name", "id")
    if combo_id is None:
        candidates = _first_match(combos, (Q(name__iexact=said), contains_text(said, "name")))
        if len(candidates) > 1:
            names = _names(candidates, lambda combo: combo.name)
            raise Conflict(
                str(AMBIGUOUS_COMBO) % {"said": said, "names": names},
                code="combo.combo_ambiguous",
            )
        combo_id = candidates[0].pk if candidates else None
    found = (Combo.objects.all() if rows is None else rows).filter(pk=combo_id)
    combo = (found.select_for_update() if lock else found).first()
    if combo is None:
        raise NotFound(str(COMBO_NOT_FOUND))
    return combo


def find_group(
    group_id: UUID | None,
    combo_id: UUID | None,
    combo: str | None,
    said: str | None,
    *,
    lock: bool = False,
) -> ChoiceGroup:
    """The course named by its id, or by its name inside its menu."""
    if group_id is None:
        menu = find_combo(combo_id, combo)
        groups = menu.groups.order_by("sort_order", "name", "id")
        candidates = _first_match(
            groups, (Q(name__iexact=said), contains_text(said, "name"))
        )
        if len(candidates) > 1:
            names = _names(candidates, lambda group: group.name)
            raise Conflict(
                str(AMBIGUOUS_GROUP) % {"said": said, "names": names},
                code="combo.group_ambiguous",
            )
        group_id = candidates[0].pk if candidates else None
    found = ChoiceGroup.objects.filter(pk=group_id).select_related("combo")
    group = (found.select_for_update(of=("self",)) if lock else found).first()
    if group is None:
        raise NotFound(str(GROUP_NOT_FOUND))
    return group


def _product_lookups(said: str):
    return (
        Q(product__sku__iexact=said),
        Q(product__name__iexact=said),
        contains_text(said, "product__name"),
    )


def find_option(  # noqa: PLR0913
    option_id: UUID | None,
    *,
    combo_id: UUID | None = None,
    combo: str | None = None,
    group_id: UUID | None = None,
    group: str | None = None,
    product: str | None = None,
    lock: bool = False,
) -> ChoiceOption:
    """The choice named by its id, or by its product inside its menu (and its course when told)."""
    if option_id is None:
        # The schemas ask for the menu (or the course's id) whenever a choice is named by its product.
        if group_id is not None or group is not None:
            options = ChoiceOption.objects.filter(group=find_group(group_id, combo_id, combo, group))
        else:
            options = ChoiceOption.objects.filter(group__combo=find_combo(combo_id, combo))
        options = options.select_related("group", "product").order_by(
            "group__sort_order", "sort_order", "id"
        )
        candidates = _first_match(options, _product_lookups(product))
        if len(candidates) > 1:
            names = _names(candidates, lambda option: option.group.name)
            raise Conflict(
                str(AMBIGUOUS_OPTION) % {"said": product, "names": names},
                code="combo.option_ambiguous",
            )
        option_id = candidates[0].pk if candidates else None
    found = ChoiceOption.objects.filter(pk=option_id).select_related(
        "group__combo", "product"
    )
    option = (found.select_for_update(of=("self",)) if lock else found).first()
    if option is None:
        raise NotFound(str(OPTION_NOT_FOUND))
    return option
