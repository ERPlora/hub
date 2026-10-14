"""The factory payment methods of the sale app: Cash and Card (the old seed of sales).

Planted the first time a hub creates the app's tables (and in every template that carries it), only
for a type the business has no method of yet: if the owner already made his own cash method, it stays
his. The names are canonical English: the till reads them in the reader's language while they keep
that name. The reverse removes exactly the factory rows no sale points to (PROTECT keeps the rest).

The data is frozen here on purpose (a migration never imports the app's code).
"""

from django.db import migrations

# (name, type, position)
FACTORY = [("Cash", "cash", 10), ("Card", "card", 20)]


def plant(apps, schema_editor):
    PaymentMethod = apps.get_model("sale", "PaymentMethod")
    for name, kind, position in FACTORY:
        if not PaymentMethod.objects.using(schema_editor.connection.alias).filter(type=kind).exists():
            PaymentMethod.objects.using(schema_editor.connection.alias).create(
                name=name, type=kind, sort_order=position, is_system=True, is_active=True
            )


def uproot(apps, schema_editor):
    PaymentMethod = apps.get_model("sale", "PaymentMethod")
    SalePayment = apps.get_model("sale", "SalePayment")
    used = SalePayment.objects.using(schema_editor.connection.alias).values_list("method_id", flat=True)
    PaymentMethod.objects.using(schema_editor.connection.alias).filter(is_system=True).exclude(pk__in=used).delete()


class Migration(migrations.Migration):
    dependencies = [("sale", "0001_initial")]

    operations = [migrations.RunPython(plant, uproot)]
