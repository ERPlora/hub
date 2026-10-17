"""The invoice app declares its module metadata, its menu entries, its permissions and what each role gets."""

from django.apps import apps
from django.conf import settings
from live.meta import Category, LiveAppConfig, Nav, module_configs, permissions_for_role

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
        "invoice.invoice.line_defaults",
        "invoice.invoice.create",
        "invoice.invoice.create_from_sale",
        "invoice.invoice.substitute",
        "invoice.invoice.mark_paid",
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
