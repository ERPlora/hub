"""The take-away alcohol category for the hubs that ran the first 0002 (TAX-F16, review 2026-10-14).

Alcoholic drinks served to drink on the premises are a hospitality service, 10 % (art. 91.Uno.2.2º of
Law 37/1992): 0002 now plants restaurant.alcohol at 10 %. Alcohol sold to take away or delivered is a
sale of goods, 21 %: retail.alcohol, with its two aliases. A hub that already ran the first 0002 gets
retail.alcohol here; its restaurant.alcohol rule is its own and is not rewritten (a rate changes with
an end date and a new rule, TAX-F07). On a new hub, 0002 already planted all of it and this is a no-op.

The data is frozen here on purpose (a migration never imports the app's code).
"""

from datetime import date
from decimal import Decimal

from django.db import migrations

SPAIN = "ES"
SPAIN_FROM = date(2012, 9, 1)
KEY = "retail.alcohol"
NAME = "Retail — alcohol to take away"
DESCRIPTION = "Alcoholic drinks sold to take away or delivered — art. 90 (ES)"
ALIASES = ("takeaway_beer", "takeaway_wine")


def plant(apps, schema_editor):
    TaxCategory = apps.get_model("tax", "TaxCategory")
    TaxRule = apps.get_model("tax", "TaxRule")
    TaxAlias = apps.get_model("tax", "TaxAlias")
    categories = TaxCategory.objects.using(schema_editor.connection.alias)
    rules = TaxRule.objects.using(schema_editor.connection.alias)
    aliases = TaxAlias.objects.using(schema_editor.connection.alias)

    category = categories.filter(key=KEY).first()
    if category is None:
        category = categories.create(key=KEY, name=NAME, description=DESCRIPTION, is_system=True)
    if not rules.filter(category=category, country_code=SPAIN, region_code="", parent__isnull=True).exists():
        rules.create(
            category=category,
            country_code=SPAIN,
            region_code="",
            rate_pct=Decimal("21"),
            tax_type="vat",
            operation_class="subject",
            valid_from=SPAIN_FROM,
        )
    for alias in ALIASES:
        if not aliases.filter(alias=alias).exists():
            aliases.create(alias=alias, category=category, source="shipped")


def unplant(apps, schema_editor):
    TaxCategory = apps.get_model("tax", "TaxCategory")
    TaxRule = apps.get_model("tax", "TaxRule")
    TaxAlias = apps.get_model("tax", "TaxAlias")
    TaxAlias.objects.using(schema_editor.connection.alias).filter(alias__in=ALIASES, source="shipped").delete()
    TaxRule.objects.using(schema_editor.connection.alias).filter(
        category__key=KEY, country_code=SPAIN, region_code="", parent__isnull=True, valid_from=SPAIN_FROM
    ).delete()
    TaxCategory.objects.using(schema_editor.connection.alias).filter(key=KEY, is_system=True).delete()


class Migration(migrations.Migration):
    dependencies = [("tax", "0004_root_natural_key")]

    operations = [migrations.RunPython(plant, unplant)]
