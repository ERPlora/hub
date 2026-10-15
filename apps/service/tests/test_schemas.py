"""Input schemas of the service app: what a caller (screen, assistant, API key) may send.

Every rule that needs no database lives here, so the 422 names the field: money in whole cents and
never negative, a service takes time, a voucher has lines, a reason is said, a reference is given.
"""

import datetime as dt
import uuid

import pytest
from pydantic import ValidationError

from apps.service.schemas import (
    AdjustIn,
    AssignIn,
    AssignmentPatchIn,
    CategoryIn,
    CategoryPatchIn,
    GrantIn,
    GrantListIn,
    MovementListIn,
    PackageIn,
    PackagePatchIn,
    PageIn,
    RedeemIn,
    ServiceBulkIn,
    ServiceIn,
    ServiceListIn,
    ServicePatchIn,
    ServiceRefIn,
    SettingsIn,
    VoidIn,
)


def errors(schema, **data) -> dict[str, str]:
    """The fields ``schema`` refuses in ``data``, with the first message of each (``__all__`` for the whole)."""
    try:
        schema.model_validate(data)
    except ValidationError as exc:
        out: dict[str, str] = {}
        for error in exc.errors():
            out.setdefault(
                ".".join(str(part) for part in error["loc"]) or "__all__", error["msg"]
            )
        return out
    return {}


def test_a_page_is_one_to_a_hundred_rows():
    assert PageIn().limit == 50
    assert errors(PageIn, limit=0) and errors(PageIn, limit=101)
    assert not errors(PageIn, limit=100, offset=200)


def test_a_list_refuses_a_filter_it_does_not_declare():
    assert "colour" in errors(ServiceListIn, colour="red")
    assert not errors(
        ServiceListIn,
        status="archived",
        price_min=0,
        price_max=5000,
        pricing_type="from",
    )


def test_a_service_is_named_by_its_id_or_by_its_name():
    assert errors(ServiceRefIn) == {
        "__all__": "Value error, Say which service: its id, or its name."
    }
    assert not errors(ServiceRefIn, id=str(uuid.uuid7()))
    assert not errors(ServiceRefIn, service="Haircut")


def test_a_new_service_needs_a_name_and_whole_non_negative_cents():
    assert "name" in errors(ServiceIn, name="   ")
    assert "price" in errors(ServiceIn, name="Cut", price=-1)
    assert "price" in errors(ServiceIn, name="Cut", price=12.5)
    assert "cost" in errors(ServiceIn, name="Cut", cost=-5)
    created = ServiceIn.model_validate({"name": "  Cut  ", "price": 2000})
    assert (
        created.name,
        created.pricing_type,
        created.duration_minutes,
        created.tax_category_key,
    ) == (
        "Cut",
        "fixed",
        None,
        None,
    )


def test_a_service_takes_time_and_serves_someone():
    assert "duration_minutes" in errors(ServiceIn, name="Cut", duration_minutes=0)
    assert "max_capacity" in errors(ServiceIn, name="Cut", max_capacity=0)
    assert "buffer_before" in errors(ServiceIn, name="Cut", buffer_before=-1)


def test_a_pricing_type_is_one_of_the_five_and_its_minimum_is_not_above_its_maximum():
    assert "pricing_type" in errors(ServiceIn, name="Cut", pricing_type="barter")
    problems = errors(
        ServiceIn,
        name="Highlights",
        pricing_type="from",
        min_price=6500,
        max_price=5000,
    )
    assert problems == {
        "__all__": "Value error, The minimum price cannot be above the maximum price."
    }


def test_an_edit_refuses_a_field_that_is_not_editable_and_an_empty_name():
    ref = str(uuid.uuid7())
    assert "is_active" in errors(ServicePatchIn, id=ref, is_active=False)
    assert "name" in errors(ServicePatchIn, id=ref, name="")
    assert not errors(ServicePatchIn, id=ref, category_id=None, price=0)


def test_a_bulk_create_is_one_to_five_hundred_services_with_each_mistake_under_its_line():
    assert "services" in errors(ServiceBulkIn, services=[])
    assert "services" in errors(
        ServiceBulkIn, services=[{"name": f"S{i}"} for i in range(501)]
    )
    assert "services.1.price" in errors(
        ServiceBulkIn, services=[{"name": "A"}, {"name": "B", "price": -1}]
    )


def test_a_category_has_a_name_an_hex_colour_and_a_non_negative_order():
    assert "name" in errors(CategoryIn, name=" ")
    assert "color" in errors(CategoryIn, name="Hair", color="red")
    assert "sort_order" in errors(CategoryIn, name="Hair", sort_order=-1)
    assert not errors(CategoryIn, name="Hair", color="#AA3300", sort_order=2)
    assert errors(CategoryPatchIn) == {
        "__all__": "Value error, Say which category: its id, or its name."
    }


def test_the_settings_keep_a_duration_of_at_least_a_minute():
    assert "default_duration" in errors(SettingsIn, default_duration=0)
    assert "default_buffer_time" in errors(SettingsIn, default_buffer_time=-1)
    assert not errors(SettingsIn, default_tax_category_key=None, show_prices=False)


def test_an_assignment_names_the_service_and_the_professional_with_an_own_time_and_price():
    assert errors(AssignIn, member="Ana") == {
        "__all__": "Value error, Say which service: its id, or its name."
    }
    assert errors(AssignIn, service="Cut") == {
        "__all__": "Value error, Say which professional: their id, or their name."
    }
    assert "custom_duration" in errors(
        AssignIn, service="Cut", member="Ana", custom_duration=0
    )
    assert "custom_price" in errors(
        AssignIn, service="Cut", member="Ana", custom_price=-1
    )
    assert "custom_price" in errors(
        AssignmentPatchIn, id=str(uuid.uuid7()), custom_price=-1
    )


def test_a_package_needs_a_line_a_discount_in_range_and_no_service_twice():
    cut = str(uuid.uuid7())
    assert errors(PackageIn, name="Bono", items=[]) == {
        "items": "List should have at least 1 item after validation, not 0"
    }
    assert "discount_percent_bp" in errors(
        PackageIn, name="Bono", discount_percent_bp=10001, items=[{"service_id": cut}]
    )
    assert "validity_days" in errors(
        PackageIn, name="Bono", validity_days=0, items=[{"service_id": cut}]
    )
    assert "max_uses" in errors(
        PackageIn, name="Bono", max_uses=0, items=[{"service_id": cut}]
    )
    assert "items.0.sessions" in errors(
        PackageIn, name="Bono", items=[{"service_id": cut, "sessions": 0}]
    )
    assert errors(
        PackageIn, name="Bono", items=[{"service_id": cut}, {"service_id": cut}]
    ) == {
        "items": "Value error, A service is repeated in the lines: each service goes once."
    }
    assert errors(PackageIn, name="Bono", items=[{"sessions": 2}]) == {
        "items.0": "Value error, Say which service: its id, or its name."
    }


def test_a_package_edit_never_changes_its_lines():
    assert "items" in errors(PackagePatchIn, id=str(uuid.uuid7()), items=[])


def test_a_voucher_is_granted_to_a_customer():
    assert errors(GrantIn, package="Bono") == {
        "__all__": "Value error, Pick the customer this voucher belongs to: a voucher with no owner cannot be redeemed."
    }
    assert "amount" in errors(GrantIn, package="Bono", customer="Lucía", amount=-1)
    assert not errors(GrantIn, package="Bono", customer="+34600111222", amount=9000)


def test_a_voucher_is_never_bought_in_the_future_and_its_moment_has_a_time_zone():
    # A purchase dated ahead would never expire: the extension of a voucher is «Adjust», with its limits.
    now = dt.datetime.now(dt.UTC)
    base = {"package": "Bono", "customer": "Lucía"}
    assert errors(GrantIn, **base, granted_at=(now + dt.timedelta(days=1)).isoformat()) == {
        "granted_at": "Value error, A voucher cannot be bought in the future."
    }
    assert errors(GrantIn, **base, granted_at="2026-10-01T10:00:00") == {
        "granted_at": "Value error, Give the moment with its time zone."
    }
    assert not errors(GrantIn, **base, granted_at=(now + dt.timedelta(minutes=2)).isoformat())
    assert not errors(GrantIn, **base, granted_at=(now - dt.timedelta(days=40)).isoformat())


def test_voiding_and_adjusting_say_why():
    ref = str(uuid.uuid7())
    assert errors(VoidIn, id=ref, reason="   ") == {
        "reason": "Value error, Say why this voucher is being voided: the reason stays on its record."
    }
    assert errors(AdjustIn, id=ref, uses_delta=1, reason=" ") == {
        "reason": "Value error, Say why this voucher is being adjusted: the reason stays on its record."
    }


def test_an_adjustment_moves_up_to_a_hundred_sessions_and_a_year_of_days_and_moves_something():
    ref = str(uuid.uuid7())
    assert "uses_delta" in errors(AdjustIn, id=ref, uses_delta=101, reason="x")
    assert "uses_delta" in errors(AdjustIn, id=ref, uses_delta=-101, reason="x")
    assert "days_delta" in errors(AdjustIn, id=ref, days_delta=367, reason="x")
    assert "days_delta" in errors(AdjustIn, id=ref, days_delta=-1, reason="x")
    assert errors(AdjustIn, id=ref, reason="closed in August") == {
        "__all__": "Value error, Add or remove at least one session, or add at least one day."
    }


def test_a_session_is_spent_from_a_voucher_sold():
    assert "id" in errors(RedeemIn)
    assert not errors(
        RedeemIn, id=str(uuid.uuid7()), service="Cut", sale_id=str(uuid.uuid7())
    )


def test_a_movements_list_names_its_package_and_a_grants_list_may_filter_by_customer():
    assert errors(MovementListIn) == {
        "__all__": "Value error, Say which package: its id, or its name."
    }
    assert not errors(GrantListIn, customer="Lucía", status="voided")


@pytest.mark.parametrize(
    "schema", [ServiceIn, CategoryIn, PackageIn, GrantIn, SettingsIn]
)
def test_writes_refuse_a_field_they_do_not_know(schema):
    assert "colour" in errors(
        schema,
        colour="red",
        name="X",
        items=[{"service": "Cut"}],
        package="P",
        customer="C",
    )
