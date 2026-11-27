"""A schedule the assistant creates without a name is named as the Schedules screen names it, in the person's
language: the write runs in the language of the request that says yes to its card."""

import json

from apps.staff.models import Schedule
from base.tenancy.tests.business import A
from base.tests.fake_gateway import gateway, signed
from base.tests.test_api_assistant import frames, post

from .conftest import HUB_DB, in_business_a, make_member

__all__ = ["gateway", "in_business_a", "signed"]

pytestmark = HUB_DB


def test_a_schedule_the_assistant_creates_without_a_name_is_named_in_the_persons_language(client, make_user, gateway, settings):
    member = make_member()
    client.force_login(make_user("olga", host=A.key, role="hub_admin"))
    client.cookies[settings.LANGUAGE_COOKIE_NAME] = "es"
    arguments = json.dumps({"member_id": str(member.id), "days": [{"weekday": 1, "start_time": "10:00", "end_time": "19:00"}]})
    call = {"call_id": "c1", "name": "staff__schedule__create", "arguments": arguments}
    function = {"name": call["name"], "arguments": arguments}
    asked = {"role": "assistant", "content": "", "tool_calls": [{"id": "c1", "type": "function", "function": function}]}
    body = {"messages": [{"role": "user", "content": "Ana trabaja los martes de 10 a 7"}, asked], "pending": [call], "continuation": "tok"}

    card, waiting = frames(post(client, "/assistant/turn", body))
    assert "name" not in [field["name"] for field in card["card"]["fields"]]

    gateway.turn({"type": "text_delta", "text": "Hecho."}, {"type": "response", "output": [], "usage": {}, "continuation": None})
    yes = {**body, "pending": waiting["pending"], "decision": {"call_id": "c1", "accepted": True}}
    ran = frames(post(client, "/assistant/turn", yes))[0]
    assert (ran["name"], ran["outcome"]) == ("staff.schedule.create", "ok")
    assert list(Schedule.objects.filter(member=member).values_list("name", flat=True)) == ["Horario habitual"]
