"""The factory catalogue of the tax app (TAX-F16): 11 categories, 18 aliases and the Spanish VAT rules.

Planted the first time a hub creates the app's tables (and in every template that carries it). It
never touches a row that already exists: a category by its key, a rule by its slot (Spain, the whole
country, its category, a root) whatever its state, an alias by its text. No IGIC, IPSI, surcharge or
other country: a made-up rate would be declared to the tax agency as if it were valid.

The data is frozen here on purpose (a migration never imports the app's code). The reverse removes
exactly what the seed planted; if the business made a seeded category its own (rules or aliases of its
own point to it), PROTECT stops the reverse instead of deleting the business's data.
"""

from datetime import date
from decimal import Decimal

from django.db import migrations

SPAIN = "ES"
SPAIN_FROM = date(2012, 9, 1)
GENERAL_REGIME = "01"

# key → (English name, description, rate, qualification, exemption cause)
CATEGORIES = {
    "restaurant.food": ("Restaurant — food", "", "10", "subject", ""),
    "restaurant.drink": ("Restaurant — drink", "", "10", "subject", ""),
    # Drinks served to drink on the premises are a hospitality service (art. 91.Uno.2.2º LIVA), 10 %;
    # alcohol sold to take away or delivered is a sale of goods, 21 % (retail.alcohol).
    "restaurant.alcohol": (
        "Restaurant — alcohol",
        "Alcoholic drinks served to drink on the premises — art. 91.Uno.2.2 (ES)",
        "10",
        "subject",
        "",
    ),
    "retail.alcohol": (
        "Retail — alcohol to take away",
        "Alcoholic drinks sold to take away or delivered — art. 90 (ES)",
        "21",
        "subject",
        "",
    ),
    "restaurant.delivery": ("Restaurant — delivery", "", "10", "subject", ""),
    "service.generic": ("Service — generic", "", "21", "subject", ""),
    "service.health": (
        "Service — healthcare (VAT exempt)",
        "Assistance provided by medical or health professionals — art. 20.Uno.3 (ES)",
        "0",
        "exempt",
        "E1",
    ),
    "service.education": (
        "Service — education (VAT exempt)",
        "Regulated teaching and training — art. 20.Uno.9 (ES)",
        "0",
        "exempt",
        "E1",
    ),
    "product.generic": ("Product — generic", "", "21", "subject", ""),
    "product.reduced": ("Product — reduced (food staples, pharmacy)", "", "10", "subject", ""),
    "product.super_reduced": ("Product — super-reduced (bread, books, basics)", "", "4", "subject", ""),
}

ALIASES = {
    "food": "restaurant.food",
    "prepared_food": "restaurant.food",
    "meal": "restaurant.food",
    "pizza": "restaurant.food",
    "drink": "restaurant.drink",
    "beverage": "restaurant.drink",
    "soft_drink": "restaurant.drink",
    "alcohol": "restaurant.alcohol",
    "beer": "restaurant.alcohol",
    "wine": "restaurant.alcohol",
    "takeaway_beer": "retail.alcohol",
    "takeaway_wine": "retail.alcohol",
    "delivery": "restaurant.delivery",
    "service": "service.generic",
    "product": "product.generic",
    "goods": "product.generic",
    "health": "service.health",
    "training": "service.education",
}


def plant(apps, schema_editor):
    TaxCategory = apps.get_model("tax", "TaxCategory")
    TaxRule = apps.get_model("tax", "TaxRule")
    TaxAlias = apps.get_model("tax", "TaxAlias")
    categories = TaxCategory.objects.using(schema_editor.connection.alias)
    rules = TaxRule.objects.using(schema_editor.connection.alias)
    aliases = TaxAlias.objects.using(schema_editor.connection.alias)

    for key, (name, description, rate, operation_class, exempt_reason) in CATEGORIES.items():
        category = categories.filter(key=key).first()
        if category is None:
            category = categories.create(key=key, name=name, description=description, is_system=True)
        slot = rules.filter(category=category, country_code=SPAIN, region_code="", parent__isnull=True)
        if not slot.exists():
            rules.create(
                category=category,
                country_code=SPAIN,
                region_code="",
                rate_pct=Decimal(rate),
                tax_type="vat",
                operation_class=operation_class,
                exempt_reason=exempt_reason,
                regime_key=GENERAL_REGIME if operation_class == "exempt" else "",
                valid_from=SPAIN_FROM,
            )

    for alias, key in ALIASES.items():
        if not aliases.filter(alias=alias).exists():
            aliases.create(alias=alias, category=categories.get(key=key), source="shipped")


def unplant(apps, schema_editor):
    TaxCategory = apps.get_model("tax", "TaxCategory")
    TaxRule = apps.get_model("tax", "TaxRule")
    TaxAlias = apps.get_model("tax", "TaxAlias")
    TaxAlias.objects.using(schema_editor.connection.alias).filter(alias__in=ALIASES, source="shipped").delete()
    TaxRule.objects.using(schema_editor.connection.alias).filter(
        category__key__in=CATEGORIES,
        country_code=SPAIN,
        region_code="",
        parent__isnull=True,
        valid_from=SPAIN_FROM,
    ).delete()
    TaxCategory.objects.using(schema_editor.connection.alias).filter(key__in=CATEGORIES, is_system=True).delete()


class Migration(migrations.Migration):
    dependencies = [("tax", "0001_initial")]

    operations = [migrations.RunPython(plant, unplant)]
