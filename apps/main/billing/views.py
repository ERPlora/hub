"""
Hub Billing Views — displays invoices from Cloud.
"""
import logging
import traceback

from apps.accounts.decorators import login_required
from apps.core.htmx import htmx_view
from apps.sync.services.cloud_api import get_cloud_api, CloudAPIError

logger = logging.getLogger(__name__)


@login_required
@htmx_view('main/billing/pages/index.html', 'main/billing/partials/content.html')
def index(request):
    """Hub billing page — shows invoices fetched from Cloud API."""
    invoices = []
    error = None

    try:
        api = get_cloud_api()
        if api.is_configured:
            invoices = api.get_invoices()
    except CloudAPIError as e:
        logger.error(f"[BILLING] Failed to fetch invoices: {e}")
        error = str(e)
    except Exception as e:
        logger.error(f"[BILLING] Unexpected error: {e}\n{traceback.format_exc()}")
        error = str(e)

    return {
        'invoices': invoices,
        'error': error,
    }
