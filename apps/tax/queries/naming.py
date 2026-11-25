"""How a person or an outside text names a tax category: its exact key, its name in any language of the Hub or a
learned alias, never a similar one."""


from django.conf import settings
from django.utils import translation

from apps.tax.models import SYSTEM_CATEGORY_LABELS, TaxAlias, TaxCategory
from apps.tax.schemas import normalize_text


def category_by_reference(text: str) -> TaxCategory | None:
    """The category a person names: its exact key, else what ``resolve_category_text`` reads."""
    category = TaxCategory.objects.filter(key=text.strip()).first()
    if category is None:
        key, _matched_by = resolve_category_text(text)
        category = TaxCategory.objects.filter(key=key).first() if key else None
    return category


def resolve_category_text(text: str) -> tuple[str | None, str | None]:
    """``(category key, matched by)`` of an outside text, or ``(None, None)``; never a similar one.

    Compared normalised, against the active categories and aliases, in this order: the keys; the
    names, the stored ones and the factory categories' in every language of the Hub; the aliases.
    """
    text = normalize_text(text)
    categories = TaxCategory.objects.filter(is_active=True)
    if categories.filter(key=text).exists():
        return text, "key"
    for category in categories.only("key", "name").order_by("key", "id"):
        if normalize_text(category.name) == text:
            return category.key, "name"
    system_keys = set(categories.filter(is_system=True).values_list("key", flat=True))
    for language, _language_name in settings.LANGUAGES:
        with translation.override(language):
            for key, label in SYSTEM_CATEGORY_LABELS.items():
                if key in system_keys and normalize_text(str(label.name)) == text:
                    return key, "name"
    alias = TaxAlias.objects.select_related("category").filter(alias=text, is_active=True, category__is_active=True).first()
    if alias is not None:
        return alias.category.key, "alias"
    return None, None
