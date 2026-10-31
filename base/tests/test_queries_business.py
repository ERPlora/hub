"""``base.business.get``: Settings › Business (APP-BASE-6; BASE-G97, G98, G99, and the old ``/api/hub/context``, G43).

The business as the SaaS registered it (``PUT /internal/hubs/{id}``: its name, country, time zone and language), with
the currency its country pays in, each named in the person's language, and where on erplora.com an owner or an
administrator changes them (the Hub never writes them: the SaaS owns them and pushes them). Everyone of the hub reads
it; a demo has no business on erplora.com, so no address to change it. It re-runs when the SaaS registers the business
again (``base.hub.registered``), so a change made on erplora.com shows without reloading. Each hub reads its own row.
"""

import pytest
from django.urls import resolve
from django.utils import translation
from live.assistant import description
from live.context import OperationContext, Scope
from live.errors import NotFound, PermissionDenied
from live.live_registry import live_registry
from live.operations import get

from base.events import HUB_REGISTERED
from base.models import Hub
from base.schemas import BusinessIn, BusinessOut

pytestmark = pytest.mark.django_db

A = Scope("host", "a")
B = Scope("host", "b")
HOME = "base.view_home"


def business(scope=A, language="es", permissions=(HOME,)):
    ctx = OperationContext(scope=scope, actor="ana", permissions=frozenset(permissions), language=language)
    return get("base.business.get")(ctx, BusinessIn()).model_dump(mode="json")


@pytest.fixture
def hubs():
    """The rows of ``a`` and ``b`` (the local hubs, already in the registry), as the SaaS registered each business."""
    a, _ = Hub.objects.update_or_create(
        slug="a",
        defaults={
            "status": "ready",
            "name": "Peluquería Ana",
            "country": "ES",
            "timezone": "Atlantic/Canary",
            "language": "es",
        },
    )
    b, _ = Hub.objects.update_or_create(
        slug="b",
        defaults={
            "status": "ready",
            "name": "Bar Varsovia",
            "country": "PL",
            "timezone": "Europe/Warsaw",
            "language": "en",
        },
    )
    return a, b


def test_declaration():
    op = get("base.business.get")
    assert (op.kind, op.permission, op.input, op.output) == ("query", HOME, BusinessIn, BusinessOut)
    assert description(op)
    assert "base.business.get" in live_registry.affected([HUB_REGISTERED])


def test_the_business_as_the_saas_registered_it_named_in_the_person_s_language(hubs, settings):
    a, _ = hubs
    settings.SAAS_URL = "https://erplora.com"
    assert business() == {
        "name": "Peluquería Ana",
        "country": "ES",
        "country_name": "España",
        "timezone": "Atlantic/Canary",
        "language": "es",
        "language_name": "Español",
        "currency": "EUR",
        "currency_label": "EUR · Euro",
        "currency_decimals": 2,
        "demo": False,
        "settings_url": f"https://erplora.com/dashboard/businesses/{a.id}/settings",
    }
    in_english = business(language="en")
    assert (in_english["country_name"], in_english["language_name"]) == ("Spain", "Spanish")


def test_each_hub_reads_its_own_business_never_another_s(hubs):
    a, b = hubs
    on_a, on_b = business(A), business(B)
    assert (on_a["name"], on_a["currency"], on_a["timezone"]) == ("Peluquería Ana", "EUR", "Atlantic/Canary")
    assert (on_b["name"], on_b["currency"], on_b["currency_label"], on_b["language_name"]) == (
        "Bar Varsovia",
        "PLN",
        "PLN · Esloti polaco",
        "Inglés",
    )
    assert str(b.id) in on_b["settings_url"] and str(a.id) not in on_b["settings_url"]


def test_a_change_the_saas_pushed_is_what_it_reads_next(hubs):
    Hub.objects.filter(slug="a").update(language="en", timezone="Europe/Madrid", name="Ana Estilistas")
    after = business()
    assert (after["name"], after["language"], after["language_name"], after["timezone"]) == (
        "Ana Estilistas",
        "en",
        "Inglés",
        "Europe/Madrid",
    )


def test_a_demo_has_no_business_on_erplora_com_to_change_it(settings):
    settings.LANGUAGE_CODE, settings.TIME_ZONE = "en", "Europe/Madrid"
    Hub.objects.create(slug="demo-x1y2", status="ready", is_demo=True)
    demo = business(Scope("host", "demo-x1y2"))
    assert (demo["demo"], demo["settings_url"], demo["name"]) == (True, "", "")
    # No country: euros; the deployment's zone and language until the SaaS says otherwise.
    assert (demo["country"], demo["currency"], demo["timezone"], demo["language"]) == ("", "EUR", "Europe/Madrid", "en")


ERPLORA = Scope("host", "erplora")


def test_erplora_s_own_hub_answers_erplora_s_business_from_its_issuer(settings):
    """Phase 1: ERPlora's own hub has no registry row (``create_platform_hub``), yet its business is ERPlora itself,
    the issuer of its invoices: its legal name and country, that country's currency, and the deployment's zone and
    language. Nothing of it is changed on erplora.com, so no address to change it."""
    settings.LANGUAGE_CODE, settings.TIME_ZONE = "en", "Europe/Madrid"
    settings.PLATFORM_ISSUER_LEGAL_NAME, settings.PLATFORM_ISSUER_COUNTRY = "ERPLORA CLOUD SL", "ES"
    assert not Hub.objects.filter(slug="erplora").exists()
    answer = business(ERPLORA)
    assert answer == BusinessOut.model_validate(answer).model_dump(mode="json")
    assert answer == {
        "name": "ERPLORA CLOUD SL",
        "country": "ES",
        "country_name": "España",
        "timezone": "Europe/Madrid",
        "language": "en",
        "language_name": "Inglés",
        "currency": "EUR",
        "currency_label": "EUR · Euro",
        "currency_decimals": 2,
        "demo": False,
        "settings_url": "",
    }


def test_erplora_s_own_hub_follows_its_issuer_s_country_and_not_a_registry_row(settings):
    """Its currency is always the one its invoices and its apps charge in (``business_currency``): the issuer's
    country's, even once phase 2 gives it a registry row."""
    settings.PLATFORM_ISSUER_LEGAL_NAME, settings.PLATFORM_ISSUER_COUNTRY = "ERPlora Ltd", "GB"
    first = business(ERPLORA, language="en")
    Hub.objects.create(slug="erplora", status="ready", name="Another name", country="JP")
    assert business(ERPLORA, language="en") == first
    assert (first["name"], first["country"], first["country_name"]) == ("ERPlora Ltd", "GB", "United Kingdom")
    assert (first["currency"], first["currency_label"], first["currency_decimals"]) == ("GBP", "GBP · British Pound", 2)


def test_the_decimals_are_the_currency_s_own_never_a_fixed_two(hubs, settings):
    """What every app counts with (``currency_decimals``) is the currency's own (CLDR), on a business's hub and on
    ERPlora's: the yen has none, the Kuwaiti dinar three."""
    Hub.objects.filter(slug="a").update(country="JP")
    Hub.objects.filter(slug="b").update(country="KW")
    assert (business(A)["currency"], business(A)["currency_decimals"]) == ("JPY", 0)
    assert (business(B)["currency"], business(B)["currency_decimals"]) == ("KWD", 3)
    settings.PLATFORM_ISSUER_COUNTRY = "JP"
    assert (business(ERPLORA)["currency"], business(ERPLORA)["currency_decimals"]) == ("JPY", 0)


def test_a_scope_without_a_business_is_not_found_and_says_so_in_the_person_s_language():
    with translation.override("es"), pytest.raises(NotFound) as refused:
        business(Scope("host", "nobody"))
    assert refused.value.message == "No hay ningún negocio aquí."


def test_without_the_home_s_permission_it_is_refused(hubs):
    with pytest.raises(PermissionDenied):
        business(permissions=())


def test_its_route(client, make_user, hubs):
    from base.api import router

    [route] = router.path_operations["/business"].operations
    assert (route.methods, route.operation_id) == (["GET"], "base.business.get")
    assert resolve("/api/business").url_name
    client.force_login(make_user("eva", host="a", role="hub_employee"))
    response = client.get("/api/business", HTTP_HOST="a.localhost:8000", HTTP_ACCEPT_LANGUAGE="en")
    assert response.status_code == 200
    assert (response.json()["name"], response.json()["country_name"]) == ("Peluquería Ana", "Spain")
    assert client.get("/api/business", HTTP_HOST="b.localhost:8000").status_code in (401, 403)
