"""
Core services for ERPlora Hub.

These services are shared across all modules and provide common functionality.
Import them in your module like:

    from apps.core.services import format_currency, calculate_tax, export_to_csv
"""
from .sync_service import get_sync_service, SyncService
from .currency_service import (
    get_currency,
    get_currency_symbol,
    format_currency,
    format_number,
    parse_currency,
    currency,
)
from .tax_service import (
    get_tax_config,
    get_tax_rate,
    is_tax_included,
    calculate_tax,
    get_net_amount,
    get_gross_amount,
    get_tax_amount,
    format_tax_rate,
)
from .export_service import (
    export_to_csv,
    export_to_excel,
    generate_csv_string,
)
from .import_service import (
    parse_import_file,
    ImportResult,
)
from .print_service import (
    render_print_page,
    render_receipt,
    render_report,
)

__all__ = [
    # Sync
    "get_sync_service",
    "SyncService",
    # Currency
    "get_currency",
    "get_currency_symbol",
    "format_currency",
    "format_number",
    "parse_currency",
    "currency",
    # Tax
    "get_tax_config",
    "get_tax_rate",
    "is_tax_included",
    "calculate_tax",
    "get_net_amount",
    "get_gross_amount",
    "get_tax_amount",
    "format_tax_rate",
    # Export
    "export_to_csv",
    "export_to_excel",
    "generate_csv_string",
    # Import
    "parse_import_file",
    "ImportResult",
    # Print
    "render_print_page",
    "render_receipt",
    "render_report",
]
