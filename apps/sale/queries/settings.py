"""The till's settings, as the manager reads them and as the till sells with them."""

from live.context import OperationContext
from live.operations import AI, operation

from apps.sale.models.settings import Settings
from apps.sale.schemas.fields import EmptyIn
from apps.sale.schemas.settings import SettingsOut

SETTINGS_FIELDS = [
    "allow_cash",
    "allow_card",
    "allow_transfer",
    "show_products",
    "show_services",
    "require_customer",
    "allow_discounts",
    "max_discount_percent",
    "enable_parked_tickets",
    "default_tax_included",
    "auto_invoice_with_tax_id",
    "default_document_type",
    "receipt_header",
    "receipt_footer",
    "receipt_footer_image",
    "receipt_marketing_url",
    "receipt_marketing_text",
]


def current_settings() -> Settings:
    """The business's row, or an unsaved one with the factory values."""
    return Settings.objects.first() or Settings()


def settings_row(settings: Settings) -> dict:
    row = {field: getattr(settings, field) for field in SETTINGS_FIELDS}
    row["updated_at"] = None if settings._state.adding else settings.updated_at
    return row


@operation(
    "sale.settings.get",
    kind="query",
    permission="sale.manage_settings",
    input=EmptyIn,
    output=SettingsOut,
    ai=AI(
        description="Read the till settings: payment methods allowed, products and services shown, customer required, "
        "discounts and their cap, parked checks, prices with VAT, default document and the receipt's texts.",
        asks={
            "en": (
                "what's the till configured to do?",
                "what's the most discount we allow?",
                "what does the receipt footer say?",
            ),
            "es": (
                "¿cómo tengo configurado el TPV?",
                "¿cuál es el descuento máximo que dejamos?",
                "¿qué pone al pie del ticket?",
            ),
        },
    ),
)
def get_settings(ctx: OperationContext, params: EmptyIn) -> dict:
    return settings_row(current_settings())


@operation(
    "sale.pos_settings.get",
    kind="query",
    permission="sale.view_sale",
    input=EmptyIn,
    output=SettingsOut,
    ai=AI(
        description="Read the till settings the till needs to sell, readable by whoever sells: payment methods "
        "allowed, products and services shown, customer required, discounts and their cap, parked checks, prices with "
        "VAT included or not, default document and the receipt's texts.",
        asks={
            "en": (
                "can I park checks on this till?",
                "do our prices include VAT?",
            ),
            "es": (
                "¿puedo dejar cuentas aparcadas?",
                "¿los precios del TPV van con IVA?",
            ),
        },
    ),
)
def get_pos_settings(ctx: OperationContext, params: EmptyIn) -> dict:
    return settings_row(current_settings())
