"""``base.business.get``: Settings › Business, and what the old ``/api/hub/context`` gave.

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
from live.context import OperationContext
from live.errors import NotFound, PermissionDenied
from live.live_registry import live_registry
from live.operations import get

from apps.sale.tests.test_business_currency import platform
from base.events import HUB_REGISTERED
from base.models import Hub
from base.schemas import BusinessIn, BusinessOut
from base.tenancy.context import use_hub
from base.tenancy.tests.business import A, B, HOST, HUB_DB, in_business_a

__all__ = ["in_business_a", "platform"]

pytestmark = HUB_DB

HOME = "base.view_home"


def business(scope=A, language="es", permissions=(HOME,)):
    ctx = OperationContext(scope=scope, actor="ana", permissions=frozenset(permissions), language=language)
    return get("base.business.get")(ctx, BusinessIn()).model_dump(mode="json")


@pytest.fixture
def hubs(hub_a, hub_b):
    """The rows of A and B, as the SaaS registered each business."""
    Hub.objects.filter(pk=hub_a.pk).update(
        name="Peluquería Ana", country="ES", timezone="Atlantic/Canary", language="es"
    )
    Hub.objects.filter(pk=hub_b.pk).update(name="Bar Varsovia", country="PL", timezone="Europe/Warsaw", language="en")
    return hub_a, hub_b


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
    on_a = business(A)
    with use_hub(b):
        on_b = business(B)
    assert (on_a["name"], on_a["currency"], on_a["timezone"]) == ("Peluquería Ana", "EUR", "Atlantic/Canary")
    assert (on_b["name"], on_b["currency"], on_b["currency_label"], on_b["language_name"]) == (
        "Bar Varsovia",
        "PLN",
        "PLN · Esloti polaco",
        "Inglés",
    )
    assert str(b.id) in on_b["settings_url"] and str(a.id) not in on_b["settings_url"]


def test_a_change_the_saas_pushed_is_what_it_reads_next(hubs):
    Hub.objects.filter(slug=A.key).update(language="en", timezone="Europe/Madrid", name="Ana Estilistas")
    after = business()
    assert (after["name"], after["language"], after["language_name"], after["timezone"]) == (
        "Ana Estilistas",
        "en",
        "Inglés",
        "Europe/Madrid",
    )


def test_a_demo_has_no_business_on_erplora_com_to_change_it(settings, hub_b):
    settings.LANGUAGE_CODE, settings.TIME_ZONE = "en", "Europe/Madrid"
    Hub.objects.filter(pk=hub_b.pk).update(is_demo=True)
    with use_hub(hub_b):
        demo = business(B)
    assert (demo["demo"], demo["settings_url"], demo["name"]) == (True, "", "")
    # No country: euros; the deployment's zone and language until the SaaS says otherwise.
    assert (demo["country"], demo["currency"], demo["timezone"], demo["language"]) == ("", "EUR", "Europe/Madrid", "en")


def test_erplora_s_own_hub_answers_erplora_s_business_from_its_issuer(settings, platform):
    """ERPlora's own hub has a registry row with nothing of its own (``create_platform_hub``), yet its business is
    ERPlora itself, the issuer of its invoices: its legal name and country, that country's currency, and the
    deployment's zone and language. Nothing of it is changed on erplora.com, so no address to change it."""
    settings.LANGUAGE_CODE, settings.TIME_ZONE = "en", "Europe/Madrid"
    settings.PLATFORM_ISSUER_LEGAL_NAME, settings.PLATFORM_ISSUER_COUNTRY = "ERPLORA CLOUD SL", "ES"
    assert (platform.name, platform.country) == ("", "")
    with use_hub(platform):
        answer = business(B)
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


def test_erplora_s_own_hub_follows_its_issuer_s_country_and_not_a_registry_row(settings, platform):
    """Its currency is always the one its invoices and its apps charge in (``business_currency``): the issuer's
    country's, whatever its registry row says."""
    settings.PLATFORM_ISSUER_LEGAL_NAME, settings.PLATFORM_ISSUER_COUNTRY = "ERPlora Ltd", "GB"
    with use_hub(platform):
        first = business(B, language="en")
        Hub.objects.filter(pk=platform.pk).update(name="Another name", country="JP")
        assert business(B, language="en") == first
    assert (first["name"], first["country"], first["country_name"]) == ("ERPlora Ltd", "GB", "United Kingdom")
    assert (first["currency"], first["currency_label"], first["currency_decimals"]) == ("GBP", "GBP · British Pound", 2)


def test_the_decimals_are_the_currency_s_own_never_a_fixed_two(hubs, settings):
    """What every app counts with (``currency_decimals``) is the currency's own (CLDR), on a business's hub and on
    ERPlora's: the yen has none, the Kuwaiti dinar three."""
    _, b = hubs
    Hub.objects.filter(slug=A.key).update(country="JP")
    Hub.objects.filter(slug=B.key).update(country="KW")
    assert (business(A)["currency"], business(A)["currency_decimals"]) == ("JPY", 0)
    with use_hub(b):
        assert (business(B)["currency"], business(B)["currency_decimals"]) == ("KWD", 3)
        settings.PLATFORM_HUB_SLUG, settings.PLATFORM_ISSUER_COUNTRY = B.key, "JP"
        assert (business(B)["currency"], business(B)["currency_decimals"]) == ("JPY", 0)


def test_a_scope_without_a_business_is_not_found_and_says_so_in_the_person_s_language():
    Hub.objects.filter(slug=A.key).update(slug="moved")  # no registry row holds A's address any more
    with translation.override("es"), pytest.raises(NotFound) as refused:
        business(A)
    assert refused.value.message == "No hay ningún negocio aquí."


def test_without_the_home_s_permission_it_is_refused(hubs):
    with pytest.raises(PermissionDenied):
        business(permissions=())


def test_its_route(client, make_user, hubs):
    from base.api import router

    [route] = router.path_operations["/business"].operations
    assert (route.methods, route.operation_id) == (["GET"], "base.business.get")
    assert resolve("/api/business").url_name
    client.force_login(make_user("eva", host=A.key, role="hub_employee"))
    response = client.get("/api/business", HTTP_HOST=HOST, HTTP_ACCEPT_LANGUAGE="en")
    assert response.status_code == 200
    assert (response.json()["name"], response.json()["country_name"]) == ("Peluquería Ana", "Spain")
    assert client.get("/api/business", HTTP_HOST=f"{B.key}.localhost").status_code in (401, 403)
