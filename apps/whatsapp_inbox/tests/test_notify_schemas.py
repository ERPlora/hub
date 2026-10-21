"""The input of ``whatsapp_inbox.message.notify`` (FLOW-F31): a number, and a text, a template or both."""

import pydantic
import pytest

from apps.whatsapp_inbox.notify_schemas import NotifyIn


def test_it_takes_the_number_with_a_text_a_template_or_both():
    both = NotifyIn.model_validate(
        {"phone": " +34600111222 ", "text": " Hi ", "template": {"name": "recordatorio", "variables": ["Ana"]}}
    )
    assert (both.phone, both.text, both.template.name, both.client_message_id) == ("+34600111222", "Hi", "recordatorio", None)
    assert NotifyIn.model_validate({"phone": "+34600111222", "text": "Hi"}).template is None
    assert NotifyIn.model_validate({"phone": "+34600111222", "template": {"name": "recordatorio"}}).text == ""


@pytest.mark.parametrize("payload", [{"phone": "+34600111222"}, {"phone": "+34600111222", "text": "  "}])
def test_without_a_text_or_a_template_it_says_nothing(payload):
    with pytest.raises(pydantic.ValidationError) as invalid:
        NotifyIn.model_validate(payload)
    assert [error["loc"] for error in invalid.value.errors()] == [("text",)]


def test_a_text_is_whatsapp_s_longest():
    with pytest.raises(pydantic.ValidationError):
        NotifyIn.model_validate({"phone": "+34600111222", "text": "x" * 4097})
