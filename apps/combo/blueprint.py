"""What of Menus and combos travels in an export of the business (BASE-F35): every menu with its closed price, its
courses and the products to choose in each with their supplement, and its own photo, read with the app's own reads and
written with its own creates. A product is named by its code (its name without one), never by an id of the business
that made the file."""

from django.utils.translation import gettext_lazy as _
from live.context import OperationContext

from base.blueprint.calls import (
    Dataset,
    Loaded,
    attempt,
    call,
    count_of,
    create_each,
    given,
    ids_of,
    listed,
    natural_key,
    pages,
    remover,
    text_of,
)
from base.blueprint.photos import load_image

MENU_FIELDS = ("name", "kitchen_name", "price", "supply_kind", "tax_category_key", "sort_order", "is_active")
COURSE_FIELDS = ("name", "min_choices", "max_choices", "allow_repeat")
CHOICE_FIELDS = ("product", "price_delta", "is_available")
IMAGES = ("combo.combo.set_image", "combo.combo.upload_image")


def _course_row(course) -> dict:
    choices = [
        {"product": option.sku or option.product_name, "price_delta": option.price_delta, "is_available": option.is_available}
        for option in course.options
    ]
    return {name: getattr(course, name) for name in COURSE_FIELDS} | {"choices": choices}


def _menu_rows(ctx: OperationContext) -> list[dict]:
    rows = []
    for menu in pages(ctx, "combo.combo.list"):
        courses = [_course_row(course) for course in call(ctx, "combo.combo.get", id=menu.id).groups]
        row = {name: getattr(menu, name) for name in MENU_FIELDS} | {"tax_category_key": menu.tax_category_key or ""}
        rows.append(row | {"courses": courses} | ({"image": menu.image} if menu.image else {}))
    return rows


def _fill(ctx: OperationContext, loaded: Loaded, row: dict, pk: str) -> None:
    menu = text_of(row, "name")
    for course in listed(row, "courses", dict):
        label = f"{menu} · {text_of(course, 'name')}"
        made = attempt(ctx, loaded, label, "combo.group.create", combo_id=pk, **given(course, COURSE_FIELDS))
        if made is None:
            continue
        for choice in listed(course, "choices", dict):
            attempt(ctx, loaded, f"{label} · {text_of(choice, 'product')}", "combo.option.create", group_id=made.id,
                    **given(choice, CHOICE_FIELDS))
    load_image(ctx, loaded, IMAGES, pk, row, menu)


def _menu_load(ctx: OperationContext, rows: list[dict], loaded: Loaded) -> None:
    """Each menu the business does not have, by its name, made with its courses, their choices and its photo."""
    existing = {natural_key(menu.name) for menu in pages(ctx, "combo.combo.list")}
    create_each(ctx, rows, loaded, name="combo.combo.create", key=lambda row: natural_key(text_of(row, "name")),
                existing=existing, build=lambda row: given(row, MENU_FIELDS), label=lambda row: text_of(row, "name"),
                after=lambda row, pk: _fill(ctx, loaded, row, pk))


DATASETS = [
    Dataset(
        key="combo.combo",
        models=("Combo", "ChoiceGroup", "ChoiceOption"),
        label=_("Menus"),
        rows=_menu_rows,
        ids=ids_of("combo.combo.list"),
        count=count_of("combo.combo.list"),
        load=_menu_load,
        remove=remover("combo.combo.delete"),
        images=IMAGES,
    ),
]
