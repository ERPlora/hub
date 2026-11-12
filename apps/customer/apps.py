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
    # What a manager approves on the spot with their PIN on the employee's own device (BASE-F84), in the words the
    # dialog «An approval is needed» says. The old customers module's rule: what the manager holds, another profile does
    # with a manager's approval; what is the administrator's only (delete cards, groups and tags, erase personal data)
    # never; export is a read, never approved. ``customer.activity.add`` is left out: no screen asks for it.
    approvals = {
        "customer.customer.merge": _("Merge two customer cards"),
        "customer.group.create": _("Create a customer group"),
        "customer.group.update": _("Change a customer group"),
        "customer.tag.create": _("Create a customer tag"),
        "customer.tag.update": _("Change a customer tag"),
        "customer.field.create": _("Create a custom field"),
        "customer.field.update": _("Change a custom field"),
        "customer.field.delete": _("Delete a custom field"),
    }
    # The product's four tabs, with the product's icons (all in @erplora/ui's ION_ICONS).
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
        Nav(id="tags", label=_("Tags"), icon="ion:pricetags", path="/customer/tags"),
        Nav(
            id="fields",
            label=_("Fields"),
            icon="ion:layers-outline",
            path="/customer/fields",
        ),
    ]

    def fiscal_documents_kept(self) -> bool:
        """hub#599: the platform asks (``base.tenancy.offboarding``) before it drops the database of a business that
        left: The card sales of its customers (a manual entry has no sale behind it) here are documents nothing archives yet (PLAN-DB §6), so the database stays."""
        from apps.customer import queries  # the models are not loaded yet when this module is

        return queries.keeps_fiscal_documents()

    def recoverable_from_copy(self) -> list:
        """hub#1257: the platform asks (``base.tenancy.recovery``) what a separate copy of the business gives back when
        the staff recovers from it (BASE-F114): the copy's live cards the business lacks (``queries.cards_in_copy``,
        ``queries.cards_not_in_business``), each created by ``customer.customer.create``, the till's and the card's
        own. Never one whose personal data was erased."""
        from apps.customer import queries  # the models are not loaded yet when this module is
        from base.tenancy.recovery import Recoverable

        return [
            Recoverable(
                label=self.verbose_name,
                reads_since="0001_initial",
                read=queries.cards_in_copy,
                missing=queries.cards_not_in_business,
                create="customer.customer.create",
            )
        ]
