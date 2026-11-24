"""The customer app: the business's file of people and companies, and the owner of their personal data."""

from django.utils.translation import gettext_lazy as _
from live.meta import Category, Help, LiveAppConfig, Nav


class CustomerConfig(LiveAppConfig):
    name = "apps.customer"
    label = "customer"
    kind = "app"
    verbose_name = _("Customers")
    icon = "ion:people-outline"
    category = Category.PEOPLE
    premium = False
    # The public store's texts, which register_apps writes to shared.app.
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
    # What these words mean to the Hub's assistant (base.assistant.relevance.synonyms): a customer assigned to a check, as
    # the till's button says it («Asignar cliente», «Assign customer»), or a check put in their name is what
    # customer.order.link does. Only as phrases: «asigna», «pon» or «set» alone assign or set anything.
    assistant_synonyms = (
        (
            "link", "enlaza", "enlazar", "assign customer", "assign a customer", "assign the customer", "set the customer",
            "set a customer", "set customer", "in her name", "in his name", "in their name", "asignar cliente",
            "asigna cliente", "asignar un cliente", "asigna un cliente", "asignar el cliente", "asigna el cliente",
            "poner un cliente", "pon un cliente", "poner el cliente", "pon el cliente", "a su nombre",
        ),
    )
    # The product's 21 permissions, folded where every role held them together. Not declared on
    # purpose: ``customer.record_purchase``, which only the system context holds (the product's
    # ``internal`` commands): owner and admin get every declared permission.
    permissions = {
        "customer.view": _("View customers, groups, tags, activity, purchases and consents"),
        "customer.manage": _("Add, edit and import customers, add notes, groups and tags, and record consent"),
        "customer.configure": _("Create and change groups, tags and custom fields"),
        "customer.merge": _("Merge duplicate customers"),
        "customer.export": _("Export customers to CSV"),
        "customer.delete": _("Delete customers, groups and tags"),
        "customer.erase": _("Erase a customer's personal data"),
        "customer.record_activity": _("Note in a customer's activity what other apps bring"),
    }
    # Keys are the customer roles as the SaaS sends them (``hub_`` prefix included). The rights at
    # the counter (view, create, edit, notes, consent, link the order) are the employee's.
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
    # dialog «An approval is needed» says. What the manager holds, another profile does with a manager's approval;
    # what is the administrator's only (delete cards, groups and tags, erase personal data) never; export is a read,
    # never approved. ``customer.activity.add`` is left out: no screen asks for it.
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
            permission="customer.view",
        ),
        Nav(
            id="groups",
            label=_("Groups"),
            icon="ion:people-outline",
            path="/customer/groups",
            permission="customer.configure",
        ),
        Nav(id="tags", label=_("Tags"), icon="ion:pricetags", path="/customer/tags", permission="customer.configure"),
        Nav(
            id="fields",
            label=_("Fields"),
            icon="ion:layers-outline",
            path="/customer/fields",
            permission="customer.configure",
        ),
    ]
    help = Help()

    fiscal_archive_models = ("Purchase",)

    def fiscal_documents_kept(self) -> bool:
        """The platform asks (``base.tenancy.offboarding``) before it drops the database of a business that left: the
        card sales of its customers (a manual entry has no sale behind it) are documents to keep, so the database stays;
        they go to the fiscal archive first (``fiscal_archive_models``)."""
        from apps.customer import queries  # the models are not loaded yet when this module is

        return queries.keeps_fiscal_documents()

    def recoverable_from_copy(self) -> list:
        """The platform asks (``base.tenancy.recovery``) what a separate copy of the business gives back when the staff
        recovers from it: of the copy's live cards (``queries.cards_in_copy``), each the business still holds deleted
        comes back the same, with all that hangs from it (``queries.cards_deleted_in_business``,
        ``customer.customer.restore``, CUSTOMER-F33) and the groups, tags and custom field values the business deleted
        since (hub#1356), and each it no longer has is made again by
        ``customer.customer.recover`` (``queries.cards_not_in_business``): as ``customer.customer.create``, the till's
        and the card's own, makes it, with its groups, tags and custom field values there
        (``queries.recoverable_cards_in_copy``, hub#1285), each by the screen's own operation. Never one merged into
        another or whose personal data was erased."""
        from apps.customer import queries  # the models are not loaded yet when this module is
        from base.recovery import Recoverable

        return [
            Recoverable(
                label=self.verbose_name,
                reads_since="0001_initial",
                read=queries.recoverable_cards_in_copy,
                missing=queries.cards_not_in_business,
                create="customer.customer.recover",
                deleted=queries.cards_deleted_in_business,
                restore="customer.customer.restore",
            )
        ]
