"""
Marketplace Views - Multi-store marketplace with sidebar filters

Tabs:
- Modules: Software modules from Cloud marketplace
- Business Types: Browse by business type (from blueprints)
- Compliance: Country-specific required modules
"""
import json
import logging
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from pathlib import Path

from django.core.cache import cache
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.conf import settings as django_settings
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from apps.core.htmx import htmx_view
from apps.accounts.decorators import login_required

logger = logging.getLogger(__name__)


def _get_session():
    """Get a requests session with automatic retry on connection errors.

    Retries on connection resets/timeouts (common after long idle periods
    when the underlying TCP connection goes stale in the pool).
    """
    session = requests.Session()
    retry = Retry(total=2, backoff_factor=0.3, status_forcelist=[502, 503, 504])
    adapter = HTTPAdapter(max_retries=retry)
    session.mount('https://', adapter)
    session.mount('http://', adapter)
    return session


# Cache TTL (seconds)
_CACHE_TTL = getattr(django_settings, 'MARKETPLACE_CACHE_TTL', 300)

# Cache key prefixes
_CK_MODULES_LIST = 'mp:modules_list'
_CK_SECTORS_LIST = 'mp:sectors_list'
_CK_TYPES_LIST = 'mp:types_list'
_CK_FU_DETAIL = 'mp:fu:'                  # + slug (functional unit)
_CK_TYPE_DETAIL = 'mp:type:'              # + slug (business type)
_CK_MODULE_DETAIL = 'mp:module:'           # + slug
_CK_INSTALLED_IDS = 'mp:installed_ids'


# --- Marketplace navigation (tabbar) ---

def _marketplace_navigation(active_tab):
    """Build navigation context for the marketplace footer tabbar."""
    return [
        {
            'url': reverse('marketplace:index'),
            'icon': 'cube-outline',
            'label': str(_('Modules')),
            'active': active_tab == 'modules',
        },
        {
            'url': reverse('marketplace:my_purchases'),
            'icon': 'bag-check-outline',
            'label': str(_('My Purchases')),
            'active': active_tab == 'purchases',
        },
        {
            'url': reverse('marketplace:business_types'),
            'icon': 'business-outline',
            'label': str(_('Business Types')),
            'active': active_tab == 'business_types',
        },
        {
            'url': reverse('marketplace:compliance'),
            'icon': 'shield-checkmark-outline',
            'label': str(_('Compliance')),
            'active': active_tab == 'compliance',
        },
    ]


def _get_cloud_api_url():
    """Get the Cloud API base URL."""
    return getattr(django_settings, 'CLOUD_API_URL', 'https://erplora.com')


def _get_installed_module_ids():
    """Get list of installed module IDs from the modules directory (cached 60s)."""
    cached = cache.get(_CK_INSTALLED_IDS)
    if cached is not None:
        return cached
    modules_dir = Path(django_settings.MODULES_DIR)
    installed = []
    if modules_dir.exists():
        for module_dir in modules_dir.iterdir():
            if module_dir.is_dir() and not module_dir.name.startswith('.'):
                installed.append(module_dir.name.lstrip('_'))
    cache.set(_CK_INSTALLED_IDS, installed, 60)
    return installed


def _invalidate_installed_cache():
    """Invalidate the installed modules cache (call after install/uninstall)."""
    cache.delete(_CK_INSTALLED_IDS)


def _get_installed_module_version(module_id):
    """Read MODULE_VERSION from an installed module's module.py. Returns None if not found."""
    from apps.core.services.module_install_service import ModuleInstallService
    version = ModuleInstallService.get_installed_version(module_id)
    return version if version != '0.0.0' else None


# Store type configurations
STORE_TYPES = {
    'modules': {
        'name': 'Modules',
        'name_es': 'Módulos',
        'icon': 'cube-outline',
        'api_endpoint': '/api/marketplace/modules/',
        'enabled': True,
        'filters': ['sector', 'type'],
    },
    'hubs': {
        'name': 'Hubs',
        'name_es': 'Hubs',
        'icon': 'server-outline',
        'api_endpoint': '/api/marketplace/hubs/',
        'enabled': True,
        'filters': ['region', 'plan'],
    },
    'components': {
        'name': 'Components',
        'name_es': 'Componentes',
        'icon': 'hardware-chip-outline',
        'api_endpoint': '/api/marketplace/components/',
        'enabled': False,
        'filters': ['category', 'brand'],
    },
    'products': {
        'name': 'Products',
        'name_es': 'Productos',
        'icon': 'pricetag-outline',
        'api_endpoint': '/api/marketplace/products/',
        'enabled': False,
        'filters': ['category', 'supplier'],
    },
}


def get_store_config(store_type):
    """Get configuration for a store type"""
    return STORE_TYPES.get(store_type, STORE_TYPES['modules'])


@login_required
@htmx_view('marketplace/pages/marketplace.html', 'marketplace/partials/marketplace_content.html')
def store_index(request, store_type='modules'):
    """
    Main marketplace view with sidebar filters.
    """
    from apps.configuration.models import HubConfig

    config = get_store_config(store_type)
    if not config['enabled'] and store_type not in ['modules', 'hubs']:
        store_type = 'modules'
        config = get_store_config(store_type)

    # Get language for localized names
    language = getattr(request, 'LANGUAGE_CODE', 'en')[:2]

    # Get filters based on store type
    filters_data = _get_filters_for_store(store_type, language, request)

    # Default business type filter from HubConfig
    hub_config = HubConfig.get_config()
    selected_types = hub_config.selected_business_types or []
    default_business_types = []
    if selected_types and store_type == 'modules':
        all_types = _fetch_business_types_for_filters()
        types_by_code = {t.get('code', ''): t for t in all_types}
        for code in selected_types:
            t = types_by_code.get(code)
            if t:
                default_business_types.append({
                    'code': code,
                    'name': t.get('name', code),
                })

    return {
        'current_section': 'marketplace',
        'page_title': 'Marketplace',
        'store_type': store_type,
        'store_config': config,
        'store_types': STORE_TYPES,
        'filters': filters_data,
        'default_business_types': default_business_types,
        'navigation': _marketplace_navigation('modules'),
    }


def _fetch_sectors_for_filters():
    """Fetch sectors from Cloud blueprints API for the marketplace filter (cached)."""
    cached = cache.get(_CK_SECTORS_LIST)
    if cached is not None:
        return cached

    cloud_api_url = getattr(django_settings, 'CLOUD_API_URL', 'https://erplora.com')

    try:
        response = _get_session().get(
            f"{cloud_api_url}/api/blueprints/sectors/",
            headers={'Accept': 'application/json'},
            timeout=10,
        )
        if response.status_code == 200:
            data = response.json()
            sectors = data.get('results', data) if isinstance(data, dict) else data
            if not isinstance(sectors, list):
                sectors = []
            cache.set(_CK_SECTORS_LIST, sectors, _CACHE_TTL)
            return sectors
    except requests.exceptions.RequestException:
        pass
    return []


def _fetch_business_types_for_filters():
    """Fetch business types from Cloud blueprints API for the marketplace filter (cached)."""
    cached = cache.get(_CK_TYPES_LIST)
    if cached is not None:
        return cached

    cloud_api_url = getattr(django_settings, 'CLOUD_API_URL', 'https://erplora.com')

    try:
        response = _get_session().get(
            f"{cloud_api_url}/api/blueprints/types/",
            headers={'Accept': 'application/json'},
            timeout=10,
        )
        if response.status_code == 200:
            data = response.json()
            types = data.get('results', data) if isinstance(data, dict) else data
            if not isinstance(types, list):
                types = []
            # Filter out types without a code (required for URL generation)
            types = [t for t in types if t.get('code')]
            cache.set(_CK_TYPES_LIST, types, _CACHE_TTL)
            return types
    except requests.exceptions.RequestException:
        pass
    return []


def _fetch_functional_units():
    """Fetch functional units from Cloud blueprints API (cached, replaces solutions)."""
    cache_key = 'mp:functional_units_list'
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    cloud_api_url = getattr(django_settings, 'CLOUD_API_URL', 'https://erplora.com')

    try:
        response = _get_session().get(
            f"{cloud_api_url}/api/blueprints/functional-units/",
            headers={'Accept': 'application/json'},
            timeout=15,
        )
        if response.status_code == 200:
            data = response.json()
            units = data.get('results', data) if isinstance(data, dict) else data
            if not isinstance(units, list):
                units = []
            cache.set(cache_key, units, _CACHE_TTL)
            return units
    except requests.exceptions.RequestException:
        pass
    return []


def _get_filters_for_store(store_type, language, request):
    """Get filter options based on store type"""
    filters = {}

    if store_type == 'modules':
        # Fetch sectors and business types from blueprints API
        sectors = _fetch_sectors_for_filters()
        business_types = _fetch_business_types_for_filters()
        functional_units = _fetch_functional_units()

        filters['sectors'] = sectors
        filters['business_types'] = business_types
        filters['types'] = [
            {'id': 'free', 'name': 'Free', 'name_es': 'Gratis', 'icon': 'gift-outline'},
            {'id': 'one_time', 'name': 'One-time', 'name_es': 'Pago único', 'icon': 'card-outline'},
            {'id': 'subscription', 'name': 'Subscription', 'name_es': 'Suscripción', 'icon': 'sync-outline'},
        ]

        # Build industries_list for the template filter modal
        industries_list = [
            {'id': t.get('code', ''), 'name': t.get('name', t.get('code', ''))}
            for t in business_types
            if t.get('code')
        ]
        filters['industries_list'] = industries_list
        filters['industries'] = bool(industries_list)

        # Build solutions_grouped from functional units (grouped by block_type or ungrouped)
        groups_map = {}
        for unit in functional_units:
            block_type = unit.get('block_type') or unit.get('group') or ''
            block_type_name = unit.get('block_type_name') or block_type or 'Other'
            if block_type not in groups_map:
                groups_map[block_type] = {'name': block_type_name, 'blocks': []}
            groups_map[block_type]['blocks'].append({
                'id': unit.get('code') or unit.get('id', ''),
                'name': unit.get('name', ''),
                'is_active': False,
            })
        filters['solutions_grouped'] = list(groups_map.values())

    elif store_type == 'hubs':
        filters['regions'] = [
            {'id': 'eu', 'name': 'Europe', 'name_es': 'Europa'},
            {'id': 'us', 'name': 'United States', 'name_es': 'Estados Unidos'},
            {'id': 'latam', 'name': 'Latin America', 'name_es': 'Latinoamérica'},
        ]
        filters['plans'] = [
            {'id': 'free', 'name': 'Free', 'name_es': 'Gratis'},
            {'id': 'basic', 'name': 'Basic', 'name_es': 'Básico'},
            {'id': 'pro', 'name': 'Professional', 'name_es': 'Profesional'},
            {'id': 'enterprise', 'name': 'Enterprise', 'name_es': 'Empresa'},
        ]

    return filters


# Cancel subscription

@login_required
def cancel_subscription(request):
    """Cancel a module subscription via Cloud API."""
    if request.method != 'POST':
        return HttpResponse(status=405)

    try:
        data = json.loads(request.body)
        module_id = data.get('module_id', '')
    except (json.JSONDecodeError, ValueError):
        return HttpResponse(
            json.dumps({'success': False, 'error': 'Invalid data'}),
            content_type='application/json', status=400,
        )

    if not module_id:
        return HttpResponse(
            json.dumps({'success': False, 'error': 'Missing module_id'}),
            content_type='application/json', status=400,
        )

    from apps.configuration.models import HubConfig
    hub_config = HubConfig.get_solo()
    auth_token = hub_config.hub_jwt or hub_config.cloud_api_token

    if not auth_token:
        return HttpResponse(
            json.dumps({'success': False, 'error': str(_('Hub not connected to Cloud.'))}),
            content_type='application/json', status=400,
        )

    cloud_api_url = _get_cloud_api_url()

    try:
        response = _get_session().post(
            f"{cloud_api_url}/api/marketplace/modules/{module_id}/cancel-subscription/",
            json={},
            headers={
                'X-Hub-Token': auth_token,
                'Content-Type': 'application/json',
            },
            timeout=30,
        )

        resp_data = response.json()
        if response.status_code == 200:
            return HttpResponse(
                json.dumps({'success': True, 'message': resp_data.get('message', '')}),
                content_type='application/json',
            )
        else:
            return HttpResponse(
                json.dumps({'success': False, 'error': resp_data.get('error', 'Failed to cancel')}),
                content_type='application/json', status=response.status_code,
            )
    except requests.exceptions.RequestException as e:
        return HttpResponse(
            json.dumps({'success': False, 'error': str(e)}),
            content_type='application/json', status=500,
        )


# My Purchases

@login_required
@htmx_view('marketplace/pages/marketplace.html', 'marketplace/partials/my_purchases_content.html')
def my_purchases(request):
    """My Purchases — show paid purchases from Cloud with subscription status."""
    from apps.configuration.models import HubConfig

    hub_config = HubConfig.get_solo()
    auth_token = hub_config.hub_jwt or hub_config.cloud_api_token

    if not auth_token:
        return {
            'current_section': 'marketplace',
            'page_title': _('My Purchases'),
            'error': str(_('Hub not connected to Cloud. Please connect in Settings.')),
            'navigation': _marketplace_navigation('purchases'),
        }

    cloud_api_url = _get_cloud_api_url()

    try:
        response = _get_session().get(
            f"{cloud_api_url}/api/marketplace/modules/my_purchases/",
            headers={
                'X-Hub-Token': auth_token,
                'Content-Type': 'application/json',
            },
            timeout=15,
        )
        if response.status_code != 200:
            return {
                'current_section': 'marketplace',
                'page_title': _('My Purchases'),
                'error': str(_('Could not fetch purchases from Cloud.')),
                'navigation': _marketplace_navigation('purchases'),
            }
        purchases = response.json()
    except requests.exceptions.RequestException:
        return {
            'current_section': 'marketplace',
            'page_title': _('My Purchases'),
            'error': str(_('Could not connect to Cloud.')),
            'navigation': _marketplace_navigation('purchases'),
        }

    installed_module_ids = _get_installed_module_ids()

    for p in purchases:
        p['is_installed'] = (
            p.get('module_slug', '') in installed_module_ids
            or p.get('module_id', '') in installed_module_ids
        )
        p['detail_url'] = reverse(
            'marketplace:module_detail',
            kwargs={'slug': p.get('module_slug', '')},
        )
        # Use subscription_price_monthly (real module price) over amount paid
        monthly = p.get('subscription_price_monthly') or p.get('price') or 0
        try:
            monthly = float(monthly)
            p['annual_cost'] = f"{monthly * 12:.2f}" if monthly else ''
            # Ensure price reflects the real subscription price, not trial $0
            if p.get('subscription_price_monthly') and not p.get('price'):
                p['price'] = monthly
        except (TypeError, ValueError):
            p['annual_cost'] = ''

    # Sort: active/trialing first, then canceled, then expired/other
    status_order = {'active': 0, 'trialing': 1, 'past_due': 2, 'canceled': 3, 'expired': 4}
    purchases.sort(key=lambda p: status_order.get(p.get('subscription_status', ''), 5))

    return {
        'current_section': 'marketplace',
        'page_title': _('My Purchases'),
        'purchases': purchases,
        'navigation': _marketplace_navigation('purchases'),
    }


# Filters endpoint

@login_required
def filters_view(request, store_type):
    """Get filters for a store type (HTMX endpoint)"""
    language = getattr(request, 'LANGUAGE_CODE', 'en')[:2]
    filters_data = _get_filters_for_store(store_type, language, request)

    html = render_to_string('marketplace/partials/filters_content.html', {
        'filters': filters_data,
        'store_type': store_type,
    }, request=request)

    return HttpResponse(html)


MARKETPLACE_PER_PAGE_CHOICES = [12, 24, 48, 96, 0]


def _create_roles_for_installed_modules(module_slugs):
    """
    After installing modules, create all required roles:
    1. Default system roles (admin, manager, viewer)
    2. Blueprint roles from selected business types (chef, waiter, etc.)
    3. Module-driven roles (employee) via permission sync
    """
    from apps.configuration.models import HubConfig
    from apps.core.services.permission_service import PermissionService

    hub_config = HubConfig.get_solo()
    if not hub_config.hub_id:
        return

    hub_id = str(hub_config.hub_id)

    # 1. Always ensure default roles exist (admin, manager, viewer)
    try:
        PermissionService.create_default_roles(hub_id)
        logger.info("[AUTO ROLES] Default roles ensured (admin, manager, viewer)")
    except Exception as e:
        logger.warning("[AUTO ROLES] Failed to create default roles: %s", e)

    # 2. Sync all module permissions (creates employee role if modules need it)
    try:
        PermissionService.sync_all_module_permissions(hub_id)
        logger.info("[AUTO ROLES] Module permissions synced")
    except Exception as e:
        logger.warning("[AUTO ROLES] Failed to sync module permissions: %s", e)

    # 3. Create blueprint roles from selected business types
    selected_types = hub_config.selected_business_types or []
    if selected_types:
        cloud_api_url = _get_cloud_api_url()
        for type_code in selected_types:
            try:
                resp = _get_session().get(
                    f"{cloud_api_url}/api/blueprints/types/{type_code}/",
                    headers={'Accept': 'application/json'},
                    timeout=15,
                )
                if resp.status_code == 200:
                    roles_data = resp.json().get('roles', [])
                    if roles_data:
                        PermissionService.create_blueprint_roles(hub_id, roles_data)
                        logger.info("[AUTO ROLES] Created roles for business type %s: %s",
                                    type_code, [r.get('id') for r in roles_data])
            except Exception as e:
                logger.warning("[AUTO ROLES] Failed for business type %s: %s", type_code, e)


# Products list with DataTable pagination

@login_required
def products_list(request, store_type):
    """
    HTMX endpoint: Fetch and render products with DataTable pagination.
    Returns HTML partial with product cards or table rows.
    Supports filters: q (search), sector, type, page, sort, dir, view
    """
    from apps.configuration.models import HubConfig

    # Get filters from query params
    search_query = request.GET.get('q', '').strip()
    sector_filter = request.GET.get('sector', '').strip()
    type_filter = request.GET.get('type', '').strip()
    industry_filter = request.GET.get('industry', '').strip()
    solution_filter = request.GET.get('solution', '').strip()
    status_filter = request.GET.get('status', '').strip()
    sort_field = request.GET.get('sort', 'name')
    sort_dir = request.GET.get('dir', 'asc')
    current_view = request.GET.get('view', 'cards')
    try:
        per_page = int(request.GET.get('per_page', 12))
    except (ValueError, TypeError):
        per_page = 12
    if per_page not in MARKETPLACE_PER_PAGE_CHOICES:
        per_page = 12
    page_number = request.GET.get('page', 1)

    config = get_store_config(store_type)

    if store_type == 'modules':
        return _fetch_modules_list(request, search_query, sector_filter, type_filter, sort_field, sort_dir, current_view, per_page, page_number, industry_filter, solution_filter, status_filter)
    elif store_type == 'hubs':
        return _fetch_hubs_list(request, search_query, '', 12)
    else:
        # Coming soon stores
        html = render_to_string('marketplace/partials/coming_soon.html', {
            'store_type': store_type,
            'store_config': config,
        }, request=request)
        return HttpResponse(html)


def _fetch_all_modules():
    """Fetch all modules from Cloud API (cached).

    Returns:
        tuple: (modules_list or None, error_message or None)
    """
    cached = cache.get(_CK_MODULES_LIST)
    if cached is not None:
        return cached, None

    from apps.configuration.models import HubConfig
    hub_config = HubConfig.get_solo()
    auth_token = hub_config.hub_jwt or hub_config.cloud_api_token

    if not auth_token:
        return None, str(_('Hub not connected to Cloud. Please connect in Settings.'))

    cloud_api_url = getattr(django_settings, 'CLOUD_API_URL', 'https://erplora.com')
    headers = {'Accept': 'application/json', 'X-Hub-Token': auth_token}

    try:
        response = _get_session().get(
            f"{cloud_api_url}/api/marketplace/modules/",
            headers=headers,
            timeout=30,
        )
        if response.status_code != 200:
            logger.warning(f"[MARKETPLACE] Cloud API returned {response.status_code}")
            return None, str(_('Could not load modules from Cloud (error %(code)s). Please try again.') % {'code': response.status_code})

        data = response.json()
        modules = data.get('results', data) if isinstance(data, dict) else data
        if not isinstance(modules, list):
            modules = []
        cache.set(_CK_MODULES_LIST, modules, _CACHE_TTL)
        return modules, None
    except requests.exceptions.ConnectionError as e:
        logger.error(f"[MARKETPLACE] Connection error fetching modules: {e}")
        return None, str(_('Connection error. Please check your internet connection and try again.'))
    except requests.exceptions.Timeout as e:
        logger.error(f"[MARKETPLACE] Timeout fetching modules: {e}")
        return None, str(_('Cloud is taking too long to respond. Please try again.'))
    except requests.exceptions.RequestException as e:
        logger.error(f"[MARKETPLACE] Error fetching modules: {e}")
        return None, str(_('Could not connect to Cloud. Please try again.'))


def _fetch_modules_list(request, search_query, sector_filter, type_filter, sort_field, sort_dir, current_view, per_page, page_number, industry_filter='', solution_filter='', status_filter=''):
    """Fetch modules from Cloud API with DataTable pagination"""
    from django.core.paginator import Paginator

    installed_module_ids = _get_installed_module_ids()

    modules, error = _fetch_all_modules()
    if modules is None:
        html = render_to_string('marketplace/partials/error.html', {
            'error': error or 'Unknown error'
        }, request=request)
        return HttpResponse(html)

    # Work on a copy so cache stays clean
    modules = [dict(m) for m in modules]

    # Apply filters
    if search_query:
        query_lower = search_query.lower()
        modules = [m for m in modules if (
            query_lower in m.get('name', '').lower() or
            query_lower in m.get('description', '').lower() or
            any(query_lower in str(tag).lower() for tag in m.get('tags', []))
        )]

    if sector_filter:
        sector_slugs = [s.strip() for s in sector_filter.split(',') if s.strip()]
        if sector_slugs:
            # Filter modules by sector membership
            modules = [m for m in modules if any(
                ss in m.get('sectors', []) or ss in m.get('sector_slugs', [])
                for ss in sector_slugs
            )]

    if industry_filter:
        industry_codes = [c.strip() for c in industry_filter.split(',') if c.strip()]
        if industry_codes:
            industry_set = set(industry_codes)
            modules = [m for m in modules if industry_set & set(m.get('business_types', []))]

    if solution_filter:
        solution_codes = [c.strip() for c in solution_filter.split(',') if c.strip()]
        if solution_codes:
            solution_set = set(solution_codes)
            modules = [m for m in modules if m.get('functional_unit', '') in solution_set]

    if type_filter:
        modules = [m for m in modules if m.get('module_type') == type_filter]

    # Mark installed
    for module in modules:
        module['is_installed'] = module.get('slug', '') in installed_module_ids or module.get('module_id', '') in installed_module_ids

    # Filter by installation status
    if status_filter == 'installed':
        modules = [m for m in modules if m.get('is_installed')]
    elif status_filter == 'not_installed':
        modules = [m for m in modules if not m.get('is_installed')]

    # Check updates and add URLs
    for module in modules:
        module['has_update'] = False
        if module['is_installed']:
            mod_id = module.get('module_id', '') or module.get('slug', '')
            installed_version = _get_installed_module_version(mod_id)
            cloud_version = module.get('version', '')
            if installed_version and cloud_version and installed_version != cloud_version:
                module['has_update'] = True
                module['installed_version'] = installed_version
        module['detail_url'] = reverse('marketplace:module_detail', kwargs={'slug': module.get('slug', '')})
        if not module.get('download_url'):
            module['download_url'] = f"{_get_cloud_api_url()}/api/marketplace/modules/{module.get('slug', '')}/download/"

    # Sort
    sort_key_map = {
        'name': lambda m: m.get('name', '').lower(),
        'price': lambda m: float(m.get('price', 0)),
        'rating': lambda m: float(m.get('rating', 0)),
    }
    sort_fn = sort_key_map.get(sort_field, sort_key_map['name'])
    modules.sort(key=sort_fn, reverse=(sort_dir == 'desc'))

    # Page-based pagination
    paginator = Paginator(modules, per_page if per_page > 0 else max(len(modules), 1))
    page_obj = paginator.get_page(page_number)

    html = render_to_string('marketplace/partials/products_grid.html', {
        'products': page_obj,
        'page_obj': page_obj,
        'store_type': 'modules',
        'search_query': search_query,
        'sector_filter': sector_filter,
        'type_filter': type_filter,
        'sort_field': sort_field,
        'sort_dir': sort_dir,
        'current_view': current_view,
        'per_page': per_page,
    }, request=request)

    return HttpResponse(html)


def _fetch_hubs_list(request, search_query, cursor, page_size):
    """Fetch hubs - placeholder for now"""
    # TODO: Implement hub fetching from Cloud API
    hubs = [
        {
            'id': 'hub-demo-1',
            'name': 'Demo Hub Europe',
            'slug': 'demo-hub-eu',
            'description': 'A demo hub instance in Europe region',
            'price': 0,
            'is_free': True,
            'icon': 'server-outline',
            'region': 'eu',
            'plan': 'free',
        },
        {
            'id': 'hub-pro-1',
            'name': 'Professional Hub',
            'slug': 'pro-hub',
            'description': 'Professional hub with advanced features',
            'price': 29.99,
            'is_free': False,
            'icon': 'server-outline',
            'region': 'eu',
            'plan': 'pro',
        },
    ]

    if search_query:
        query_lower = search_query.lower()
        hubs = [h for h in hubs if query_lower in h['name'].lower()]

    html = render_to_string('marketplace/partials/products_grid.html', {
        'products': hubs,
        'store_type': 'hubs',
        'has_more': False,
        'next_cursor': '',
    }, request=request)

    return HttpResponse(html)


# Module Detail View

@login_required
@htmx_view('marketplace/pages/marketplace.html', 'marketplace/partials/module_detail_content.html')
def module_detail(request, slug):
    """
    Module detail page view.
    Fetches module details from Cloud API.
    """
    from apps.configuration.models import HubConfig

    hub_config = HubConfig.get_solo()
    auth_token = hub_config.hub_jwt or hub_config.cloud_api_token

    if not auth_token:
        return {
            'current_section': 'marketplace',
            'error': 'Hub not connected to Cloud. Please connect in Settings.',
        }

    installed_module_ids = _get_installed_module_ids()

    cloud_api_url = _get_cloud_api_url()
    headers = {'Accept': 'application/json', 'X-Hub-Token': auth_token}

    try:
        # Fetch module details from Cloud API (cached)
        cache_key = f"{_CK_MODULE_DETAIL}{slug}"
        module = cache.get(cache_key)
        if module is None:
            response = _get_session().get(
                f"{cloud_api_url}/api/marketplace/modules/{slug}/",
                headers=headers,
                timeout=30
            )

            if response.status_code == 404:
                return {
                    'current_section': 'marketplace',
                    'error': f'Module "{slug}" not found.',
                }

            if response.status_code != 200:
                return {
                    'current_section': 'marketplace',
                    'error': f'Cloud API returned {response.status_code}',
                }

            module = response.json()
            cache.set(cache_key, module, _CACHE_TTL)

        # Check if installed (compare both slug and module_id)
        is_installed = slug in installed_module_ids or module.get('module_id', '') in installed_module_ids

        # Check if update available (compare local version vs Cloud version)
        has_update = False
        installed_version = None
        cloud_version = module.get('version', '')
        if is_installed:
            mod_id = module.get('module_id', '') or slug
            installed_version = _get_installed_module_version(mod_id)
            if installed_version and cloud_version and installed_version != cloud_version:
                has_update = True

        # Check ownership (from API response or via check_ownership endpoint)
        is_owned = module.get('is_owned', False)
        if not is_owned:
            try:
                ownership_response = _get_session().get(
                    f"{cloud_api_url}/api/marketplace/modules/{module.get('id', '')}/check_ownership/",
                    headers=headers,
                    timeout=10
                )
                if ownership_response.status_code == 200:
                    ownership_data = ownership_response.json()
                    is_owned = ownership_data.get('is_owned', False)
            except Exception:
                pass

        # Determine if free
        is_free = module.get('module_type') == 'free' or module.get('price', 0) == 0

        # Related modules (same category) — use cached modules list
        related_modules = []
        all_modules, _ = _fetch_all_modules()
        if all_modules:
            category = module.get('category', '')
            related_modules = [
                m for m in all_modules
                if m.get('category') == category and m.get('slug') != slug
            ][:3]

        return {
            'current_section': 'marketplace',
            'page_title': module.get('name', 'Module Details'),
            'module': module,
            'is_installed': is_installed,
            'has_update': has_update,
            'installed_version': installed_version,
            'is_owned': is_owned,
            'is_free': is_free,
            'related_modules': related_modules,
            'back_url': reverse('marketplace:index'),
            'navigation': _marketplace_navigation('modules'),
        }

    except requests.exceptions.RequestException as e:
        return {
            'current_section': 'marketplace',
            'error': f'Failed to connect to Cloud: {str(e)}',
        }


# --- Functional Units views (replaces Solutions) ---


def _fetch_functional_unit_modules(slug, cloud_api_url):
    """Fetch module list for a single functional unit from Cloud API (cached)."""
    cache_key = f"{_CK_FU_DETAIL}{slug}"
    cached = cache.get(cache_key)
    if cached is not None:
        return slug, cached

    try:
        r = _get_session().get(
            f"{cloud_api_url}/api/blueprints/functional-units/{slug}/",
            headers={'Accept': 'application/json'}, timeout=15,
        )
        if r.status_code == 200:
            modules = r.json().get('modules', [])
            cache.set(cache_key, modules, _CACHE_TTL)
            return slug, modules
    except Exception:
        pass
    return slug, []


@login_required
def solutions_bulk_install(request):
    """POST: Install multiple functional unit blocks at once."""
    if request.method != 'POST':
        return HttpResponse(status=405)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return HttpResponse(
            json.dumps({'success': False, 'error': 'Invalid JSON'}),
            content_type='application/json', status=400,
        )

    block_slugs = data.get('block_slugs', [])
    if not block_slugs:
        return HttpResponse(
            json.dumps({'success': False, 'error': 'No blocks specified'}),
            content_type='application/json', status=400,
        )

    from apps.configuration.models import HubConfig
    hub_config = HubConfig.get_config()
    active_types = list(hub_config.selected_business_types or [])
    for slug in block_slugs:
        if slug not in active_types:
            active_types.append(slug)
    hub_config.selected_business_types = active_types
    hub_config.save(update_fields=['selected_business_types'])

    from apps.core.services.module_install_service import ModuleInstallService
    hub_token = ModuleInstallService.get_hub_token(hub_config)
    result = ModuleInstallService.install_block_modules(block_slugs, hub_config)

    if result.installed > 0:
        _invalidate_installed_cache()
        installed_slugs = [r.module_id for r in result.results if r.success]
        if installed_slugs:
            ModuleInstallService.notify_cloud_installations(
                installed_slugs, hub_token,
            )
        ModuleInstallService.run_post_install(
            load_all=True, run_migrations=True, schedule_restart=True,
        )

    # Create default roles + blueprint roles from selected business types
    if hub_config.hub_id:
        from apps.core.services.permission_service import PermissionService
        hub_id = str(hub_config.hub_id)
        PermissionService.create_default_roles(hub_id)
        PermissionService.sync_all_module_permissions(hub_id)
        # Create roles from all selected business types
        all_types = list(hub_config.selected_business_types or [])
        cloud_api_url = _get_cloud_api_url()
        for type_code in all_types:
            try:
                resp = _get_session().get(
                    f"{cloud_api_url}/api/blueprints/types/{type_code}/",
                    headers={'Accept': 'application/json'}, timeout=15,
                )
                if resp.status_code == 200:
                    roles_data = resp.json().get('roles', [])
                    if roles_data:
                        PermissionService.create_blueprint_roles(hub_id, roles_data)
                        logger.info("Created roles for business type %s", type_code)
            except Exception as e:
                logger.warning("Failed to create roles for business type %s: %s", type_code, e)

    return HttpResponse(json.dumps({
        'success': True,
        'installed': result.installed,
        'errors': result.errors,
        'server_restarting': result.installed > 0,
    }), content_type='application/json')


@login_required
def modules_bulk_install(request):
    """POST: Install multiple modules at once.

    All modules (free and premium) install the same way.
    Premium modules are gated by ModuleSubscriptionMiddleware when the
    user opens them — no purchase check at install time.
    """
    if request.method != 'POST':
        return HttpResponse(status=405)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return HttpResponse(
            json.dumps({'success': False, 'error': 'Invalid JSON'}),
            content_type='application/json', status=400,
        )

    modules = data.get('modules', [])
    if not modules:
        return HttpResponse(
            json.dumps({'success': False, 'error': 'No modules specified'}),
            content_type='application/json', status=400,
        )

    from apps.core.services.module_install_service import ModuleInstallService
    hub_token = ModuleInstallService.get_hub_token()
    cloud_api_url = _get_cloud_api_url()

    cache.delete(_CK_MODULES_LIST)
    all_cloud_modules, _ = _fetch_all_modules()
    all_cloud_modules = all_cloud_modules or []
    catalog = {m.get('slug') or m.get('module_id'): m for m in all_cloud_modules}

    modules_to_install = []

    for m in modules:
        slug = m.get('slug')
        if not slug:
            continue

        cloud_mod = catalog.get(slug)
        if cloud_mod and not cloud_mod.get('is_active', True):
            continue
        modules_to_install.append({
            'slug': slug,
            'name': (cloud_mod or {}).get('name', m.get('name', slug)),
            'download_url': (cloud_mod or {}).get('download_url')
                or f"{cloud_api_url}/api/marketplace/modules/{slug}/download/",
        })

    # Resolve transitive dependencies
    if modules_to_install:
        installed_ids = set(_get_installed_module_ids())
        all_slugs = {m['slug'] for m in modules_to_install}
        dep_modules = ModuleInstallService._resolve_dependencies(
            all_slugs, installed_ids, cloud_api_url, hub_token
        )
        if dep_modules:
            for dep in dep_modules:
                modules_to_install.append(dep)

            logger.info(
                "[BULK INSTALL] Adding %d dependency modules: %s",
                len(dep_modules), [d['slug'] for d in dep_modules],
            )

    installed_count = 0
    errors = []

    if modules_to_install:
        logger.info(
            "[BULK INSTALL] Installing %d modules: %s",
            len(modules_to_install),
            [m['slug'] for m in modules_to_install],
        )

        result = ModuleInstallService.bulk_download_and_install(modules_to_install, hub_token)
        installed_count = result.installed
        errors = result.errors

        logger.info(
            "[BULK INSTALL] Result: installed=%d, errors=%s",
            result.installed, result.errors,
        )

        if result.installed > 0:
            _invalidate_installed_cache()
            installed_slugs = [m['slug'] for m in modules_to_install]
            ModuleInstallService.notify_cloud_installations(
                installed_slugs, hub_token,
            )
            ModuleInstallService.run_post_install(
                load_all=True, run_migrations=True, schedule_restart=True,
            )
            _create_roles_for_installed_modules(installed_slugs)

    return HttpResponse(json.dumps({
        'success': True,
        'installed': installed_count,
        'errors': errors,
        'server_restarting': installed_count > 0,
    }), content_type='application/json')


@login_required
@htmx_view('marketplace/pages/marketplace.html', 'marketplace/partials/solution_detail_content.html')
def solution_detail(request, slug):
    """Functional unit detail — shows modules, roles, and activate/deactivate button."""
    cloud_api_url = _get_cloud_api_url()
    installed_ids = _get_installed_module_ids()

    try:
        # Cached functional unit detail
        fu_cache_key = f"{_CK_FU_DETAIL}{slug}:full"
        solution = cache.get(fu_cache_key)
        if solution is None:
            response = _get_session().get(
                f"{cloud_api_url}/api/blueprints/functional-units/{slug}/",
                headers={'Accept': 'application/json'},
                timeout=15,
            )
            if response.status_code == 404:
                return {
                    'current_section': 'marketplace',
                    'error': _('Functional unit not found.'),
                    'navigation': _marketplace_navigation('modules'),
                }
            if response.status_code != 200:
                return {
                    'current_section': 'marketplace',
                    'error': f'Cloud API returned {response.status_code}',
                    'navigation': _marketplace_navigation('modules'),
                }
            solution = response.json()
            cache.set(fu_cache_key, solution, _CACHE_TTL)

        # Check if this functional unit is active
        from apps.configuration.models import HubConfig
        hub_config = HubConfig.get_config()
        active_types = set(hub_config.selected_business_types or [])
        is_block_active = slug in active_types

        # Split modules into required/optional and mark installed
        required_modules = []
        optional_modules = []
        all_installed = True
        for mod in solution.get('modules', []):
            mod['is_installed'] = mod.get('slug', '') in installed_ids or mod.get('module_id', '') in installed_ids
            if mod.get('role') == 'required':
                required_modules.append(mod)
                if not mod['is_installed']:
                    all_installed = False
            else:
                optional_modules.append(mod)

        return {
            'current_section': 'marketplace',
            'page_title': solution.get('name', 'Functional Unit'),
            'solution': solution,
            'required_modules': required_modules,
            'optional_modules': optional_modules,
            'all_installed': all_installed,
            'is_block_active': is_block_active,
            'back_url': reverse('marketplace:index'),
            'navigation': _marketplace_navigation('modules'),
        }

    except requests.exceptions.RequestException as e:
        return {
            'current_section': 'marketplace',
            'error': f'Failed to connect to Cloud: {str(e)}',
            'navigation': _marketplace_navigation('modules'),
        }


@login_required
def solution_install(request, slug):
    """POST: Install all required modules from a functional unit."""
    if request.method != 'POST':
        return HttpResponse(status=405)

    cloud_api_url = _get_cloud_api_url()
    installed_ids = _get_installed_module_ids()

    try:
        # Fetch functional unit detail to get modules
        response = _get_session().get(
            f"{cloud_api_url}/api/blueprints/functional-units/{slug}/",
            headers={'Accept': 'application/json'},
            timeout=15,
        )
        if response.status_code != 200:
            return HttpResponse(
                json.dumps({'success': False, 'error': 'Functional unit not found'}),
                content_type='application/json', status=404,
            )

        solution = response.json()
        required_modules = [
            m for m in solution.get('modules', [])
            if m.get('role') == 'required' and m.get('slug', '') not in installed_ids and m.get('module_id', '') not in installed_ids
        ]

        if not required_modules:
            return HttpResponse(
                json.dumps({'success': True, 'message': str(_('All modules are already installed.')), 'installed': 0}),
                content_type='application/json',
            )

        # Install modules via ModuleInstallService (parallel bulk download)
        from apps.core.services.module_install_service import ModuleInstallService
        from apps.configuration.models import HubConfig
        hub_config = HubConfig.get_solo()
        hub_token = ModuleInstallService.get_hub_token(hub_config)

        modules_to_install = [
            {
                'slug': mod['slug'],
                'name': mod.get('name', mod['slug']),
                'download_url': f"{cloud_api_url}/api/marketplace/modules/{mod['slug']}/download/",
            }
            for mod in required_modules
        ]

        # Resolve transitive dependencies
        installed_set = set(installed_ids)
        all_slugs = {m['slug'] for m in modules_to_install}
        dep_modules = ModuleInstallService._resolve_dependencies(
            all_slugs, installed_set, cloud_api_url, hub_token
        )
        if dep_modules:
            modules_to_install.extend(dep_modules)

        bulk_result = ModuleInstallService.bulk_download_and_install(
            modules_to_install, hub_token
        )
        installed_count = bulk_result.installed
        errors = bulk_result.errors

        # Post-install: load, migrate, create roles
        if installed_count > 0:
            _invalidate_installed_cache()
            installed_slugs = [m['slug'] for m in modules_to_install]
            ModuleInstallService.notify_cloud_installations(
                installed_slugs, hub_token,
            )
            ModuleInstallService.run_post_install(
                load_all=True, run_migrations=True,
                schedule_restart=True,
            )

            # Create roles from functional unit definition
            roles_data = solution.get('roles', [])
            if roles_data and hub_config.hub_id:
                try:
                    from apps.core.services.permission_service import PermissionService
                    PermissionService.create_blueprint_roles(str(hub_config.hub_id), roles_data)
                except Exception as e:
                    logger.warning(f"Failed to create roles for functional unit {slug}: {e}")

        result = {
            'success': True,
            'installed': installed_count,
            'total': len(required_modules),
            'errors': errors,
            'server_restarting': installed_count > 0,
        }
        return HttpResponse(json.dumps(result), content_type='application/json')

    except requests.exceptions.RequestException as e:
        return HttpResponse(
            json.dumps({'success': False, 'error': str(e)}),
            content_type='application/json', status=500,
        )


@login_required
def block_toggle(request, slug):
    """POST: Activate or deactivate a functional unit."""
    if request.method != 'POST':
        return HttpResponse(status=405)

    from apps.configuration.models import HubConfig
    hub_config = HubConfig.get_config()
    active_types = list(hub_config.selected_business_types or [])

    if slug in active_types:
        # Deactivate: remove from list
        active_types.remove(slug)
        hub_config.selected_business_types = active_types
        hub_config.save(update_fields=['selected_business_types'])
        return HttpResponse(
            json.dumps({'success': True, 'action': 'uninstalled', 'slug': slug, 'active_count': len(active_types)}),
            content_type='application/json',
        )
    else:
        # Activate: add to list + install modules + create roles
        active_types.append(slug)
        hub_config.selected_business_types = active_types
        hub_config.save(update_fields=['selected_business_types'])

        # Install required modules for this functional unit
        from apps.core.services.module_install_service import ModuleInstallService
        result = ModuleInstallService.install_block_modules([slug], hub_config)

        if result.installed > 0:
            _invalidate_installed_cache()
            ModuleInstallService.run_post_install(
                load_all=True, run_migrations=True,
                sync_permissions=bool(hub_config.hub_id),
                hub_id=str(hub_config.hub_id) if hub_config.hub_id else None,
                schedule_restart=True,
            )

        # Create roles for this business type
        if hub_config.hub_id:
            cloud_api_url = _get_cloud_api_url()
            try:
                response = _get_session().get(
                    f"{cloud_api_url}/api/blueprints/types/{slug}/",
                    headers={'Accept': 'application/json'},
                    timeout=15,
                )
                if response.status_code == 200:
                    type_data = response.json()
                    roles_data = type_data.get('roles', [])
                    if roles_data:
                        from apps.core.services.permission_service import PermissionService
                        PermissionService.create_blueprint_roles(str(hub_config.hub_id), roles_data)
                        logger.info("Created roles for business type %s: %s",
                                    slug, [r.get('id') for r in roles_data])
            except Exception as e:
                logger.warning(f"Failed to create roles for business type {slug}: {e}")

        return HttpResponse(
            json.dumps({
                'success': True,
                'action': 'installed',
                'slug': slug,
                'active_count': len(active_types),
                'modules_installed': result.installed,
                'install_errors': result.errors,
                'server_restarting': result.installed > 0,
            }),
            content_type='application/json',
        )


# --- Business Types views (informational, from blueprints API) ---

@login_required
@htmx_view('marketplace/pages/marketplace.html', 'marketplace/partials/business_types_content.html')
def business_types_index(request):
    """Business types list — browse by type to see recommended modules and roles."""
    business_types = _fetch_business_types_for_filters()

    return {
        'current_section': 'marketplace',
        'page_title': _('Business Types'),
        'industries': business_types,
        'navigation': _marketplace_navigation('business_types'),
    }


@login_required
@htmx_view('marketplace/pages/marketplace.html', 'marketplace/partials/business_type_detail_content.html')
def business_type_detail(request, slug):
    """Business type detail — shows recommended modules and roles (informational only)."""
    cloud_api_url = getattr(django_settings, 'CLOUD_API_URL', 'https://erplora.com')

    try:
        # Cached business type detail
        type_cache_key = f"{_CK_TYPE_DETAIL}{slug}:full"
        industry = cache.get(type_cache_key)
        if industry is None:
            response = _get_session().get(
                f"{cloud_api_url}/api/blueprints/types/{slug}/",
                headers={'Accept': 'application/json'},
                timeout=15,
            )
            if response.status_code == 404:
                return {
                    'current_section': 'marketplace',
                    'error': _('Business type not found.'),
                    'navigation': _marketplace_navigation('business_types'),
                }
            if response.status_code != 200:
                return {
                    'current_section': 'marketplace',
                    'error': f'Cloud API returned {response.status_code}',
                    'navigation': _marketplace_navigation('business_types'),
                }
            industry = response.json()
            cache.set(type_cache_key, industry, _CACHE_TTL)

        # Work on a copy so cache stays clean
        industry = dict(industry)
        industry['modules'] = [dict(m) for m in industry.get('modules', [])]

        # Mark installed modules
        installed_ids = _get_installed_module_ids()
        for mod in industry.get('modules', []):
            mod['is_installed'] = (
                mod.get('slug', '') in installed_ids
                or mod.get('module_id', '') in installed_ids
            )

        # Check if this business type is active
        from apps.configuration.models import HubConfig
        hub_config = HubConfig.get_config()
        active_types = hub_config.selected_business_types or []
        is_active = slug in active_types

        return {
            'current_section': 'marketplace',
            'page_title': industry.get('name', _('Business Type')),
            'industry': industry,
            'is_active': is_active,
            'back_url': reverse('marketplace:business_types'),
            'navigation': _marketplace_navigation('business_types'),
        }

    except requests.exceptions.RequestException as e:
        return {
            'current_section': 'marketplace',
            'error': f'Failed to connect to Cloud: {str(e)}',
            'navigation': _marketplace_navigation('business_types'),
        }


@login_required
def business_type_activate(request, slug):
    """POST: Activate a business type — installs modules, creates roles, imports seeds."""
    if request.method != 'POST':
        return HttpResponse(status=405)

    from apps.configuration.models import HubConfig
    hub_config = HubConfig.get_config()
    if not hub_config.hub_id:
        return HttpResponse(
            json.dumps({'success': False, 'error': 'Hub not configured'}),
            content_type='application/json', status=400,
        )

    active_types = list(hub_config.selected_business_types or [])
    already_active = slug in active_types

    if not already_active:
        active_types.append(slug)
        hub_config.selected_business_types = active_types
        hub_config.save(update_fields=['selected_business_types'])

    # Create default roles (admin, manager, viewer) if not exist
    from apps.core.services.permission_service import PermissionService
    PermissionService.create_default_roles(str(hub_config.hub_id))

    # Install blueprint: modules + roles + seed products
    from apps.core.services.blueprint_service import BlueprintService
    result = BlueprintService.install_blueprint(hub_config, active_types)
    logger.info("install_blueprint for %s: %s", slug, result)

    # Sync permissions after modules are installed
    PermissionService.sync_all_module_permissions(str(hub_config.hub_id))

    return HttpResponse(json.dumps({
        'success': True,
        'slug': slug,
        'already_active': already_active,
        'modules_installed': result.get('modules_installed', 0),
        'roles_created': result.get('roles_created', 0),
        'seeds_imported': result.get('seeds_imported', 0),
        'server_restarting': result.get('restart_scheduled', False),
    }), content_type='application/json')


# --- Compliance views ---

# Category display labels (keep in sync with Cloud ComplianceRequirement.CATEGORY_CHOICES)
COMPLIANCE_CATEGORY_LABELS = {
    'invoicing': _('Electronic Invoicing'),
    'tax_reporting': _('Tax Reporting'),
    'pos_fiscal': _('POS / Cash Register'),
    'data_protection': _('Data Protection'),
    'accounting': _('Accounting'),
    'other': _('Other'),
}

COMPLIANCE_CATEGORY_ICONS = {
    'invoicing': 'document-text-outline',
    'tax_reporting': 'calculator-outline',
    'pos_fiscal': 'card-outline',
    'data_protection': 'shield-outline',
    'accounting': 'book-outline',
    'other': 'ellipsis-horizontal-outline',
}


def _get_compliance_data():
    """
    Local compliance data — regulatory modules required per country.
    module_id: the module_id of the ERPlora module that covers this requirement, or None.
    """
    return [
        {
            'country_code': 'ES',
            'country_name': 'España',
            'description': 'España tiene requisitos nacionales (VeriFactu, SII) y regionales (TicketBAI en País Vasco). También se prevé facturación electrónica B2B obligatoria.',
            'requirements': [
                {
                    'name': 'VeriFactu',
                    'description': 'Sistema antifraude de facturación electrónica. Requiere software certificado que garantice integridad, inmutabilidad y trazabilidad de los registros de facturación.',
                    'module_id': 'verifactu',
                    'region': '',
                },
                {
                    'name': 'SII',
                    'description': 'Suministro Inmediato de Información. Comunicación electrónica en tiempo real de datos de IVA a la AEAT.',
                    'module_id': 'sii',
                    'region': '',
                },
                {
                    'name': 'TicketBAI',
                    'description': 'Sistema de facturación regional del País Vasco. Cada factura se firma digitalmente y se encadena con la anterior.',
                    'module_id': None,
                    'region': 'País Vasco (Álava, Gipuzkoa, Bizkaia)',
                },
                {
                    'name': 'Factura-e B2B',
                    'description': 'Facturación electrónica B2B obligatoria en formato estructurado EN 16931.',
                    'module_id': 'facturae_b2b',
                    'region': '',
                },
            ],
        },
        {
            'country_code': 'PT',
            'country_name': 'Portugal',
            'description': 'Portugal requiere software de facturación certificado (SAF-T) para todas las empresas. Códigos QR y ATCUD obligatorios en todas las facturas.',
            'requirements': [
                {
                    'name': 'SAF-T PT',
                    'description': 'Envío mensual del fichero SAF-T de facturación a la Autoridade Tributária. Requiere software certificado por la AT.',
                    'module_id': None,
                    'region': '',
                },
                {
                    'name': 'ATCUD',
                    'description': 'Código único de documento (ATCUD) y código QR obligatorios en todas las facturas.',
                    'module_id': None,
                    'region': '',
                },
            ],
        },
        {
            'country_code': 'FR',
            'country_name': 'Francia',
            'description': 'Francia requiere certificación NF525/LNE para todo software de TPV. La facturación electrónica B2B obligatoria entra en vigor desde septiembre de 2026.',
            'requirements': [
                {
                    'name': 'NF525 TPV',
                    'description': 'Certificación antifraude IVA para software de TPV/caja registradora.',
                    'module_id': None,
                    'region': '',
                },
                {
                    'name': 'Facture-X B2B',
                    'description': 'Facturación electrónica B2B obligatoria a través de plataformas certificadas (PDP).',
                    'module_id': None,
                    'region': '',
                },
            ],
        },
        {
            'country_code': 'IT',
            'country_name': 'Italia',
            'description': 'Italia tiene un sistema centralizado de facturación electrónica (SDI) obligatorio para todas las empresas desde 2019.',
            'requirements': [
                {
                    'name': 'FatturaPA',
                    'description': 'Sistema centralizado de facturación electrónica. Todas las facturas en formato FatturaPA XML transmitidas a través de SDI.',
                    'module_id': None,
                    'region': '',
                },
                {
                    'name': 'Corrispettivi',
                    'description': 'Cajas registradoras electrónicas certificadas para comercio minorista.',
                    'module_id': None,
                    'region': '',
                },
            ],
        },
        {
            'country_code': 'DE',
            'country_name': 'Alemania',
            'description': 'Alemania requiere TSE certificado para todas las cajas registradoras electrónicas. La facturación electrónica B2B se está implementando.',
            'requirements': [
                {
                    'name': 'TSE KassenSichV',
                    'description': 'Todas las cajas registradoras electrónicas deben tener un TSE certificado que registra y firma digitalmente cada transacción.',
                    'module_id': None,
                    'region': '',
                },
                {
                    'name': 'XRechnung',
                    'description': 'Facturación electrónica B2B obligatoria en formatos EN 16931.',
                    'module_id': None,
                    'region': '',
                },
            ],
        },
        {
            'country_code': 'PL',
            'country_name': 'Polonia',
            'description': 'Polonia implementa KSeF, una plataforma gubernamental centralizada de facturación electrónica obligatoria.',
            'requirements': [
                {
                    'name': 'KSeF',
                    'description': 'Plataforma gubernamental centralizada de facturación electrónica. Formato XML FA(3) obligatorio.',
                    'module_id': None,
                    'region': '',
                },
            ],
        },
        {
            'country_code': 'GR',
            'country_name': 'Grecia',
            'description': 'Grecia implementa facturación electrónica B2B obligatoria a través de la plataforma myDATA.',
            'requirements': [
                {
                    'name': 'myDATA',
                    'description': 'Facturación electrónica B2B obligatoria via myDATA.',
                    'module_id': None,
                    'region': '',
                },
            ],
        },
        {
            'country_code': 'RO',
            'country_name': 'Rumanía',
            'description': 'Rumanía tiene facturación electrónica obligatoria (RO e-Factura) para todas las transacciones B2B y B2C.',
            'requirements': [
                {
                    'name': 'e-Factura RO',
                    'description': 'Facturación electrónica obligatoria a través de la plataforma RO e-Factura.',
                    'module_id': None,
                    'region': '',
                },
                {
                    'name': 'SAF-T RO',
                    'description': 'Fichero estándar de auditoría fiscal, enviado electrónicamente mediante Declaración Informativa D406 a ANAF.',
                    'module_id': None,
                    'region': '',
                },
            ],
        },
        {
            'country_code': 'HU',
            'country_name': 'Hungría',
            'description': 'Hungría tiene informes de facturas en tiempo real (RTIR) obligatorios para todos los contribuyentes de IVA.',
            'requirements': [
                {
                    'name': 'NAV Online',
                    'description': 'Comunicación en tiempo real de datos de facturas a NAV mediante el sistema Online Számla.',
                    'module_id': None,
                    'region': '',
                },
            ],
        },
        {
            'country_code': 'BE',
            'country_name': 'Bélgica',
            'description': 'Bélgica obliga a la facturación electrónica B2B a través de Peppol desde enero de 2026.',
            'requirements': [
                {
                    'name': 'Peppol BE',
                    'description': 'Facturación electrónica B2B estructurada obligatoria en formato EN 16931 a través de la red Peppol.',
                    'module_id': None,
                    'region': '',
                },
            ],
        },
        {
            'country_code': 'AT',
            'country_name': 'Austria',
            'description': 'Austria requiere cajas registradoras a prueba de manipulaciones (RKSV) con unidades de firma digital.',
            'requirements': [
                {
                    'name': 'RKSV',
                    'description': 'Cajas registradoras a prueba de manipulaciones con unidades de firma digital.',
                    'module_id': None,
                    'region': '',
                },
            ],
        },
        {
            'country_code': 'HR',
            'country_name': 'Croacia',
            'description': 'Croacia implementa Fiscalización 2.0 con facturación electrónica B2B obligatoria e informes en tiempo real.',
            'requirements': [
                {
                    'name': 'Fiscalización HR',
                    'description': 'Facturación electrónica B2B y B2G obligatoria e informes en tiempo real.',
                    'module_id': None,
                    'region': '',
                },
            ],
        },
    ]


@login_required
@htmx_view('marketplace/pages/marketplace.html', 'marketplace/partials/compliance_content.html')
def compliance_index(request):
    """Country compliance — local data, no Cloud dependency."""
    installed_ids = _get_installed_module_ids()
    countries = _get_compliance_data()

    # Mark which modules exist (installed locally)
    for country in countries:
        supported = 0
        for req in country['requirements']:
            module_id = req.get('module_id')
            if module_id and module_id in installed_ids:
                req['is_available'] = True
                req['is_installed'] = True
                supported += 1
            elif module_id:
                # Module exists in ERPlora but not installed on this Hub
                req['is_available'] = True
                req['is_installed'] = False
                supported += 1
            else:
                req['is_available'] = False
                req['is_installed'] = False
        country['supported_count'] = supported
        country['requirement_count'] = len(country['requirements'])

    from apps.configuration.models import HubConfig
    hub_config = HubConfig.get_config()

    return {
        'current_section': 'marketplace',
        'page_title': _('Compliance'),
        'countries': countries,
        'hub_country': hub_config.country_code,
        'navigation': _marketplace_navigation('compliance'),
    }


@login_required
def compliance_detail(request, country_code):
    """Redirect to the main compliance page (accordion view)."""
    from django.shortcuts import redirect
    return redirect('marketplace:compliance')


# =============================================================================
# Module Pricing Page (Bouncer redirect target)
# =============================================================================

@login_required
@htmx_view('marketplace/pages/marketplace.html', 'marketplace/partials/module_pricing_content.html')
def module_pricing(request, module_id):
    """
    Pricing page for a premium module.

    Users land here when the ModuleSubscriptionMiddleware redirects them
    because they haven't paid for a premium module.
    """
    from apps.core.middleware.module_subscription import (
        _get_module_pricing, get_subscription_status,
    )

    # Read module metadata from module.py
    modules_dir = Path(django_settings.MODULES_DIR)
    module_name = module_id
    module_icon = 'cube-outline'
    module_description = ''
    tiers = []
    price_monthly = 0
    default_tier_slug = ''

    module_py = modules_dir / module_id / 'module.py'
    if module_py.exists():
        try:
            import importlib.util
            spec = importlib.util.spec_from_file_location(
                f'{module_id}.module', module_py,
            )
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)

            module_name = str(getattr(mod, 'MODULE_NAME', module_id))
            module_icon = getattr(mod, 'MODULE_ICON', 'cube-outline')
            menu = getattr(mod, 'MENU', {})
            if menu and isinstance(menu, dict):
                module_icon = menu.get('icon', module_icon)

            pricing = getattr(mod, 'PRICING', {})
            if pricing:
                price_monthly = pricing.get('subscription_price_monthly', 0)

            module_description = str(getattr(mod, 'MODULE_DESCRIPTION', ''))
        except Exception:
            pass

    # Also try Cloud API for richer data (tiers, description, etc.)
    cloud_api_url = _get_cloud_api_url()
    try:
        cache_key = f'{_CK_MODULE_DETAIL}{module_id}'
        cloud_module = cache.get(cache_key)
        if cloud_module is None:
            from apps.configuration.models import HubConfig
            hub_config = HubConfig.get_solo()
            auth_token = hub_config.hub_jwt or hub_config.cloud_api_token
            if auth_token:
                resp = _get_session().get(
                    f'{cloud_api_url}/api/marketplace/modules/{module_id}/',
                    headers={'X-Hub-Token': auth_token, 'Accept': 'application/json'},
                    timeout=10,
                )
                if resp.status_code == 200:
                    cloud_module = resp.json()
                    cache.set(cache_key, cloud_module, _CACHE_TTL)

        if cloud_module:
            module_name = cloud_module.get('name', module_name)
            module_description = cloud_module.get('description', module_description)
            if cloud_module.get('assistant_tiers'):
                tiers = cloud_module['assistant_tiers']
                default_tier_slug = tiers[0].get('slug', '') if tiers else ''
            elif cloud_module.get('subscription_price_monthly'):
                price_monthly = cloud_module['subscription_price_monthly']
            elif cloud_module.get('price'):
                price_monthly = cloud_module['price']
    except Exception:
        pass

    # Get current subscription status
    subscription_status = get_subscription_status(module_id)
    show_trial = subscription_status not in ('expired',)  # No trial for returning users

    # Calculate yearly savings if applicable
    price_yearly = None
    yearly_savings = 0
    if price_monthly and not tiers:
        price_yearly = round(float(price_monthly) * 10, 2)  # 2 months free
        yearly_savings = round((1 - (price_yearly / (float(price_monthly) * 12))) * 100)

    return {
        'current_section': 'marketplace',
        'page_title': f'{module_name} — {_("Pricing")}',
        'content_template': 'marketplace/partials/module_pricing_content.html',
        'module_id': module_id,
        'module_name': module_name,
        'module_icon': module_icon,
        'module_description': module_description,
        'tiers': tiers,
        'default_tier_slug': default_tier_slug,
        'price_monthly': price_monthly,
        'price_yearly': price_yearly,
        'yearly_savings': yearly_savings,
        'subscription_status': subscription_status,
        'show_trial': show_trial,
    }


@login_required
def module_subscribe(request):
    """
    Create a Stripe Checkout session for a module subscription.

    POST payload:
    - module_id: the module directory name (e.g., 'tobacco')
    - tier_slug: optional tier for tiered pricing (e.g., 'basic', 'pro')
    """
    if request.method != 'POST':
        return HttpResponse(status=405)

    try:
        data = json.loads(request.body)
        module_id = data.get('module_id', '')
        tier_slug = data.get('tier_slug', '')
    except (json.JSONDecodeError, ValueError):
        return HttpResponse(
            json.dumps({'success': False, 'error': 'Invalid data'}),
            content_type='application/json', status=400,
        )

    if not module_id:
        return HttpResponse(
            json.dumps({'success': False, 'error': 'Missing module_id'}),
            content_type='application/json', status=400,
        )

    from apps.configuration.models import HubConfig
    hub_config = HubConfig.get_solo()
    auth_token = hub_config.hub_jwt or hub_config.cloud_api_token

    if not auth_token:
        return HttpResponse(
            json.dumps({'success': False, 'error': str(_('Hub not connected to Cloud.'))}),
            content_type='application/json', status=400,
        )

    cloud_api_url = _get_cloud_api_url()

    try:
        purchase_payload = {
            'success_url': request.build_absolute_uri(f'/m/{module_id}/?subscription=success'),
            'cancel_url': request.build_absolute_uri(f'/marketplace/pricing/{module_id}/'),
            'ui_mode': 'embedded',
        }
        if tier_slug:
            purchase_payload['tier_slug'] = tier_slug

        response = _get_session().post(
            f'{cloud_api_url}/api/marketplace/modules/{module_id}/purchase/',
            json=purchase_payload,
            headers={
                'X-Hub-Token': auth_token,
                'Content-Type': 'application/json',
            },
            timeout=30,
        )

        if response.status_code in (200, 201):
            resp_data = response.json()

            # Invalidate subscription cache on successful purchase
            from apps.core.middleware.module_subscription import invalidate_subscription_cache
            invalidate_subscription_cache(module_id)

            if resp_data.get('client_secret'):
                return HttpResponse(
                    json.dumps({
                        'success': True,
                        'client_secret': resp_data['client_secret'],
                        'session_id': resp_data.get('session_id', ''),
                        'stripe_publishable_key': resp_data.get('stripe_publishable_key', ''),
                    }),
                    content_type='application/json',
                )
            elif resp_data.get('checkout_url'):
                return HttpResponse(
                    json.dumps({
                        'success': True,
                        'checkout_url': resp_data['checkout_url'],
                    }),
                    content_type='application/json',
                )
            else:
                return HttpResponse(
                    json.dumps({
                        'success': True,
                        'message': resp_data.get('message', str(_('Subscription processed.'))),
                    }),
                    content_type='application/json',
                )

        elif response.status_code == 409:
            resp_data = response.json()
            return HttpResponse(
                json.dumps({
                    'success': False,
                    'error': resp_data.get('error', str(_('You already have a subscription.'))),
                }),
                content_type='application/json', status=409,
            )
        else:
            error_data = {}
            try:
                error_data = response.json()
            except Exception:
                pass
            return HttpResponse(
                json.dumps({
                    'success': False,
                    'error': error_data.get('error', f'Cloud API returned {response.status_code}'),
                }),
                content_type='application/json', status=500,
            )

    except requests.exceptions.RequestException as e:
        return HttpResponse(
            json.dumps({'success': False, 'error': str(e)}),
            content_type='application/json', status=500,
        )
