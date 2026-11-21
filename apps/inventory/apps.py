"""The inventory app: the catalog of what is sold with stock, its categories and the stock ledger."""

from django.utils.translation import gettext_lazy as _
from live.meta import Category, Help, LiveAppConfig, Nav, SetupCheck, SetupStep, Widget

from apps.inventory.events import FIGURE_EVENTS, PRODUCT_EVENTS
from base.allergens import ALLERGENS

VIEW = "inventory.view_product"
#: How a quantity of goods is said in a unit: what the assistant reads as goods and as their stock.
QUANTITIES_OF_GOODS = (
    "kilos de", "kg de", "gramos de", "litros de", "cajas de", "sacos de",
    "kilos of", "kg of", "grams of", "litres of", "liters of", "boxes of",
)
#: Goods noted down as arrived («apunta que han llegado…» is read «apunta que llegan…»), never «llegan» alone: people
#: arrive too («han llegado dos más para la mesa 7»).
GOODS_NOTED_AS_ARRIVED = ("apunta que llegan", "apuntame que llegan", "anota que llegan", "registra que llegan")
#: Stock told as broken, the stock a write-off takes out.
BROKEN_STOCK = ("roto", "rotura", "broke", "broken")


class InventoryConfig(LiveAppConfig):
    name = "apps.inventory"
    label = "inventory"
    kind = "app"
    verbose_name = _("Inventory")
    icon = "ion:cube-outline"
    category = Category.CATALOG
    premium = False
    # The app store's texts, which register_apps writes to shared.app.
    summary = _(
        "Your catalog with its stock: products, categories, goods received, counts and low-stock alerts."
    )
    description = _(
        "Inventory keeps what you sell with stock: each product with its SKU, price, cost, tax category, "
        "unit of measure and how many are left. The till sells from this catalog and every sale lowers "
        "the stock on its own; goods received, stock counts and write-offs leave a movement that is never "
        "edited, so every balance is explained. It warns when an article runs low, imports and exports "
        "the catalog as CSV and sells by weight or measure without rounding."
    )
    # The restaurant's menu is this catalog. The hair salon's template brings a few retail products and turns the
    # app on when it is loaded (base/seeds, INVENTORY-F12).
    verticals = ["restaurant"]
    # Each product and category points at a tax category (tax.TaxCategory).
    requires = ["tax"]
    # The products' own photos (base.images): served by /p/media/ to the hub's sessions only.
    members_media = ["inventory/products/"]
    default_auto_field = "django.db.models.BigAutoField"
    # The allergens by their names: no field of the models labels them, so the assistant's card would say their codes.
    choices = {"allergens": ALLERGENS}
    # What these words mean to the Hub's assistant (base.assistant.relevance.synonyms). The «unidades» are the units of measure
    # (inventory.unit), and a «albarán», the «mercancía» or what «entran» (never «entrada»: its stem is that of «entre»)
    # is the goods inventory.stock.receive records. So are «20 kilos de» or «5 cajas de» a product, and what is noted
    # down as arrived, which are also its stock (inventory.stock); not the bottles, cans or units a sale line or a cart
    # counts too. A restaurant's «carta» is its products, in the very group live says for them (with fewer words it would
    # be a second concept, and «los productos de la carta» would count the products twice). What broke is the breakage
    # a write-off records, «roto» or «broken» (never «break» nor «breakage»: their stem is a staff member's break), and
    # told as broken («se han roto», «got broken») it is stock too, so beside a count it still brings the write-off;
    # not «rota» nor «rotas», which say what the business's own things are («la cadena está rota»).
    assistant_synonyms = (
        ("unidad", "unidades", "unit", "units"),
        (
            "albaran", "mercancia", "entran", "recibir", "recibe", "recibido", "receive", "received", "goods",
            "delivery note", *QUANTITIES_OF_GOODS, *GOODS_NOTED_AS_ARRIVED,
        ),
        ("stock", *BROKEN_STOCK, *QUANTITIES_OF_GOODS, *GOODS_NOTED_AS_ARRIVED),
        ("carta", "producto", "articulo", "product"),
        ("roto", "rota", "rotos", "rotas", "rotura", "broke", "broken"),
    )
    permissions = [
        "inventory.view_product",
        "inventory.view_category",
        "inventory.view_stock",
        "inventory.add_product",
        "inventory.change_product",
        "inventory.delete_product",
        "inventory.add_category",
        "inventory.change_category",
        "inventory.delete_category",
        "inventory.import_product",
        "inventory.export_product",
        "inventory.adjust_stock",
        "inventory.manage_settings",
    ]
    # Keys are the customer roles as the SaaS sends them (``hub_`` prefix included). The old
    # ``cashier`` role is gone: it had exactly what the employee has.
    role_permissions = {
        "hub_owner": ["inventory.*"],
        "hub_admin": ["inventory.*"],
        "hub_manager": ["inventory.*"],
        "hub_employee": [
            "inventory.view_product",
            "inventory.view_category",
            "inventory.view_stock",
        ],
    }
    # The tab bar's screens (frontend/composables/useInventoryTabs.ts): the help window names the screen in view by
    # them and the assistant links each one by its name. The first keeps the cube: it is the launcher's and «My apps»'
    # icon, and its screen is where «/inventory» lands.
    navigation = [
        Nav("dashboard", _("Dashboard"), "ion:cube-outline", "/inventory/dashboard"),
        Nav("products", _("Products"), "ion:cube-outline", "/inventory/products"),
        Nav("movements", _("Movements"), "ion:swap-vertical-outline", "/inventory/movements"),
        Nav("categories", _("Categories"), "ion:list-outline", "/inventory/categories"),
    ]
    help = Help(videos={"es": "dIppfjMEKWo", "en": "Pet7Q2ayo_Y"})
    # The Home's hooks, on the Panel's own queries. Registered icons only: `trending-down-outline` waits in
    # UI-REQUESTS.md.
    setup = [
        SetupStep(
            key="catalog",
            operation="inventory.stock.get_summary",
            configured_when=[SetupCheck(field="active_products", truthy=True)],
            title=_("Your catalog"),
            description=_("Add at least one product so there is something to sell."),
            icon="ion:cube-outline",
            route="/inventory/products",
            permission="inventory.add_product",
            order=30,
            required=True,
            refresh_on=PRODUCT_EVENTS,
        )
    ]
    widgets = [
        # A KPI says its name once, in its title; the money one is in the hub's currency. Every figure is in the colour of
        # data of inventory (6), the same on every screen.
        Widget(
            key="low_stock_count",
            title=_("Low-stock products"),
            icon="ion:alert-circle-outline",
            size="sm",
            permission=VIEW,
            default=True,
            refresh_on=FIGURE_EVENTS,
            kind="kpi",
            operation="inventory.stock.get_summary",
            map={"value": "products_low_stock"},
            options={"format": "number", "tone": 6},
        ),
        Widget(
            key="value",
            title=_("Stock value (at cost)"),
            icon="ion:cash-outline",
            size="sm",
            permission=VIEW,
            default=True,
            refresh_on=FIGURE_EVENTS,
            kind="kpi",
            operation="inventory.stock.get_summary",
            map={"value": "stock_value"},
            options={"format": "currency", "tone": 6},
        ),
        Widget(
            key="in_stock",
            title=_("Products in stock"),
            icon="ion:cube-outline",
            size="sm",
            permission=VIEW,
            refresh_on=FIGURE_EVENTS,
            kind="stat",
            operation="inventory.stock.get_summary",
            map={"value": "products_in_stock"},
            options={"format": "number", "tone": 6},
        ),
        # The Panel's own page size: the five with less stock, the one with less first.
        Widget(
            key="low_stock_products",
            title=_("Lowest-stock products"),
            icon="ion:arrow-down-outline",
            size="md",
            permission=VIEW,
            default=True,
            refresh_on=FIGURE_EVENTS,
            kind="bar-list",
            operation="inventory.product.list_low_stock",
            params={"limit": 5},
            map={"label": "name", "value": "stock"},
            options={"valueFormat": "number"},
        ),
    ]

    def recoverable_from_copy(self) -> list:
        """What a separate copy of the business gives back when ERPlora's staff recovers from it (BASE-F114), in this
        order: first each category the business lacks, by ``inventory.category.recover``, with the deleted products it
        had back in it; then each product it still holds deleted, the same, by ``inventory.product.restore``
        (INVENTORY-F34), and each it no longer holds, by ``inventory.product.recover`` (the screen's create and its
        image of the library), in its categories here; last, each product the business kept live goes back into the
        category brought back, by the screen's ``inventory.product_category.add``, counted apart because it touches
        what the business has."""
        from apps.inventory import queries  # the models are not loaded yet when this module is
        from base.recovery import Recoverable

        return [
            Recoverable(
                label=_("Product categories"),
                reads_since="0001_initial",
                read=queries.recovery.categories_in_copy,
                missing=queries.recovery.categories_not_in_business,
                create="inventory.category.recover",
            ),
            Recoverable(
                label=_("Products"),
                reads_since="0005_product_image",
                read=queries.recovery.products_in_copy,
                missing=queries.recovery.products_not_in_business,
                create="inventory.product.recover",
                deleted=queries.recovery.products_deleted_in_business,
                restore="inventory.product.restore",
            ),
            Recoverable(
                label=_("Product links to categories"),
                reads_since="0001_initial",
                read=queries.recovery.product_links_in_copy,
                missing=queries.recovery.product_links_not_in_business,
                create="inventory.product_category.add",
            ),
        ]
