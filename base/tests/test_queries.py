"""base.session.me: who is in front of the SPA, what they may do and the menu they see."""

from dataclasses import dataclass, field

import pytest
from django.utils.translation import gettext_lazy
from live.context import OperationContext, Scope
from live.meta import Nav, module_configs
from live.operations import get

from base.schemas import SessionMeIn, SessionMeOut

pytestmark = pytest.mark.django_db

A = Scope("host", "a")
DEMO_MENU = {
    "id": "demo",
    "label": "Demo",
    "items": [{"path": "/demo/items", "label": "Demo", "icon": "ion:flask-outline"}],
}


def session_me(actor=None, permissions=(), language="en"):
    ctx = OperationContext(scope=A, actor=actor, permissions=frozenset(permissions), language=language)
    return get("base.session.me")(ctx, SessionMeIn()).model_dump(mode="json")


def test_declaration():
    op = get("base.session.me")
    assert (op.kind, op.permission, op.input, op.output) == ("query", None, SessionMeIn, SessionMeOut)


def test_anonymous():
    assert session_me(language="es") == {
        "user": None,
        "scope": {"kind": "host", "key": "a"},
        "permissions": [],
        "menu": [],
        "apps": [],
        "language": "es",
        "demo": None,
    }


def test_superuser_sees_every_app(superuser):
    me = session_me(superuser, {"*"})
    modules = module_configs()
    assert me["user"] == {"id": str(superuser.pk), "label": "root"}
    assert me["permissions"] == ["*"]
    # Every installed module: a menu group for each one with navigation, an app entry for all.
    assert DEMO_MENU in me["menu"]
    assert [group["id"] for group in me["menu"]] == [config.label for config in modules if config.navigation]
    assert me["apps"] == [{"label": config.label, "state": "on"} for config in modules]


def test_employee_sees_demo(make_user):
    user = make_user("ana", first_name="Ana", last_name="García")
    me = session_me(user, {"demo.view"})
    assert me["user"] == {"id": str(user.pk), "label": "Ana García"}
    assert me["permissions"] == ["demo.view"]
    assert me["menu"] == [DEMO_MENU]


def test_user_without_role_sees_no_app(make_user):
    me = session_me(make_user())
    assert (me["menu"], me["apps"], me["permissions"]) == ([], [], [])


@dataclass
class FakeApp:
    """Stands in for a LiveAppConfig: only what the menu reads."""

    label: str
    verbose_name: str
    permissions: list[str]
    navigation: list[Nav] = field(default_factory=list)
    kind: str = "app"
    listed: bool = True


@pytest.fixture
def two_apps(monkeypatch):
    """Two modules with a menu, one without, and a platform app (which never shows)."""
    apps = [
        FakeApp("demo", "Demo", ["demo.view", "demo.manage"], [Nav("demo", "Demo", "ion:flask-outline", "/demo/items")]),
        FakeApp("stock", gettext_lazy("January"), ["stock.view", "stock.count"], [
            Nav("stock", gettext_lazy("January"), "mdi:package-variant", "/stock"),
            Nav("stock-count", "Count", "mdi:counter", "/stock/count"),
        ]),
        FakeApp("reports", "Reports", ["reports.view"]),
        FakeApp("platform", "Platform", ["platform.view"], [Nav("platform", "Platform", "ion:home", "/platform")],
                kind="platform"),
    ]
    # Patched at the source, so the stand-ins go through the real module_configs() filter.
    monkeypatch.setattr("live.meta.all_live_app_configs", lambda: apps)
    return apps


def test_menu_lists_only_permitted_apps(make_user, two_apps):
    me = session_me(make_user(), {"demo.view"})
    assert [group["id"] for group in me["menu"]] == ["demo"]
    assert me["apps"] == [{"label": "demo", "state": "on"}]


def test_any_permission_of_an_app_makes_it_visible(make_user, two_apps):
    me = session_me(make_user(), {"stock.count"})
    assert [group["id"] for group in me["menu"]] == ["stock"]
    assert [item["path"] for item in me["menu"][0]["items"]] == ["/stock", "/stock/count"]


def test_app_without_navigation_is_listed_but_has_no_menu(make_user, two_apps):
    me = session_me(make_user(), {"reports.view"})
    assert me["menu"] == []
    assert me["apps"] == [{"label": "reports", "state": "on"}]


def test_labels_are_translated_to_the_context_language(make_user, two_apps):
    me = session_me(make_user(), {"stock.view"}, language="es")
    assert me["menu"][0]["label"] == "enero"
    assert me["menu"][0]["items"][0]["label"] == "enero"


def test_platform_apps_never_appear_even_with_a_menu_and_every_permission(make_user, two_apps):
    me = session_me(make_user(), {"*", "platform.view"})
    assert "platform" not in [group["id"] for group in me["menu"]]
    assert "platform" not in [app["label"] for app in me["apps"]]


def test_superuser_does_not_see_base_among_its_apps(superuser):
    me = session_me(superuser, {"*"})
    assert "base" not in [app["label"] for app in me["apps"]]
    assert "base" not in [group["id"] for group in me["menu"]]


def test_system_actor(two_apps):
    me = session_me("system", {"*"})
    assert me["user"] == {"id": "system", "label": "system"}
    assert [app["label"] for app in me["apps"]] == ["demo", "stock", "reports"]


def test_on_a_demo_it_says_when_the_demo_ends():
    # plan 2026-10-17, §1.6: the shell's banner reads it.
    from django.utils import timezone

    from base.models import Hub

    demo = Hub.objects.create(slug="demo-0000beef", is_demo=True, status="ready", expires_at=timezone.now())
    ctx = OperationContext(scope=Scope("host", demo.slug), actor=None, permissions=frozenset(), language="en")
    me = get("base.session.me")(ctx, SessionMeIn())
    assert me.demo is not None and me.demo.expires_at == demo.expires_at


def test_a_module_out_of_the_store_stays_out_of_a_customers_menu_and_apps(make_user, settings):
    """The reference app (``demo``, ``listed = False``) is never offered to a customer: not in the menu, not in
    «My apps», whatever the person may do (prod and pre run with ``SHOW_UNLISTED_MODULES`` off)."""
    settings.SHOW_UNLISTED_MODULES = False
    me = session_me(make_user(), {"demo.view", "demo.manage"})
    assert "demo" not in [group["id"] for group in me["menu"]]
    assert "demo" not in [app["label"] for app in me["apps"]]


def test_a_module_out_of_the_store_shows_on_a_demos_hub_and_with_the_setting_on(make_user, settings):
    """A demo's hub lists it whatever the setting says; development, the tests and the e2e list it everywhere."""
    from django.utils import timezone

    from base.models import Hub

    settings.SHOW_UNLISTED_MODULES = False
    demo = Hub.objects.create(slug="demo-0000beef", is_demo=True, status="ready", expires_at=timezone.now())
    on_demo = OperationContext(
        scope=Scope("host", demo.slug), actor=make_user(), permissions=frozenset({"demo.view"}), language="en"
    )
    me = get("base.session.me")(on_demo, SessionMeIn()).model_dump(mode="json")
    assert (me["menu"], me["apps"]) == ([DEMO_MENU], [{"label": "demo", "state": "on"}])

    settings.SHOW_UNLISTED_MODULES = True
    assert session_me(make_user("bea"), {"demo.view"})["menu"] == [DEMO_MENU]


@pytest.mark.parametrize("slug", ["a", "acme"])
def test_on_a_business_or_a_slug_without_a_row_there_is_no_demo(slug):
    assert session_me().get("demo", "missing") is None
    ctx = OperationContext(scope=Scope("host", slug), actor=None, permissions=frozenset(), language="en")
    assert get("base.session.me")(ctx, SessionMeIn()).demo is None
