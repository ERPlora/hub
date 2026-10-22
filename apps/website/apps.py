"""The website app: a hub's public presentation page on its own host, ``<slug>.erplora.com`` (round 2026-10-21, PLAN §29).

The owner picks one of four templates, fills in fixed sections (texts, photos, catalog, contact, address and
colours), hides the ones she does not use and publishes. A visitor without a session who opens ``/`` gets that page
(``apps/website/public_home.py``, the provider ``base.public_home`` loads); the staff sign in from its «Log in».
"""

from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy
from live.meta import Category, LiveAppConfig, Nav


class WebsiteConfig(LiveAppConfig):
    name = "apps.website"
    label = "website"
    kind = "app"
    # With a context: Clientes translates a customer's «Website» field as «Web».
    verbose_name = pgettext_lazy("app name", "Website")
    icon = "ion:globe-outline"
    category = Category.ORGANIZATION
    premium = False
    # The public store's texts (round 16, PLAN §21), which register_apps writes to shared.app.
    summary = _("Your business's own web page, with your catalog, contact details and a QR code to print.")
    description = _(
        "Website gives your business a simple page of its own at your ERPlora address. Choose one of four "
        "designs, fill in your name, photos, a few words about you, your products or services, how to reach you "
        "and where you are, pick your colours and publish. You can change the design at any time without losing "
        "anything, hide what you do not need, and print a QR code that takes your customers there. Your team "
        "signs in from the page's «Log in» button."
    )
    # A salon and a restaurant both want a page their customers find.
    verticals = ["hair_salon", "restaurant"]
    # Inventory's products and Services' services are read by their operation's name, only when installed.
    requires = []
    default_auto_field = "django.db.models.BigAutoField"
    permissions = ["website.view", "website.manage"]
    # Keys are the customer roles as the SaaS sends them (``hub_`` prefix included). The page speaks for the
    # business: a manager sees it; only the owner and the admin change, publish or take it offline.
    role_permissions = {
        "hub_owner": ["website.*"],
        "hub_admin": ["website.*"],
        "hub_manager": ["website.view"],
        "hub_employee": [],
    }
    # Positional (id, label, icon, path): scripts/app-icons.mjs reads every line starting with `icon =` as the
    # module's own icon.
    navigation = [Nav("site", pgettext_lazy("app name", "Website"), "ion:globe-outline", "/website")]
