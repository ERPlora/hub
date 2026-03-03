"""
Module Subscription Middleware — "Bouncer" Pattern

Intercepts requests to premium modules and redirects unpaid users
to a pricing page. Zero changes needed in module code.

Flow:
1. Detect module from URL namespace (e.g., 'tobacco', 'assistant')
2. Check if module is premium (reads PRICING from module.py)
3. Query Cloud API for subscription status (cached 5 min)
4. If not paid → redirect to /marketplace/pricing/<module_id>/
5. If paid/trialing → pass through normally

Also provides `is_module_paid(module_id)` for background jobs
that don't go through HTTP middleware.
"""
import logging
from pathlib import Path

from django.conf import settings
from django.core.cache import cache
from django.http import HttpResponse
from django.shortcuts import redirect
from django.urls import reverse

logger = logging.getLogger(__name__)

# Cache TTL for subscription status (seconds)
_SUB_CACHE_TTL = 300  # 5 minutes

# Cache key prefix
_CK_SUB_STATUS = 'mod_sub:'  # + hub_id:module_id


def _get_module_pricing(module_id):
    """
    Read PRICING dict from a module's module.py file.
    Returns None for non-existent or free modules.
    """
    cache_key = f'mod_pricing:{module_id}'
    cached = cache.get(cache_key)
    if cached is not None:
        return cached if cached != '__none__' else None

    modules_dir = getattr(settings, 'MODULES_DIR', None)
    if not modules_dir:
        cache.set(cache_key, '__none__', 3600)
        return None

    module_py = Path(modules_dir) / module_id / 'module.py'
    if not module_py.exists():
        cache.set(cache_key, '__none__', 3600)
        return None

    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            f'{module_id}.module', module_py,
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        pricing = getattr(mod, 'PRICING', None)
        if pricing and isinstance(pricing, dict):
            cache.set(cache_key, pricing, 3600)
            return pricing
    except Exception as e:
        logger.warning('[MODULE_SUB] Error reading PRICING from %s: %s', module_id, e)

    cache.set(cache_key, '__none__', 3600)
    return None


def _is_premium_module(module_id):
    """Check if a module has premium pricing (not free)."""
    pricing = _get_module_pricing(module_id)
    if not pricing:
        return False
    return pricing.get('type') in ('subscription', 'one_time')


def _fetch_subscription_status(hub_id, module_id, auth_token):
    """
    Query Cloud API for module subscription status.
    Returns dict with 'status', 'trial_end', 'period_end'.
    """
    import requests as http_requests

    cloud_api_url = getattr(settings, 'CLOUD_API_URL', 'https://erplora.com')

    try:
        response = http_requests.get(
            f'{cloud_api_url}/api/hubs/me/module-subscription/',
            params={'module': module_id},
            headers={
                'X-Hub-Token': auth_token,
                'Accept': 'application/json',
            },
            timeout=10,
        )
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        logger.warning('[MODULE_SUB] Cloud API error for %s: %s', module_id, e)

    return {'status': 'unknown'}


def get_subscription_status(module_id, hub_id=None, auth_token=None):
    """
    Get subscription status for a module (cached).
    Returns: 'active', 'trialing', 'expired', 'none', or 'unknown'.
    """
    if not hub_id or not auth_token:
        from apps.configuration.models import HubConfig
        hub_config = HubConfig.get_solo()
        hub_id = hub_id or str(hub_config.hub_id or '')
        auth_token = auth_token or hub_config.hub_jwt or hub_config.cloud_api_token

    if not hub_id or not auth_token:
        return 'unknown'

    cache_key = f'{_CK_SUB_STATUS}{hub_id}:{module_id}'
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    data = _fetch_subscription_status(hub_id, module_id, auth_token)
    status = data.get('status', 'none')

    cache.set(cache_key, status, _SUB_CACHE_TTL)
    return status


def is_module_paid(module_id):
    """
    Check if a premium module has active subscription.

    Used by background jobs (APScheduler, startup sync, etc.)
    that don't go through HTTP middleware.

    Returns True if:
    - Module is free (not premium)
    - Module is premium AND has active/trialing subscription
    Returns False if:
    - Module is premium AND subscription is expired/none/unknown
    """
    if not _is_premium_module(module_id):
        return True

    status = get_subscription_status(module_id)
    return status in ('active', 'trialing')


def invalidate_subscription_cache(module_id=None):
    """
    Invalidate cached subscription status.
    Call after purchase, cancellation, or Stripe webhook.
    """
    from apps.configuration.models import HubConfig
    hub_config = HubConfig.get_solo()
    hub_id = str(hub_config.hub_id or '')

    if module_id:
        cache.delete(f'{_CK_SUB_STATUS}{hub_id}:{module_id}')
    else:
        # Can't easily clear pattern with Django cache,
        # but keys expire in 5 min anyway
        pass


class ModuleSubscriptionMiddleware:
    """
    Bouncer middleware: blocks access to premium modules without payment.

    Redirects to /marketplace/pricing/<module_id>/ if the module is premium
    and the user hasn't paid or isn't in a trial period.

    Only intercepts /m/<module_id>/ URLs (module web UI).
    Does NOT intercept API URLs, marketplace, or system pages.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        return response

    def process_view(self, request, view_func, view_args, view_kwargs):
        # Only check authenticated users on module pages
        if not hasattr(request, 'session') or 'local_user_id' not in request.session:
            return None

        # Only intercept module URLs: /m/<module_id>/...
        if not request.path.startswith('/m/'):
            return None

        # Extract module_id from resolver match namespace
        resolver = getattr(request, 'resolver_match', None)
        if not resolver:
            return None

        # The namespace is the module_id (set by router.py)
        namespace = resolver.namespace
        if not namespace:
            return None

        # Check if module is premium
        if not _is_premium_module(namespace):
            return None

        # Get Hub config for Cloud API auth
        from apps.configuration.models import HubConfig
        hub_config = HubConfig.get_solo()
        hub_id = str(hub_config.hub_id or '')
        auth_token = hub_config.hub_jwt or hub_config.cloud_api_token

        if not hub_id or not auth_token:
            # Hub not connected — let module load (can't check status)
            return None

        # Check subscription status
        status = get_subscription_status(namespace, hub_id, auth_token)

        if status in ('active', 'trialing', 'unknown'):
            return None  # Paid or can't verify — pass through (fail-open)

        # Not paid — redirect to pricing page
        pricing_url = reverse('marketplace:module_pricing', kwargs={'module_id': namespace})

        # HTMX requests need HX-Redirect header
        if getattr(request, 'htmx', False):
            return HttpResponse(
                status=200,
                headers={'HX-Redirect': pricing_url},
            )

        return redirect(pricing_url)
