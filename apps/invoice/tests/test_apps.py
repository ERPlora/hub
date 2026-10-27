"""The invoice app declares its module metadata, its menu entries, its permissions, what each role gets and its
hooks of the Home."""

from django.apps import apps
from django.conf import settings
from django.utils import translation
from live.live_registry import live_registry
from live.meta import (
    Category,
    LiveAppConfig,
    Nav,
    SetupCheck,
    SetupStep,
    module_configs,
    permissions_for_role,
)
from live.operations import registry

from apps.invoice import events as E
from base import home

PERMISSIONS = [
    "invoice.view_invoice",
    "invoice.add_invoice",
    "invoice.rectify_invoice",
    "invoice.manage_series",
    "invoice.manage_issuer",
]


def invoice():
    return apps.get_app_config("invoice")


def test_invoice_is_an_installed_live_app():
    config = invoice()
    assert isinstance(config, LiveAppConfig)
    assert config.name == "apps.invoice"
    assert config.label == "invoice"
    assert "apps.invoice" in settings.INSTALLED_APPS


def test_it_requires_tax_sale_and_customer():
    # An invoice is born from a real sale (its lines, amounts and frozen rules), its fiscal keys are
    # tax's rules and its recipient is copied from a customer's card: foreign keys to the three.
    assert invoice().requires == ["tax", "sale", "customer"]


def test_invoice_is_a_free_module_of_the_sales_group():
    config = invoice()
    assert config.kind == "app"
    assert config in module_configs()
    assert config.category is Category.SALES
    assert config.premium is False
    # Registered in the shell (packages/ui/src/shell/icons.ts); the old document-text-outline waits
    # in apps/invoice/UI-REQUESTS.md.
    assert config.icon == "ion:receipt-outline"


def test_invoice_is_in_the_store_and_in_both_verticals():
    config = invoice()
    assert 0 < len(str(config.summary)) <= 120
    assert str(config.description)
    assert config.verticals == ["hair_salon", "restaurant"]
    assert config.listed is True


def test_permissions():
    # The product's four, plus configuring the issuer (the business's tax identity), new here.
    assert invoice().permissions == PERMISSIONS


def test_roles_are_the_four_customer_roles_with_the_hub_prefix():
    assert set(invoice().role_permissions) == {
        "hub_owner",
        "hub_admin",
        "hub_manager",
        "hub_employee",
    }


def test_roles():
    config = invoice()
    for role in ("hub_owner", "hub_admin"):
        assert permissions_for_role([config], role) == set(PERMISSIONS), role
    # The manager rectifies and keeps the series; the issuer is the owner's and the admin's.
    assert permissions_for_role([config], "hub_manager") == {
        "invoice.view_invoice",
        "invoice.add_invoice",
        "invoice.rectify_invoice",
        "invoice.manage_series",
    }
    # The employee looks, prints, issues by hand and marks paid (as the product did).
    assert permissions_for_role([config], "hub_employee") == {
        "invoice.view_invoice",
        "invoice.add_invoice",
    }


def test_navigation_is_the_three_tabs_with_registered_icons():
    entries = invoice().navigation
    assert all(isinstance(entry, Nav) for entry in entries)
    assert [
        (entry.id, str(entry.label), entry.path, entry.icon) for entry in entries
    ] == [
        ("invoices", "Invoices", "/invoice/invoices", "ion:receipt-outline"),
        ("series", "Series", "/invoice/series", "ion:layers-outline"),
        ("issuer", "Issuer", "/invoice/issuer", "ion:storefront-outline"),
    ]


def test_every_operation_is_described_for_the_assistant():
    # The assistant uses the app by voice and text with the user's own session: it sees every
    # operation, and a write says how risky it is (high: issuing, substituting, rectifying, the issuer).
    from live.operations import registry

    ops = {name: op for name, op in registry.items() if name.startswith("invoice.")}
    assert set(ops) == {
        "invoice.invoice.list",
        "invoice.invoice.get",
        "invoice.invoice.by_source",
        "invoice.invoice.document",
        "invoice.invoice.print",
        "invoice.invoice.line_defaults",
        "invoice.invoice.create",
        "invoice.invoice.create_from_sale",
        "invoice.invoice.substitute",
        "invoice.invoice.mark_paid",
        "invoice.invoice.rectification_preview",
        "invoice.invoice.rectify",
        "invoice.invoice.rectify_from_refund",
        "invoice.invoice.rectify_from_void",
        "invoice.series.list",
        "invoice.series.peek_next",
        "invoice.series.create",
        "invoice.series.update",
        "invoice.numbering.status",
        "invoice.numbering.gaps",
        "invoice.numbering.allocations",
        "invoice.issuer.get",
        "invoice.issuer.update",
        "invoice.issuer.sync",
        "invoice.invoice.issue_platform",
        "invoice.invoice.platform_status",
        "invoice.invoice.platform_document",
        "invoice.invoice.platform_health",
    }
    high = {
        "invoice.invoice.create",
        "invoice.invoice.create_from_sale",
        "invoice.invoice.substitute",
        "invoice.invoice.rectify",
        "invoice.invoice.rectify_from_refund",
        "invoice.invoice.rectify_from_void",
        "invoice.issuer.update",
        "invoice.issuer.sync",
        "invoice.invoice.issue_platform",
    }
    for name, op in ops.items():
        assert isinstance(op.ai, dict) and str(op.ai.get("description", "")).strip(), (
            name
        )
        if op.kind == "command":
            assert op.ai.get("risk") == ("high" if name in high else "normal"), name
        else:
            assert "risk" not in op.ai, name


def test_every_input_field_says_what_it_is():
    # The JSON Schema of the assistant's tools: every field of every input carries a description.
    from live.operations import registry

    for name, op in registry.items():
        if not name.startswith("invoice."):
            continue
        for field_name, field in op.input.model_fields.items():
            assert (field.description or "").strip(), f"{name}.{field_name}"


def test_the_system_alone_receives_the_issuer_from_the_saas():
    # `invoice.sync_issuer` is declared by no role: only the system context (`*`) holds it.
    from live.operations import registry

    assert registry["invoice.issuer.sync"].permission == "invoice.sync_issuer"
    assert "invoice.sync_issuer" not in invoice().permissions


def test_the_system_alone_issues_erploras_own_invoices():
    # ERPlora's platform hub (PLAN-SAAS §4): `invoice.issue_platform` is declared by no role and no route serves it;
    # only /internal/platform/invoices, signed by the SaaS, calls it as the system.
    from live.operations import registry

    for name in (
        "invoice.invoice.issue_platform",
        "invoice.invoice.platform_status",
        "invoice.invoice.platform_document",
        "invoice.invoice.platform_health",
    ):
        assert registry[name].permission == "invoice.issue_platform", name
        assert registry[name].expose_api is False, name
    assert "invoice.issue_platform" not in invoice().permissions


# The Home's hooks (PLAN-HUB round 2026-10-21; FIX-INVOICE-SETUP-HOOKS): the old hub's ⛔ «Your business details»
# (a core item there, ``BLOCKING_KEYS``; here the issuer lives in Invoicing) and the old module's module.json `setup`
# «Your invoice numbering» (it had no `widgets` nor `bell`), on the queries the Issuer and Series screens read.


def steps() -> dict[str, SetupStep]:
    return {step.key: step for step in invoice().setup}


def test_the_homes_steps_are_your_business_details_then_your_invoice_numbering():
    assert all(isinstance(step, SetupStep) for step in invoice().setup)
    assert [step.key for step in invoice().setup] == ["business_identity", "numbering"]


def test_your_business_details_is_done_with_the_issuer_every_document_needs():
    """INVOICE-F21: done when the issuer has what issuing refuses to go without (``Issuer.configured``: legal name,
    tax ID and address), set up in Invoicing → Issuer by whoever may change it (gh:hub#1954: the screen with the tax
    ID in sight, never a settings tab without it)."""
    step = steps()["business_identity"]
    assert (
        step.operation,
        list(step.configured_when),
        dict(step.params),
        step.route,
        step.permission,
        step.icon,
        list(step.countries),
        step.order,
        step.required,
    ) == (
        "invoice.issuer.get",
        [SetupCheck(field="configured", truthy=True)],
        {},
        "/invoice/issuer",
        "invoice.manage_issuer",
        "ion:storefront-outline",
        [],
        40,
        True,
    )
    assert "configured" in registry[step.operation].output.model_fields
    # The ⛔ is base's (its LEGAL_STEPS, the old hub's BLOCKING_KEYS), never the module's.
    assert home.level_of(f"invoice.{step.key}", step.required) == home.LEVEL_LEGAL


def test_your_invoice_numbering_is_done_once_the_business_has_its_numbering():
    """INVOICE-F14: the series of the year are born on their own with the first document, so the step is
    recommended, pending only while the business has no series at all (before its first document, the one moment a
    prefix or the numbering of another system can still be chosen) and done for good after: a new year's series
    inherit the last year's prefix and format."""
    step = steps()["numbering"]
    assert (
        step.operation,
        list(step.configured_when),
        dict(step.params),
        step.route,
        step.permission,
        step.icon,
        list(step.countries),
        step.order,
        step.required,
    ) == (
        "invoice.numbering.status",
        [SetupCheck(field="total_series", truthy=True)],
        {},
        "/invoice/series",
        "invoice.manage_series",
        "ion:layers-outline",
        [],
        50,
        False,
    )
    assert "total_series" in registry[step.operation].output.model_fields
    assert registry[step.operation].kind == "query"  # it only reads: it never opens the year's series
    assert home.level_of(f"invoice.{step.key}", step.required) == home.LEVEL_RECOMMENDED


def test_the_steps_speak_the_language_of_whoever_reads_them():
    """gh:hub#868: the old checklist said a module's step in English to a Spanish reader."""
    texts = {}
    for language in ("en", "es"):
        with translation.override(language):
            texts[language] = [(str(step.title), str(step.description)) for step in invoice().setup]
    assert texts["en"] == [
        (
            "Your business details",
            "Legal name, tax ID and address: without them you cannot issue an invoice.",
        ),
        (
            "Your invoice numbering",
            "Before your first sale, check the prefix your invoice numbers will carry. If you are coming from "
            "another system, continue its numbering instead of starting again at 1.",
        ),
    ]
    assert texts["es"] == [
        (
            "Los datos de tu negocio",
            "Razón social, NIF y domicilio: sin ellos no puedes emitir una factura.",
        ),
        (
            "Tu numeración de facturas",
            "Antes de tu primera venta, revisa el prefijo con el que saldrán tus números de factura. Si vienes de "
            "otro sistema, continúa su numeración en vez de empezar otra vez por el 1.",
        ),
    ]


def test_each_step_is_refreshed_by_the_events_that_change_its_query():
    # gh:hub#900: the old notice stayed after the business details were saved; the issuer saved or received, a
    # series created or changed and a document that opens one re-run the steps.
    identity, numbering = steps()["business_identity"], steps()["numbering"]
    assert list(identity.refresh_on) == [E.ISSUER_UPDATED]
    assert list(numbering.refresh_on) == E.SERIES_EVENTS
    for step in (identity, numbering):
        assert set(step.refresh_on) <= set(live_registry.subscribable[step.operation]), step.key


def test_the_app_brings_no_panels_nor_counters_to_the_home():
    # The old module had neither `widgets` nor `bell`.
    assert (list(invoice().widgets), list(invoice().bell)) == ([], [])
