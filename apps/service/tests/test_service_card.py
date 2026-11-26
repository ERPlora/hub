"""The assistant's card of a new service says what it is created with: its name, its price and how long it lasts come
first (a card's line shows three data), and a duration the person did not say is the settings' one the service takes."""

from live.meta import all_live_app_configs, permissions_for_role
from live.operations import get

from apps.service.models.settings import ServiceSettings
from base import assistant

from .conftest import HUB_DB, ctx_for

pytestmark = HUB_DB

CREATE = "service.service.create"
CUT = {"name": "Corte y peinado", "tax_category_key": "service.generic", "category": "Cortes", "price": 2500}


def fields(arguments: dict, ctx=None, language: str = "es") -> list[dict]:
    return assistant.cards.card(get(CREATE), arguments, language, ctx or ctx_for())["fields"]


def test_its_name_price_and_duration_come_first():
    shown = fields({**CUT, "duration_minutes": 45})
    assert [(field["name"], field["value"]) for field in shown[:3]] == [
        ("name", "Corte y peinado"),
        ("price", 2500),
        ("duration_minutes", 45),
    ]
    assert shown[1]["kind"] == "money"


def test_a_duration_not_said_is_the_settings_one_as_if_said():
    ServiceSettings.objects.create(default_duration=40)
    for language in ("es", "en"):
        shown = fields(CUT, language=language)
        assert (shown[2]["name"], shown[2]["value"]) == ("duration_minutes", 40)
        assert shown[:3] == fields({**CUT, "duration_minutes": 40}, language=language)[:3]


def test_without_saved_settings_the_duration_is_the_factory_one():
    factory = ServiceSettings().default_duration
    assert fields(CUT)[2] == fields({**CUT, "duration_minutes": factory})[2]
    assert fields(CUT)[2]["value"] == factory


def test_who_cannot_read_the_settings_sees_no_duration_made_up():
    blind = ctx_for(permissions=permissions_for_role(all_live_app_configs(), "hub_admin") - {"service.view_service"})
    names = [field["name"] for field in fields(CUT, blind)]
    assert names[:2] == ["name", "price"]
    assert "duration_minutes" not in names
