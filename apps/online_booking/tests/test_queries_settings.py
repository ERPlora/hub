"""The page's settings as they are read: the factory ones until somebody saves them, with the rules of the diary."""

from apps.online_booking.queries.settings import get_settings
from apps.online_booking.schemas import NoIn

from .conftest import HUB_DB, ctx_for, make_page, run

pytestmark = HUB_DB


def test_the_settings_are_the_factory_ones_until_saved_with_the_rules_of_the_diary(db):
    settings = run("online_booking.settings.get").model_dump()
    assert settings == {
        "is_enabled": False,
        "page_title": "",
        "welcome_message": "",
        "primary_color": "#6366f1",
        "logo": "",
        "logo_url": "",
        "require_email": False,
        "max_upcoming_per_customer": 3,
        "allow_staff_selection": True,
        "allow_notes": True,
        "confirmation_message": "",
        "cancellation_policy": "",
        "min_booking_notice": 60,
        "max_advance_booking": 90,
        "slot_interval": 15,
        "auto_confirm_online": True,
        "allow_customer_cancellation": True,
        "cancellation_notice_hours": 24,
        "timezone": "Europe/Madrid",
    }


def test_the_employee_reads_the_settings_too(db):
    make_page(page_title="Salón Lucía")
    assert get_settings(ctx_for("hub_employee"), NoIn()).page_title == "Salón Lucía"
