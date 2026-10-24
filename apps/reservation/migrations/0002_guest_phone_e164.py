# The guest's phone kept as Customers keeps it (RESERVATION-F06, F08, F14, F16).
# Before this, a reservation or a waitlist entry whose card was chosen kept the phone as typed («600 111 222»),
# and the inbox, which looks for exactly the international number, told nobody (RESERVATION-F19). Every kept
# phone is read with Customers' rules (``apps.customer.phones.to_e164``, copied here: a migration never imports
# code that may change) in the business's country, Spain in phase 1 (``apps.customer.queries.business_country``),
# and written in E.164. What is not a valid number of its country stays as it is: never guessed.
# Backwards, nothing to undo: the typed form is not known any more, and E.164 is what every reader accepts.

import phonenumbers
from django.db import migrations
from phonenumbers import NumberParseException, PhoneNumberFormat

#: The business's country in phase 1: a number without prefix is one of Spain.
COUNTRY = "ES"
#: What may separate the digits of a typed number (a no-break space included).
SEPARATORS = frozenset("  \t-./()")


def e164(raw: str) -> str:
    """``raw`` in E.164, or ``raw`` itself when it is not a valid number of its country."""
    text = raw.strip()
    seen_digit = seen_plus = False
    for char in text:
        if "0" <= char <= "9":
            seen_digit = True
        elif char == "+" and not (seen_plus or seen_digit):
            seen_plus = True
        elif char not in SEPARATORS:
            return raw
    try:
        number = phonenumbers.parse(text, COUNTRY)
    except NumberParseException:
        return raw
    if number.extension or not phonenumbers.is_valid_number(number):
        return raw
    return phonenumbers.format_number(number, PhoneNumberFormat.E164)


def forwards(apps, schema_editor):
    for name in ("Reservation", "WaitlistEntry"):
        model = apps.get_model("reservation", name)
        kept = list(
            model.objects.using(schema_editor.connection.alias)
            .exclude(guest_phone="")
            .values_list("pk", "guest_phone")
        )
        for pk, phone in kept:
            written = e164(phone)
            if written != phone:
                # ``update`` leaves ``updated_at`` alone: nobody changed the reservation.
                model.objects.using(schema_editor.connection.alias).filter(pk=pk).update(
                    guest_phone=written
                )


def backwards(apps, schema_editor):
    """Nothing to restore: the typed form is not known any more, and E.164 is read everywhere."""


class Migration(migrations.Migration):
    dependencies = [
        ("reservation", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
