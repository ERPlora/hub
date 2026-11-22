# Every card's name, tax id and company, lowercased and without accents: what is searched for whoever does not see the
# customers' email and phone. ``Customer.save`` keeps it from now on; here it is written for the cards that exist. The
# normalising is copied from ``apps.customer.search`` (a migration never imports code that may change). Backwards, the
# column goes and nothing else changes.

import unicodedata

from django.db import migrations, models

BATCH = 500


def normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text or "")
    return "".join(char for char in decomposed if not unicodedata.combining(char)).lower().strip()


def searchable(*parts: str) -> str:
    return " ".join(normalized for normalized in (normalize(part) for part in parts) if normalized)


def forwards(apps, schema_editor):
    customers = apps.get_model("customer", "Customer").objects.using(schema_editor.connection.alias)
    cards = list(customers.only("id", "name", "tax_id", "company_name"))
    for card in cards:
        card.search_text_without_contact = searchable(card.name, card.tax_id, card.company_name)
    customers.bulk_update(cards, ["search_text_without_contact"], batch_size=BATCH)


class Migration(migrations.Migration):

    dependencies = [
        ('customer', '0003_health_record'),
    ]

    operations = [
        migrations.AddField(
            model_name='customer',
            name='search_text_without_contact',
            field=models.TextField(blank=True, default='', editable=False, verbose_name='search text without contact details'),
        ),
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
