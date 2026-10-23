"""``base.app.list``: the Apps screen (BASE-G67…G74; PLAN §20.4.1, PLAN-HUB §1a «GET /api/modules»).

Every module of the deployment the scope shows (``home.shown_modules``), from its ``LiveAppConfig`` in this process
(never the SaaS): name, icon, category, one line, whether it is paid and where its right comes from
(``base.entitlement``), its state (``on``, or ``blocked`` without the right), the first screen this person may open,
what it needs and what needs it, and erplora.com's Store of this business's modules. Re-run when the SaaS's photo
changes (``base.hub.state_applied``): a module bought there turns up here without reloading.
"""

import pytest
from django.apps import apps
from live.context import OperationContext, Scope
from live.live_registry import live_registry
from live.meta import module_configs
from live.operations import get

from base.events import HUB_STATE_APPLIED
from base.models import Hub
from base.schemas import AppListIn, AppListOut

pytestmark = pytest.mark.django_db

A = Scope("host", "a")
B = Scope("host", "b")
HOME = "base.view_home"


def app_list(*permissions, scope=A, language="en"):
    ctx = OperationContext(scope=scope, actor="ana", permissions=frozenset({HOME, *permissions}), language=language)
    return get("base.app.list")(ctx, AppListIn()).model_dump(mode="json")


def by_id(document):
    return {app["id"]: app for app in document["apps"]}


def keep(slug, state):
    Hub.objects.update_or_create(slug=slug, defaults={"status": "ready", "state": state, "state_version": 1})


@pytest.fixture
def paid_demo(monkeypatch):
    """The reference app, sold: no module of the deployment is paid yet, so a test makes one."""
    monkeypatch.setattr(apps.get_app_config("demo"), "premium", True)


def test_declaration():
    op = get("base.app.list")
    assert (op.kind, op.permission, op.input, op.output) == ("query", HOME, AppListIn, AppListOut)
    assert "base.app.list" in live_registry.affected([HUB_STATE_APPLIED])


def test_every_module_of_the_deployment_from_its_own_config():
    document = app_list()
    shown = [config for config in module_configs()]
    assert [app["id"] for app in document["apps"]] == [config.label for config in shown]
    assert "base" not in by_id(document)  # the platform is always there and never listed
    demo = by_id(document)["demo"]
    config = apps.get_app_config("demo")
    assert {key: demo[key] for key in ("name", "icon", "category", "summary", "premium", "right", "state")} == {
        "name": str(config.verbose_name),
        "icon": config.icon,
        "category": config.category,
        "summary": str(config.summary),
        "premium": False,
        "right": "free",
        "state": "on",
    }


def test_names_and_categories_in_the_language_of_who_asks():
    tax_es = by_id(app_list(language="es"))["tax"]
    tax_en = by_id(app_list(language="en"))["tax"]
    assert (tax_en["name"], tax_es["name"]) == ("Taxes", "Impuestos")
    assert (tax_en["category_label"], tax_es["category_label"]) == (
        "Sales, payments and tax",
        "Venta, cobro y fiscalidad",
    )


def test_open_leads_to_the_first_screen_of_the_app_for_who_may_see_it():
    """BASE-G68: «Open» only where the person has a screen to open; no permission of the app, no «Open»."""
    with_permission = by_id(app_list("demo.view"))["demo"]
    without = by_id(app_list())["demo"]
    assert (with_permission["path"], without["path"]) == ("/demo/items", None)


def test_what_an_app_needs_and_what_needs_it():
    """BASE-G73: what comes along with an app (its ``requires``, transitively) and what an app is needed by."""
    document = by_id(app_list())
    for config in module_configs():
        assert set(document[config.label]["requires"]) >= set(config.requires)
    invoice = apps.get_app_config("invoice")
    for required in invoice.requires:
        assert "invoice" in document[required]["required_by"]


def test_the_store_of_this_business(settings):
    settings.SAAS_URL = "https://erplora.com"
    hub = Hub.objects.get(slug="a")
    assert app_list()["store_url"] == f"https://erplora.com/store/modules?business={hub.id}"


def test_a_paid_app_without_its_right_is_blocked_and_says_so(paid_demo):
    """BASE-G74: bought on erplora.com; until then its state is ``blocked`` and it has no «Open»."""
    keep("a", {"modules": []})
    demo = by_id(app_list("demo.view"))["demo"]
    assert {key: demo[key] for key in ("premium", "right", "state", "path")} == {
        "premium": True,
        "right": "missing",
        "state": "blocked",
        "path": None,
    }


def test_a_paid_app_says_where_its_right_comes_from(paid_demo):
    """BASE-G70: «Included in your plan» or «Subscribed», from the SaaS's photo."""
    keep("a", {"modules": [{"id": "demo", "source": "plan"}]})
    keep("b", {"modules": [{"id": "demo", "source": "purchase"}]})
    in_a, in_b = by_id(app_list("demo.view"))["demo"], by_id(app_list("demo.view", scope=B))["demo"]
    assert (in_a["right"], in_a["state"], in_a["path"]) == ("plan", "on", "/demo/items")
    assert (in_b["right"], in_b["state"]) == ("purchase", "on")


def test_each_business_reads_its_own_photo(paid_demo):
    keep("a", {"modules": [{"id": "demo", "source": "purchase"}]})
    keep("b", {"modules": []})
    assert by_id(app_list(scope=A))["demo"]["state"] == "on"
    assert by_id(app_list(scope=B))["demo"]["state"] == "blocked"


def test_a_module_out_of_the_store_stays_out_on_a_customers_hub(settings):
    settings.SHOW_UNLISTED_MODULES = False
    assert "demo" not in by_id(app_list())


def test_an_anonymous_visitor_or_a_stranger_gets_no_list(client):
    response = client.get("/api/apps", HTTP_HOST="a.localhost:8000")
    assert response.status_code in (401, 403)


def test_over_http(client, make_user):
    from django.urls import resolve

    from base.api import router

    [route] = router.path_operations["/apps"].operations
    assert (route.methods, route.operation_id) == (["GET"], "base.app.list")
    assert resolve("/api/apps").url_name
    client.force_login(make_user("ana", host="a", role="hub_employee"))
    response = client.get("/api/apps", HTTP_HOST="a.localhost:8000", HTTP_ACCEPT_LANGUAGE="es")
    assert response.status_code == 200
    assert by_id(response.json())["tax"]["name"] == "Impuestos"
