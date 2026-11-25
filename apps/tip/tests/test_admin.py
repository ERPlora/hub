"""The tips app's admin, for the platform's staff: its tips and its settings row."""

from django.contrib import admin

from apps.tip.models import Settings, Tip


def test_its_tips_and_its_settings_are_in_the_admin():
    assert admin.site.is_registered(Tip)
    assert admin.site.is_registered(Settings)


def test_a_tip_is_found_by_its_sale_or_its_person():
    assert admin.site._registry[Tip].search_fields == ("sale__number", "member__first_name", "member__last_name")
