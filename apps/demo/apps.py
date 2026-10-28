"""The demo app: the reference every app of hub-next copies (plan §4.5)."""

from django.utils.translation import gettext_lazy as _
from live.meta import BellCounter, Category, LiveAppConfig, Nav, SetupCheck, SetupStep, Widget

from apps.demo.events import ITEM_CREATED, ITEM_DELETED, ITEM_UPDATED


class DemoConfig(LiveAppConfig):
    name = "apps.demo"
    label = "demo"
    kind = "app"
    verbose_name = _("Demo")
    icon = "ion:flask-outline"
    category = Category.ORGANIZATION
    premium = False
    # The public store's texts (round 16, PLAN §21), which register_apps writes to shared.app.
    summary = _("Items with lines that show up on every tablet at once: the platform's reference app.")
    description = _(
        "Demo keeps items with a name, a status and a note, each with its own list of lines. It solves "
        "no business problem: it proves on the tablet that the platform works end to end, with every "
        "change shown live on the other screens, lines added instantly and permissions enforced. It is "
        "the app every other app is copied from."
    )
    verticals = []
    # The technical reference, not sold (its WORKBOOK): registered, but kept out of the public store.
    listed = False
    default_auto_field = "django.db.models.BigAutoField"
    permissions = ["demo.view", "demo.manage"]
    # Keys are the customer roles as the SaaS sends them (``hub_`` prefix included).
    role_permissions = {
        "hub_owner": ["demo.*"],
        "hub_admin": ["demo.*"],
        "hub_manager": ["demo.*"],
        "hub_employee": ["demo.view"],
    }
    navigation = [Nav(id="demo", label=_("Demo"), icon="ion:flask-outline", path="/demo/items")]
    # What a manager approves on the spot with their PIN or badge (BASE-F84, base.approvals), the example every module
    # copies: the employee, who only views, adds a line with a manager's approval, which says what it approves with the
    # figures of that very line (``approval_figures``: holes {field}, {field, percent} or {field, money} of the
    # command's input, checked at start by base.E008).
    approvals = {"demo.item.add_line": _("Add a line to an item")}
    approval_figures = {"demo.item.add_line": [_("Add a line: {qty} × {text}")]}
    # The Home's hooks (PLAN-HUB round 2026-10-21), the example every module copies: a step of «Finish setting up
    # your business», a panel of the dashboard and a counter of the bell, each on a query of queries.py. Out of the
    # store (listed = False), so base shows them only where SHOW_UNLISTED_MODULES is on or in a demo's hub: never to a
    # customer.
    setup = [
        SetupStep(
            key="first_item",
            operation="demo.item.stats",
            configured_when=[SetupCheck(field="total", truthy=True)],
            title=_("Create your first item"),
            description=_("Add an item and watch it appear on every screen of the business at once."),
            icon="ion:flask-outline",
            route="/demo/items/new",
            permission="demo.manage",
            required=False,
            refresh_on=[ITEM_CREATED, ITEM_DELETED],
        )
    ]
    widgets = [
        Widget(
            key="open_items",
            title=_("Open items"),
            icon="ion:flask-outline",
            size="sm",
            permission="demo.manage",
            default=True,
            refresh_on=[ITEM_CREATED, ITEM_UPDATED, ITEM_DELETED],
            kind="kpi",
            operation="demo.item.stats",
            map={"value": "open"},
        )
    ]
    bell = [
        BellCounter(
            key="open_items",
            operation="demo.item.open_count",
            route="/demo/items",
            label=_("Open demo items"),
            icon="ion:flask-outline",
            permission="demo.view",
            refresh_on=[ITEM_CREATED, ITEM_UPDATED, ITEM_DELETED],
        )
    ]
