"""Input and output schemas of the customer app: what the API, the live stream and the assistant accept.

Every field carries a description: the schemas are the JSON Schema of the assistant's tools.
"""

import inspect
import uuid
from datetime import date

import pydantic
import pytest
from django.utils import translation
from ninja import Schema

from apps.customer import schemas
from apps.customer.schemas import (
    ActivityIn,
    ConsentGrantIn,
    ConsentWithdrawIn,
    CustomerIn,
    CustomerListIn,
    CustomerPatchIn,
    CustomerRefIn,
    FieldIn,
    FieldPatchIn,
    GroupIn,
    GroupPatchIn,
    ImportIn,
    MergeIn,
    NoteIn,
    OrderLinkIn,
    PageIn,
    PurchaseRecordIn,
    SetGroupsIn,
    TagIn,
)

ID = uuid.uuid7()


def invalid_fields(schema, **data):
    with pytest.raises(pydantic.ValidationError) as excinfo:
        schema(**data)
    return {
        ".".join(str(part) for part in error["loc"]) for error in excinfo.value.errors()
    }


def messages(schema, **data):
    with pytest.raises(pydantic.ValidationError) as excinfo, translation.override("en"):
        schema(**data)
    return [
        str(error["ctx"]["error"]) if "ctx" in error else error["msg"]
        for error in excinfo.value.errors()
    ]


def all_schemas():
    return [
        value
        for value in vars(schemas).values()
        if inspect.isclass(value)
        and issubclass(value, Schema)
        and value.__module__ == schemas.__name__
    ]


def test_every_field_of_every_schema_has_a_description():
    missing = [
        f"{schema.__name__}.{name}"
        for schema in all_schemas()
        for name, field in schema.model_fields.items()
        if not field.description
    ]
    assert missing == []


# Pages


def test_page_defaults_and_limits():
    assert PageIn().model_dump() == {"limit": 50, "offset": 0}
    assert invalid_fields(PageIn, limit=0) == {"limit"}
    assert invalid_fields(PageIn, limit=101) == {"limit"}
    assert invalid_fields(PageIn, offset=-1) == {"offset"}


def test_customer_list_filters_and_sort():
    params = CustomerListIn()
    assert (params.sort, params.descending, params.search, params.limit) == (
        "name",
        False,
        None,
        50,
    )
    assert (
        CustomerListIn(sort="total_spent", descending=True, spent_min=1000).spent_min
        == 1000
    )
    assert invalid_fields(CustomerListIn, sort="password") == {"sort"}
    assert invalid_fields(CustomerListIn, lifecycle_stage="customer") == {
        "lifecycle_stage"
    }
    assert invalid_fields(CustomerListIn, spent_min=-1) == {"spent_min"}


# A customer: by id or by a human reference


def test_a_customer_is_named_by_its_id_or_by_its_name_phone_or_email():
    assert CustomerRefIn(id=ID).id == ID
    assert CustomerRefIn(customer=" Ana García ").customer == "Ana García"
    assert messages(CustomerRefIn) == [
        "Give the customer's id, or their name, phone or email."
    ]
    assert messages(CustomerRefIn, customer="   ") == [
        "Give the customer's id, or their name, phone or email."
    ]


def test_the_alta_needs_only_a_name():
    data = CustomerIn(name="  Ana  ")
    assert data.model_dump() == {
        "name": "Ana",
        "email": "",
        "phone": "",
        "tax_id": "",
        "company_name": "",
        "address": "",
        "city": "",
        "postal_code": "",
        "country": "",
        "avatar": "",
        "birthday": None,
        "anniversary": None,
        "source": "walk_in",
        "lifecycle_stage": "lead",
        "preferred_channel": "none",
        "notes": "",
    }


@pytest.mark.parametrize("name", ["", "   ", "x" * 201])
def test_the_name_is_1_to_200_characters(name):
    assert invalid_fields(CustomerIn, name=name) == {"name"}


def test_an_email_is_checked_and_trimmed():
    assert CustomerIn(name="Ana", email=" ana@example.com ").email == "ana@example.com"
    assert messages(CustomerIn, name="Ana", email="ana@") == ["Enter a valid email."]


def test_the_country_is_an_iso_code_in_any_case():
    assert CustomerIn(name="Ana", country=" es ").country == "ES"
    assert messages(CustomerIn, name="Ana", country="Spain") == [
        "Choose a country from the list."
    ]
    assert messages(CustomerIn, name="Ana", country="XX") == [
        "Choose a country from the list."
    ]


def test_choices_and_dates():
    data = CustomerIn(
        name="Ana", birthday="1990-05-04", lifecycle_stage="vip", source="whatsapp"
    )
    assert (data.birthday, data.lifecycle_stage, data.source) == (
        date(1990, 5, 4),
        "vip",
        "whatsapp",
    )
    assert invalid_fields(CustomerIn, name="Ana", preferred_channel="fax") == {
        "preferred_channel"
    }
    assert invalid_fields(CustomerIn, name="Ana", birthday="1990-02-31") == {"birthday"}


def test_a_patch_carries_only_what_was_sent():
    patch = CustomerPatchIn(id=ID, notes="", birthday=None)
    assert patch.model_dump(exclude_unset=True) == {
        "id": ID,
        "notes": "",
        "birthday": None,
    }
    assert invalid_fields(CustomerPatchIn, id=ID, name="") == {"name"}
    assert (
        CustomerPatchIn(
            customer="Ana", field_values=[{"field_id": ID, "value": " Látex "}]
        )
        .field_values[0]
        .value
        == "Látex"
    )


def test_import_rows_are_free_text_one_to_fifty():
    # Each row is checked on its own by the service: a bad row is skipped, never the whole block.
    assert (
        ImportIn(rows=[{"name": "", "email": "nope", "country": "Spain"}]).rows[0].email
        == "nope"
    )
    assert invalid_fields(ImportIn, rows=[]) == {"rows"}
    assert invalid_fields(ImportIn, rows=[{"name": "x"}] * 51) == {"rows"}


def test_groups_and_tags_by_id_or_by_name():
    data = SetGroupsIn(customer="Ana", groups=[" VIP "], group_ids=[ID])
    assert (data.groups, data.group_ids) == (["VIP"], [ID])
    assert SetGroupsIn(id=ID).model_dump() == {
        "id": ID,
        "customer": None,
        "group_ids": [],
        "groups": [],
    }


def test_merge_names_both_cards():
    assert MergeIn(id=ID, absorbed="ana garcia").absorbed == "ana garcia"
    assert messages(MergeIn, id=ID) == [
        "Give the duplicate's id, or its name, phone or email."
    ]


def test_a_note_is_1_to_5000_characters():
    assert (
        NoteIn(customer_id=ID, content=" Prefers mornings ").content
        == "Prefers mornings"
    )
    assert invalid_fields(NoteIn, customer_id=ID, content="  ") == {"content"}
    assert invalid_fields(NoteIn, customer_id=ID, content="x" * 5001) == {"content"}


def test_another_app_writes_activity_with_its_own_key_but_never_one_of_ours():
    assert (
        ActivityIn(customer_id=ID, kind="appointment.visit", title="Visit").kind
        == "appointment.visit"
    )
    assert invalid_fields(ActivityIn, customer_id=ID, kind="Visit!", title="Visit") == {
        "kind"
    }
    assert messages(ActivityIn, customer_id=ID, kind="erased", title="x") == [
        "That kind is the customer app's own: use another one."
    ]


def test_consent_needs_its_channel_and_for_a_grant_the_words_shown():
    grant = ConsentGrantIn(
        customer_id=ID, channel="email", notice_text="I want offers."
    )
    assert (grant.purpose, grant.source, grant.occurred_at) == ("marketing", "counter", None)
    assert invalid_fields(
        ConsentGrantIn, customer_id=ID, channel="email", notice_text=" "
    ) == {"notice_text"}
    assert invalid_fields(
        ConsentGrantIn, customer_id=ID, channel="any", notice_text="x"
    ) == {"channel"}
    assert ConsentWithdrawIn(customer_id=ID, channel="sms").reason == ""


def test_the_address_of_a_consent_is_never_the_callers():
    # The proof must name the real contact: the server takes it from the card (WORKBOOK F14).
    for schema in (ConsentGrantIn, ConsentWithdrawIn):
        assert "contact_point" not in schema.model_fields
    sent = ConsentGrantIn(customer_id=ID, channel="email", notice_text="Yes", contact_point="someone@else.com")
    assert "contact_point" not in sent.model_dump()


@pytest.mark.parametrize("schema", [GroupIn, GroupPatchIn, FieldIn, FieldPatchIn])
def test_an_order_beyond_the_columns_range_is_422_not_a_crash(schema):
    reference = {} if schema in (GroupIn, FieldIn) else {"id": ID}
    assert invalid_fields(schema, name="x", sort_order=2_147_483_648, **reference) == {"sort_order"}
    assert schema(name="x", sort_order=2_147_483_647, **reference).sort_order == 2_147_483_647


def test_a_purchase_beyond_the_columns_range_is_422():
    assert invalid_fields(PurchaseRecordIn, customer_id=ID, sale_id=ID, total=2**63) == {"total"}


def test_a_group_tag_and_field_name_is_trimmed():
    assert GroupIn(name=" VIP ").model_dump() == {
        "name": "VIP",
        "description": "",
        "color": "primary",
        "sort_order": 0,
    }
    assert TagIn(name=" Moroso ").name == "Moroso"
    assert GroupPatchIn(group="VIP", is_active=False).is_active is False
    assert messages(GroupPatchIn, is_active=False) == [
        "Give the group's id or its name."
    ]


def test_a_select_field_needs_its_options_and_the_others_drop_them():
    field = FieldIn(
        name="Hair", field_type="select", options=[" Short ", "Long", "Short"]
    )
    assert field.options == ["Short", "Long"]
    assert FieldIn(name="Allergies", options=["x"]).options == []
    assert messages(FieldIn, name="Hair", field_type="select", options=[]) == [
        "Add at least one option."
    ]


def test_an_order_link_without_customer_unlinks():
    assert OrderLinkIn(order_id=ID).model_dump() == {
        "order_id": ID,
        "customer_id": None,
        "customer": None,
    }


def test_a_purchase_is_in_whole_cents():
    assert PurchaseRecordIn(customer_id=ID, sale_id=ID, total=1250).currency == ""
    assert invalid_fields(PurchaseRecordIn, customer_id=ID, sale_id=ID, total=-1) == {
        "total"
    }
    assert invalid_fields(PurchaseRecordIn, customer_id=ID, sale_id=ID, total=12.5) == {
        "total"
    }
