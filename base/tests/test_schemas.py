"""Shape of base.session.me, the contract the shell reads (packages/ui src/shell/session.ts), and the marks of a
schema the assistant's card reads."""

import pydantic
import pytest

from base.schemas import RecordNameOut, SessionMeIn, SessionMeOut, exactly_one, in_currency_of

FULL = {
    "user": {"id": "7", "label": "Ana"},
    "scope": {"kind": "host", "key": "a"},
    "permissions": ["demo.view"],
    "menu": [{"id": "demo", "label": "Demo", "items": [{"path": "/demo/items", "label": "Demo", "icon": "ion:flask-outline"}]}],
    "apps": [{"label": "demo", "state": "on"}],
    "language": "es",
    "demo": None,
}


def test_input_is_empty():
    assert SessionMeIn.model_fields == {}


def test_full_output_round_trips():
    assert SessionMeOut.model_validate(FULL).model_dump(mode="json") == FULL


def test_anonymous_output():
    anonymous = {**FULL, "user": None, "permissions": [], "menu": [], "apps": []}
    assert SessionMeOut.model_validate(anonymous).user is None


@pytest.mark.parametrize("state", ["on", "activating", "off"])
def test_app_states(state):
    SessionMeOut.model_validate({**FULL, "apps": [{"label": "demo", "state": state}]})


def test_unknown_app_state_is_rejected():
    with pytest.raises(pydantic.ValidationError):
        SessionMeOut.model_validate({**FULL, "apps": [{"label": "demo", "state": "broken"}]})


def test_a_demo_s_session_says_when_it_ends():
    # ``demo`` is always there, ``null`` on a business's hub.
    on_a_demo = {**FULL, "demo": {"expires_at": "2026-10-17T18:00:00Z"}}
    assert SessionMeOut.model_validate(on_a_demo).model_dump(mode="json") == on_a_demo
    without = {key: value for key, value in FULL.items() if key != "demo"}
    with pytest.raises(pydantic.ValidationError):
        SessionMeOut.model_validate(without)


def test_a_record_in_a_currency_of_its_own_is_marked_by_the_read_that_answers_it():
    """The mark base/assistant.py ``CURRENCY`` reads on a datum that names a cart or a price list (base.E011)."""
    assert in_currency_of("pricing.price_list.get", by="price_list") == {
        "currency": {"read": "pricing.price_list.get", "by": "price_list", "code": "currency"}
    }
    assert in_currency_of("demo.item.ledger", code="code") == {"currency": {"read": "demo.item.ledger", "by": "id", "code": "code"}}


# ── The read of the names an app's card shows (``sale.record.get``, ``service.record.get``) ───────────────────────────


class OneOfTwo(pydantic.BaseModel):
    """An input naming one record of two kinds, as an app's read of the names its card shows takes it."""

    sale_id: str | None = None
    refund_id: str | None = None

    @pydantic.model_validator(mode="after")
    def _one(self):
        return exactly_one(self, "Say one record, by its id.")


@pytest.mark.parametrize("data", [{"sale_id": "a"}, {"refund_id": "b"}])
def test_an_input_naming_exactly_one_record_is_taken(data):
    assert OneOfTwo.model_validate(data).model_dump(exclude_none=True) == data


@pytest.mark.parametrize("data", [{}, {"sale_id": "a", "refund_id": "b"}])
def test_an_input_naming_none_or_several_records_is_refused_in_the_apps_own_words(data):
    with pytest.raises(pydantic.ValidationError) as caught:
        OneOfTwo.model_validate(data)
    assert "Say one record, by its id." in str(caught.value)


def test_the_name_of_a_record_is_a_text():
    assert RecordNameOut(name="Refund of sale 20261014-0007").name == "Refund of sale 20261014-0007"
    with pytest.raises(pydantic.ValidationError):
        RecordNameOut.model_validate({})
