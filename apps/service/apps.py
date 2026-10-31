"""The service app: the catalog of services a salon sells, who performs each one, and the vouchers."""

from django.utils.translation import gettext_lazy as _
from live.meta import Category, LiveAppConfig, Nav, SetupCheck, SetupStep

from apps.service.events import SERVICE_EVENTS


class ServiceConfig(LiveAppConfig):
    name = "apps.service"
    label = "service"
    kind = "app"
    verbose_name = _("Services")
    # The old module's `briefcase`, registered in the shell (ION_ICONS).
    icon = "ion:briefcase-outline"
    category = Category.CATALOG
    premium = False
    # The public store's texts (round 16, PLAN §21), which register_apps writes to shared.app.
    summary = _(
        "Your service menu: prices, durations, who performs each service and prepaid session vouchers."
    )
    description = _(
        "Services keeps what your salon sells when it is not an article: each service with its price, "
        "its duration, its category and its tax category, and the professionals who perform it with "
        "their own price and time. The diary books from it and the till charges from it. It also keeps "
        "the vouchers: packs of sessions a customer pays once and spends over several visits, with "
        "their balance, their expiry, courtesies and corrections, and every session spent."
    )
    # Every hair salon turns it on at sign-up; the restaurant's template does not carry it.
    verticals = ["hair_salon"]
    # The tax category of each service (tax.TaxCategory), the professionals who perform it
    # (staff.Member) and the owner of a voucher (customer.Customer).
    requires = ["tax", "staff", "customer"]
    # The services' own photos (SERVICE-F35; round 2026-10-30, base.images): served by /p/media/ to the hub's sessions
    # only.
    members_media = ["service/services/"]
    default_auto_field = "django.db.models.BigAutoField"
    permissions = [
        "service.view_service",
        "service.add_service",
        "service.change_service",
        "service.delete_service",
        "service.view_category",
        "service.add_category",
        "service.change_category",
        "service.delete_category",
        "service.view_package",
        "service.add_package",
        "service.change_package",
        "service.delete_package",
        "service.grant_package",
        "service.redeem_package",
        "service.view_package_balance",
        "service.view_orphan_grant",
        "service.void_grant",
        "service.adjust_grant",
        "service.return_session",
        "service.manage_settings",
    ]
    # Keys are the customer roles as the SaaS sends them (``hub_`` prefix included). The old cashier
    # role is gone: what it had (view, spend sessions, grant vouchers) is the employee's.
    role_permissions = {
        "hub_owner": ["service.*"],
        "hub_admin": ["service.*"],
        "hub_manager": [
            "service.view_service",
            "service.add_service",
            "service.change_service",
            "service.view_category",
            "service.add_category",
            "service.change_category",
            "service.view_package",
            "service.add_package",
            "service.change_package",
            "service.grant_package",
            "service.redeem_package",
            "service.view_package_balance",
            "service.view_orphan_grant",
            "service.void_grant",
            "service.adjust_grant",
            "service.return_session",
        ],
        "hub_employee": [
            "service.view_service",
            "service.add_service",
            "service.view_category",
            "service.view_package",
            "service.view_package_balance",
            "service.redeem_package",
            "service.grant_package",
        ],
    }
    # The Home's hook (PLAN-HUB round 2026-10-21): the old module's own item «Your service catalogue» (module.json
    # `setup`, services#26), order 31 and important, done once one offered service can be charged (its tax category
    # alive), for whoever adds services, leading to the list of services. Refreshed on what changes the services on
    # offer. The old module declared no panel and no bell row.
    setup = [
        SetupStep(
            key="catalog",
            operation="service.catalog.status",
            configured_when=[SetupCheck(field="sellable_services", truthy=True)],
            title=_("Your service catalogue"),
            description=_("Add the services you sell, with their price and duration."),
            icon="ion:briefcase-outline",
            route="/service/services",
            permission="service.add_service",
            order=31,
            required=True,
            refresh_on=SERVICE_EVENTS,
        )
    ]
    # Positional (id, label, icon, path): scripts/app-icons.mjs reads every line starting with
    # `icon =` as the module's own icon. The same icons as the tabbar (frontend/tabs.ts).
    # SERVICE-F25: the holds of the till nobody charged in a day are marked expired, every hour, by the
    # worker as the system (cron in UTC). Reading a balance already skips them.
    scheduled_tasks = [
        {
            "name": "expire_session_holds",
            "operation": "service.session.expire",
            "cron": "0 * * * *",
            "catch_up": "collapse",
        }
    ]
    navigation = [
        Nav("services", _("Services"), "ion:briefcase-outline", "/service/services"),
        Nav(
            "categories",
            _("Categories"),
            "ion:pricetags-outline",
            "/service/categories",
        ),
        Nav("packages", _("Packages"), "ion:gift-outline", "/service/packages"),
    ]
