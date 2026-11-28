"""What the kitchen app's models share: closed lists, where a dish goes and who made and changed a row."""

from django.db.models import Q

from apps.kitchen.models.fields import (
    ACTOR_MAX_LENGTH,
    Audited,
    Destination,
    PrinterUsage,
    _destination,
    _in,
    _printer_usage,
)


def test_a_closed_list_takes_the_values_of_its_choices():
    assert _in("destination", Destination) == Q(destination__in=["both", "display", "printer"])


def test_a_station_or_a_dish_goes_to_screen_and_paper_by_the_kitchen_printer_unless_told_otherwise():
    destination, usage = _destination(), _printer_usage()
    assert (destination.default, destination.choices, destination.max_length) == ("both", Destination.choices, 8)
    assert (usage.default, usage.choices, usage.max_length) == ("kitchen", PrinterUsage.choices, 8)


def test_an_audited_row_keeps_when_it_was_made_and_who_made_and_changed_it_if_anyone():
    fields = {field.name: field for field in Audited._meta.local_fields}
    assert Audited._meta.abstract
    assert (fields["created_at"].editable, fields["updated_at"].auto_now) == (False, True)
    assert [(fields[name].max_length, fields[name].blank) for name in ("created_by", "updated_by")] == [
        (ACTOR_MAX_LENGTH, True)
    ] * 2
