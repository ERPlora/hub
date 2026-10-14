"""The customer app: the business's file of people and companies, and the owner of their personal data."""

from django.utils.translation import gettext_lazy as _
from live.meta import Category, LiveAppConfig, Nav


class CustomerConfig(LiveAppConfig):
    name = "apps.customer"
    label = "customer"
    kind = "app"
    verbose_name = _("Customers")
    icon = "ion:people-outline"
    category = Category.PEOPLE
    premium = False
    # The public store's texts (round 16, PLAN §21), which register_apps writes to shared.app.
    summary = _(
        "Your customers' file: contact and tax details, notes, groups, consent and what they bought."
    )
    description = _(
        "Customers keeps a card for every person and company you serve: contact and tax details, "
        "groups, tags and fields of your own, notes and activity, marketing consent per channel and "
        "every purchase. Phones are saved in international format, so the till, the diary and "
        "WhatsApp recognise the same person however the number was typed. Duplicate cards are "
        "merged in one step, and a customer's personal data is erased on request while the sales "
        "keep their tax copy."
    )
    verticals = ["hair_salon", "restaurant"]
    default_auto_field = "django.db.models.BigAutoField"
    # The product's 21 permissions, folded where every role held them together. Not declared on
    # purpose: ``customer.record_purchase``, which only the system context holds (the product's
    # ``internal`` commands): owner and admin get every declared permission.
    permissions = [
        "customer.view",
        "customer.manage",
        "customer.configure",
        "customer.merge",
        "customer.export",
        "customer.delete",
        "customer.erase",
        "customer.record_activity",
    ]
    # Keys are the customer roles as the SaaS sends them (``hub_`` prefix included). The old
    # «cashier» role is gone: its rights at the counter (view, create, edit, notes, consent, link
    # the order) are the employee's.
    role_permissions = {
        "hub_owner": ["customer.*"],
        "hub_admin": ["customer.*"],
        "hub_manager": [
            "customer.view",
            "customer.manage",
            "customer.configure",
            "customer.merge",
            "customer.export",
            "customer.record_activity",
        ],
        "hub_employee": ["customer.view", "customer.manage"],
    }
    # The product's four tabs. Tags waits for its own icon (pricetags: UI-REQUESTS.md); until the
    # shell registers it, a registered one.
    navigation = [
        Nav(
            id="customers",
            label=_("Customers"),
            icon="ion:people-outline",
            path="/customer/customers",
        ),
        Nav(
            id="groups",
            label=_("Groups"),
            icon="ion:people-outline",
            path="/customer/groups",
        ),
        Nav(id="tags", label=_("Tags"), icon="ion:list-outline", path="/customer/tags"),
        Nav(
            id="fields",
            label=_("Fields"),
            icon="ion:layers-outline",
            path="/customer/fields",
        ),
    ]
