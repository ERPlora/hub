"""What the public page shows of itself (its texts and its rules), only while it is on and to whoever may open it."""

import pytest
from live.errors import NotFound, PermissionDenied

from apps.online_booking.queries.page import public_page
from apps.online_booking.schemas import NoIn

from .conftest import HUB_DB, TUESDAY, ctx_for, make_page, make_rules, public

pytestmark = HUB_DB


def test_the_page_answers_nothing_while_it_is_off(salon):
    make_page(is_enabled=False)
    for name, data in (
        ("page", {}),
        ("services", {}),
        ("slots", {"service_ids": [str(salon.cut.id)], "date": TUESDAY.isoformat()}),
    ):
        with pytest.raises(NotFound) as error:
            public(name, data)
        assert error.value.code == "online_booking.page_disabled", name


def test_the_page_reads_its_texts_in_the_visitors_language_and_the_rules(salon):
    make_rules(
        min_booking_notice=120, max_advance_booking=30, cancellation_notice_hours=48
    )
    page = public("page").model_dump()
    assert page["title"] == "Book an appointment"
    assert (
        page["min_booking_notice"],
        page["max_advance_booking"],
        page["cancellation_notice_hours"],
    ) == (120, 30, 48)
    assert page["allow_customer_cancellation"] is True
    assert page["timezone"] == "Europe/Madrid"
    make_page(
        page_title="Salón Lucía", welcome_message="¡Hola!", primary_color="#112233"
    )
    page = public("page")
    assert (page.title, page.welcome_message, page.primary_color) == (
        "Salón Lucía",
        "¡Hola!",
        "#112233",
    )


def test_the_public_reads_need_the_public_permission(salon):
    with pytest.raises(PermissionDenied):
        public_page(ctx_for("hub_manager"), NoIn())
