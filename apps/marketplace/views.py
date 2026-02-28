"""
Marketplace Views - Multi-store marketplace with sidebar filters and cart

Tabs:
- Modules: Software modules from Cloud marketplace
- Solutions: Pre-configured module bundles
- Compliance: Country-specific required modules
"""
import json
import logging
import requests
from pathlib import Path

from django.http import HttpResponse
from django.template.loader import render_to_string
from django.conf import settings as django_settings
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from apps.core.htmx import htmx_view
from apps.accounts.decorators import login_required

logger = logging.getLogger(__name__)


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
    """Get list of installed module IDs from the modules directory."""
    modules_dir = Path(django_settings.MODULES_DIR)
    installed = []
    if modules_dir.exists():
        for module_dir in modules_dir.iterdir():
            if module_dir.is_dir() and not module_dir.name.startswith('.'):
                installed.append(module_dir.name.lstrip('_'))
    return installed


# Store type configurations
STORE_TYPES = {
    'modules': {
        'name': 'Modules',
        'name_es': 'Módulos',
        'icon': 'cube-outline',
        'api_endpoint': '/api/marketplace/modules/',
        'enabled': True,
        'filters': ['function', 'industry', 'type'],
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
    Main marketplace view with sidebar filters and cart.
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

    # Get cart for this store type
    cart = get_cart(request, store_type)

    return {
        'current_section': 'marketplace',
        'page_title': 'Marketplace',
        'store_type': store_type,
        'store_config': config,
        'store_types': STORE_TYPES,
        'filters': filters_data,
        'cart': cart,
        'cart_count': len(cart.get('items', [])),
        'navigation': _marketplace_navigation('modules'),
    }


def _build_grouped_categories(language):
    """Build grouped categories from local config (fallback when Cloud unavailable)."""
    from config.module_categories import get_all_categories, get_categories_grouped
    groups = get_categories_grouped(language)
    all_cats = {c['id']: c for c in get_all_categories(language)}
    result = []
    for group_key, group_data in groups.items():
        result.append({
            'key': group_key,
            'name': group_data['name'],
            'categories': [all_cats[cid] for cid in group_data['categories'] if cid in all_cats],
        })
    return result


def _build_grouped_industries(language):
    """Build grouped industries from local config (fallback when Cloud unavailable)."""
    from config.module_categories import get_all_industries, get_industries_grouped
    groups = get_industries_grouped(language)
    all_inds = {i['id']: i for i in get_all_industries(language)}
    result = []
    for group_key, group_data in groups.items():
        result.append({
            'key': group_key,
            'name': group_data['name'],
            'industries': [all_inds[iid] for iid in group_data['industries'] if iid in all_inds],
        })
    return result


def _fetch_industries_for_filters():
    """Fetch active industries from Cloud API for the marketplace filter."""
    from apps.configuration.models import HubConfig

    hub_config = HubConfig.get_solo()
    cloud_api_url = getattr(django_settings, 'CLOUD_API_URL', 'https://erplora.com')
    auth_token = hub_config.hub_jwt or hub_config.cloud_api_token

    if not auth_token:
        return []

    try:
        response = requests.get(
            f"{cloud_api_url}/api/marketplace/industries/",
            headers={'Accept': 'application/json', 'X-Hub-Token': auth_token},
            timeout=10,
        )
        if response.status_code == 200:
            return response.json()
    except requests.exceptions.RequestException:
        pass
    return []


def _fetch_industry_modules(slug):
    """Fetch recommended modules for an industry from Cloud API."""
    from apps.configuration.models import HubConfig

    hub_config = HubConfig.get_solo()
    cloud_api_url = getattr(django_settings, 'CLOUD_API_URL', 'https://erplora.com')
    auth_token = hub_config.hub_jwt or hub_config.cloud_api_token

    if not auth_token:
        return {}

    try:
        response = requests.get(
            f"{cloud_api_url}/api/marketplace/industries/{slug}/",
            headers={'Accept': 'application/json', 'X-Hub-Token': auth_token},
            timeout=10,
        )
        if response.status_code == 200:
            data = response.json()
            # Build a dict: module_id → is_essential
            result = {}
            for m in data.get('modules', []):
                result[m.get('module_id', '')] = m.get('is_essential', False)
            return result
    except requests.exceptions.RequestException:
        pass
    return {}


def _fetch_solutions_for_filters():
    """Fetch solutions from Cloud API and group by block_type for the filter modal."""
    from apps.configuration.models import HubConfig

    hub_config = HubConfig.get_config()
    cloud_api_url = getattr(django_settings, 'CLOUD_API_URL', 'https://erplora.com')
    active_blocks = set(hub_config.selected_blocks or [])

    solutions = []
    try:
        response = requests.get(
            f"{cloud_api_url}/api/marketplace/solutions/",
            headers={'Accept': 'application/json'},
            timeout=10,
        )
        if response.status_code == 200:
            solutions = response.json()
    except requests.exceptions.RequestException:
        pass

    if not solutions:
        return []

    category_order = [
        'core', 'commerce', 'services', 'hospitality', 'hr',
        'finance', 'operations', 'marketing', 'utility', 'compliance', 'specialized',
    ]
    category_labels = {
        'core': str(_('Core')), 'commerce': str(_('Commerce')), 'services': str(_('Services')),
        'hospitality': str(_('Hospitality')), 'hr': str(_('HR')), 'finance': str(_('Finance')),
        'operations': str(_('Operations')), 'marketing': str(_('Marketing')),
        'utility': str(_('Utility')), 'compliance': str(_('Compliance')),
        'specialized': str(_('Specialized')),
    }

    # Group blocks by category for the filter UI
    blocks_by_category = {}
    for s in solutions:
        cat = s.get('block_type', '') or 'other'
        blocks_by_category.setdefault(cat, []).append({
            'id': s.get('slug', ''),
            'name': s.get('name', ''),
            'is_active': s.get('slug', '') in active_blocks,
        })

    grouped = []
    for cat in category_order:
        if cat in blocks_by_category:
            grouped.append({
                'key': cat,
                'name': category_labels.get(cat, cat.title()),
                'blocks': blocks_by_category[cat],
            })
    for cat, blocks in blocks_by_category.items():
        if cat not in category_order:
            grouped.append({'key': cat, 'name': cat.title(), 'blocks': blocks})

    return grouped


def _get_filters_for_store(store_type, language, request):
    """Get filter options based on store type"""
    from apps.configuration.models import HubConfig

    filters = {}
    hub_config = HubConfig.get_solo()
    auth_token = hub_config.hub_jwt or hub_config.cloud_api_token

    if store_type == 'modules':
        # Fetch solutions grouped by block_type
        solutions_grouped = _fetch_solutions_for_filters()

        # Fetch industries for the search select
        industries = _fetch_industries_for_filters()

        filters['solutions_grouped'] = solutions_grouped
        filters['industries'] = industries
        filters['industries_list'] = industries if isinstance(industries, list) else []
        filters['types'] = [
            {'id': 'free', 'name': 'Free', 'name_es': 'Gratis', 'icon': 'gift-outline'},
            {'id': 'one_time', 'name': 'One-time', 'name_es': 'Pago único', 'icon': 'card-outline'},
            {'id': 'subscription', 'name': 'Subscription', 'name_es': 'Suscripción', 'icon': 'sync-outline'},
        ]

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


# Cart Management

def get_cart_key(store_type):
    """Get session key for cart by store type"""
    return f'marketplace_cart_{store_type}'


def get_cart(request, store_type):
    """Get cart from session for specific store type"""
    key = get_cart_key(store_type)
    return request.session.get(key, {'items': [], 'total': 0})


def save_cart(request, store_type, cart):
    """Save cart to session"""
    key = get_cart_key(store_type)
    request.session[key] = cart
    request.session.modified = True


@login_required
def cart_add(request, store_type):
    """Add item to cart — returns JSON for JS fetch calls."""
    if request.method != 'POST':
        return HttpResponse(status=405)

    try:
        data = json.loads(request.body)
        item_id = data.get('item_id')
        module_id = data.get('module_id', '')
        item_name = data.get('item_name', '')
        item_price = float(data.get('item_price', 0))
        item_icon = data.get('item_icon', 'cube-outline')
        item_type = data.get('item_type', 'one_time')
        quantity = int(data.get('quantity', 1))
        tier_slug = data.get('tier_slug', '')
    except (json.JSONDecodeError, ValueError):
        return HttpResponse(
            json.dumps({'success': False, 'error': 'Invalid data'}),
            content_type='application/json', status=400,
        )

    if not item_id:
        return HttpResponse(
            json.dumps({'success': False, 'error': 'Missing item_id'}),
            content_type='application/json', status=400,
        )

    cart = get_cart(request, store_type)

    # Check if item already in cart (for tiered modules, different tiers = different items)
    for item in cart['items']:
        if item['id'] == item_id and item.get('tier_slug', '') == tier_slug:
            item['quantity'] += quantity
            break
    else:
        cart_item = {
            'id': item_id,
            'module_id': module_id,
            'name': item_name,
            'price': item_price,
            'icon': item_icon,
            'module_type': item_type,
            'quantity': quantity,
        }
        if tier_slug:
            cart_item['tier_slug'] = tier_slug
        cart['items'].append(cart_item)

    # Recalculate total
    cart['total'] = sum(item['price'] * item['quantity'] for item in cart['items'])
    save_cart(request, store_type, cart)

    return HttpResponse(
        json.dumps({
            'success': True,
            'cart_count': len(cart['items']),
            'cart_total': cart['total'],
        }),
        content_type='application/json',
    )


@login_required
def cart_remove(request, store_type, item_id):
    """Remove item from cart (HTMX endpoint)"""
    if request.method != 'DELETE':
        return HttpResponse(status=405)

    cart = get_cart(request, store_type)
    cart['items'] = [item for item in cart['items'] if item['id'] != item_id]
    cart['total'] = sum(item['price'] * item['quantity'] for item in cart['items'])
    save_cart(request, store_type, cart)

    html = render_to_string('marketplace/partials/cart_content.html', {
        'cart': cart,
        'store_type': store_type,
    }, request=request)

    badge_count = len(cart['items'])
    hidden_attr = ' style="display:none"' if badge_count == 0 else ''
    badge_html = (
        f'<span id="cart-badge" class="badge badge-sm color-error" hx-swap-oob="true"'
        f'{hidden_attr}>{badge_count}</span>'
    )

    return HttpResponse(html + badge_html)


@login_required
def cart_clear(request, store_type):
    """Clear entire cart (HTMX endpoint)"""
    if request.method != 'DELETE':
        return HttpResponse(status=405)

    save_cart(request, store_type, {'items': [], 'total': 0})

    html = render_to_string('marketplace/partials/cart_content.html', {
        'cart': {'items': [], 'total': 0},
        'store_type': store_type,
    }, request=request)

    badge_html = '<span id="cart-badge" class="badge badge-sm color-error" hx-swap-oob="true" style="display:none">0</span>'

    return HttpResponse(html + badge_html)


@login_required
def cart_view(request, store_type):
    """Get cart content (HTMX endpoint)"""
    cart = get_cart(request, store_type)

    html = render_to_string('marketplace/partials/cart_content.html', {
        'cart': cart,
        'store_type': store_type,
    }, request=request)

    return HttpResponse(html)


@login_required
@htmx_view('marketplace/pages/marketplace.html', 'marketplace/partials/cart_page_content.html')
def cart_page(request, store_type='modules'):
    """
    Full cart page view.
    Uses same layout as store, but shows cart page content.
    """
    config = get_store_config(store_type)
    cart = get_cart(request, store_type)

    # Calculate cart summary
    subtotal = sum(item['price'] * item.get('quantity', 1) for item in cart.get('items', []))
    tax_rate = 21  # Default VAT rate
    tax = subtotal * (tax_rate / 100)
    total = subtotal + tax

    cart_summary = {
        'items': cart.get('items', []),
        'count': len(cart.get('items', [])),
        'subtotal': subtotal,
        'tax_rate': tax_rate,
        'tax': tax if subtotal > 0 else 0,
        'total': total if subtotal > 0 else 0,
    }

    return {
        'current_section': 'marketplace',
        'page_title': 'Cart',
        'store_type': store_type,
        'store_config': config,
        'cart': cart_summary,
        'cart_count': cart_summary['count'],
        'navigation': _marketplace_navigation('modules'),
    }


# Cart Checkout

@login_required
def cart_checkout(request, store_type='modules'):
    """Create Stripe Checkout session for cart items via Cloud API."""
    if request.method != 'POST':
        return HttpResponse(status=405)

    cart = get_cart(request, store_type)
    if not cart['items']:
        return HttpResponse(
            json.dumps({'success': False, 'error': str(_('Cart is empty'))}),
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
        response = requests.post(
            f"{cloud_api_url}/api/marketplace/cart/checkout/",
            json={
                'items': [
                    {
                        'module_id': item.get('module_id', item['id']),
                        'module_slug': item['id'],
                        'quantity': item.get('quantity', 1),
                        **(({'tier_slug': item['tier_slug']} if item.get('tier_slug') else {})),
                    }
                    for item in cart['items']
                ],
                'success_url': request.build_absolute_uri('/marketplace/?checkout=success'),
                'cancel_url': request.build_absolute_uri('/marketplace/?checkout=cancel'),
            },
            headers={
                'X-Hub-Token': auth_token,
                'Content-Type': 'application/json',
            },
            timeout=30,
        )

        if response.status_code == 200:
            data = response.json()
            if data.get('checkout_url'):
                return HttpResponse(
                    json.dumps({
                        'success': True,
                        'checkout_url': data['checkout_url'],
                        'session_id': data.get('session_id'),
                    }),
                    content_type='application/json',
                )
            else:
                # All free or already owned
                return HttpResponse(
                    json.dumps({
                        'success': True,
                        'message': data.get('message', str(_('No paid items to checkout.'))),
                    }),
                    content_type='application/json',
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


MARKETPLACE_PER_PAGE_CHOICES = [12, 24, 48, 96]


def _create_roles_for_installed_modules(module_slugs):
    """
    After installing modules, look up which solutions they belong to
    and auto-create the corresponding roles.
    """
    from apps.configuration.models import HubConfig

    hub_config = HubConfig.get_solo()
    if not hub_config.hub_id:
        return

    cloud_api_url = _get_cloud_api_url()
    auth_token = hub_config.hub_jwt or hub_config.cloud_api_token
    if not auth_token:
        return

    # Fetch module details to find solution_slugs
    solution_slugs_to_fetch = set()
    for slug in module_slugs:
        try:
            response = requests.get(
                f"{cloud_api_url}/api/marketplace/modules/{slug}/",
                headers={'Accept': 'application/json', 'X-Hub-Token': auth_token},
                timeout=10,
            )
            if response.status_code == 200:
                data = response.json()
                for sol_slug in data.get('solution_slugs', []):
                    solution_slugs_to_fetch.add(sol_slug)
        except Exception:
            pass

    if not solution_slugs_to_fetch:
        return

    # Fetch roles for each solution and create them
    from apps.core.services.permission_service import PermissionService
    for sol_slug in solution_slugs_to_fetch:
        try:
            resp = requests.get(
                f"{cloud_api_url}/api/marketplace/solutions/{sol_slug}/",
                headers={'Accept': 'application/json'},
                timeout=15,
            )
            if resp.status_code == 200:
                roles_data = resp.json().get('roles', [])
                if roles_data:
                    PermissionService.create_solution_roles(str(hub_config.hub_id), roles_data)
                    logger.info("[AUTO ROLES] Created roles for solution %s", sol_slug)
        except Exception as e:
            logger.warning("[AUTO ROLES] Failed for solution %s: %s", sol_slug, e)


# Products list with DataTable pagination

@login_required
def products_list(request, store_type):
    """
    HTMX endpoint: Fetch and render products with DataTable pagination.
    Returns HTML partial with product cards or table rows.
    Supports filters: q (search), category, industry, type, page, sort, dir, view
    """
    from apps.configuration.models import HubConfig

    # Get filters from query params
    search_query = request.GET.get('q', '').strip()
    solution_filter = request.GET.get('solution', '').strip()
    industry_filter = request.GET.get('industry', '').strip()
    type_filter = request.GET.get('type', '').strip()
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
        return _fetch_modules_list(request, search_query, solution_filter, industry_filter, type_filter, sort_field, sort_dir, current_view, per_page, page_number)
    elif store_type == 'hubs':
        return _fetch_hubs_list(request, search_query, '', 12)
    else:
        # Coming soon stores
        html = render_to_string('marketplace/partials/coming_soon.html', {
            'store_type': store_type,
            'store_config': config,
        }, request=request)
        return HttpResponse(html)


def _fetch_modules_list(request, search_query, solution_filter, industry_filter, type_filter, sort_field, sort_dir, current_view, per_page, page_number):
    """Fetch modules from Cloud API with DataTable pagination"""
    from django.core.paginator import Paginator
    from apps.configuration.models import HubConfig

    # Get installed modules
    modules_dir = Path(django_settings.MODULES_DIR)
    installed_module_ids = []
    if modules_dir.exists():
        for module_dir in modules_dir.iterdir():
            if module_dir.is_dir() and not module_dir.name.startswith('.'):
                installed_module_ids.append(module_dir.name.lstrip('_'))

    hub_config = HubConfig.get_solo()
    auth_token = hub_config.hub_jwt or hub_config.cloud_api_token

    if not auth_token:
        html = render_to_string('marketplace/partials/error.html', {
            'error': 'Hub not connected to Cloud. Please connect in Settings.'
        }, request=request)
        return HttpResponse(html)

    cloud_api_url = getattr(django_settings, 'CLOUD_API_URL', 'https://erplora.com')
    headers = {'Accept': 'application/json', 'X-Hub-Token': auth_token}

    try:
        response = requests.get(
            f"{cloud_api_url}/api/marketplace/modules/",
            headers=headers,
            timeout=30
        )

        if response.status_code != 200:
            html = render_to_string('marketplace/partials/error.html', {
                'error': f'Cloud API returned {response.status_code}'
            }, request=request)
            return HttpResponse(html)

        data = response.json()
        modules = data.get('results', data) if isinstance(data, dict) else data
        if not isinstance(modules, list):
            modules = []

        # Apply filters
        if search_query:
            query_lower = search_query.lower()
            modules = [m for m in modules if (
                query_lower in m.get('name', '').lower() or
                query_lower in m.get('description', '').lower() or
                any(query_lower in str(tag).lower() for tag in m.get('tags', []))
            )]

        if solution_filter:
            solution_slugs = [s.strip() for s in solution_filter.split(',') if s.strip()]
            if solution_slugs:
                # Filter modules by solution_slugs field (solution membership)
                modules = [m for m in modules if any(
                    ss in m.get('solution_slugs', []) for ss in solution_slugs
                )]

        # Industry filter: fetch recommended modules for selected industries
        industry_module_map = {}
        if industry_filter:
            industry_slugs = [s.strip() for s in industry_filter.split(',') if s.strip()]
            for ind_slug in industry_slugs:
                ind_map = _fetch_industry_modules(ind_slug)
                for mid, is_essential in ind_map.items():
                    # Keep essential=True if any industry marks it essential
                    if mid not in industry_module_map:
                        industry_module_map[mid] = is_essential
                    elif is_essential:
                        industry_module_map[mid] = True
            if industry_module_map:
                industry_module_ids = set(industry_module_map.keys())
                modules = [m for m in modules if m.get('module_id', '') in industry_module_ids]
                for m in modules:
                    m['is_essential'] = industry_module_map.get(m.get('module_id', ''), False)

        if type_filter:
            modules = [m for m in modules if m.get('module_type') == type_filter]

        # Mark installed and add URLs
        for module in modules:
            module['is_installed'] = module.get('slug', '') in installed_module_ids or module.get('module_id', '') in installed_module_ids
            module['detail_url'] = reverse('marketplace:module_detail', kwargs={'slug': module.get('slug', '')})
            if not module.get('download_url'):
                module['download_url'] = f"{cloud_api_url}/api/marketplace/modules/{module.get('slug', '')}/download/"

        # Sort
        sort_key_map = {
            'name': lambda m: m.get('name', '').lower(),
            'price': lambda m: float(m.get('price', 0)),
            'rating': lambda m: float(m.get('rating', 0)),
        }
        sort_fn = sort_key_map.get(sort_field, sort_key_map['name'])
        modules.sort(key=sort_fn, reverse=(sort_dir == 'desc'))

        # Page-based pagination
        paginator = Paginator(modules, per_page)
        page_obj = paginator.get_page(page_number)

        html = render_to_string('marketplace/partials/products_grid.html', {
            'products': page_obj,
            'page_obj': page_obj,
            'store_type': 'modules',
            'search_query': search_query,
            'solution_filter': solution_filter,
            'industry_filter': industry_filter,
            'type_filter': type_filter,
            'sort_field': sort_field,
            'sort_dir': sort_dir,
            'current_view': current_view,
            'per_page': per_page,
        }, request=request)

        return HttpResponse(html)

    except requests.exceptions.RequestException as e:
        html = render_to_string('marketplace/partials/error.html', {
            'error': f'Failed to connect to Cloud: {str(e)}'
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
            'cart_count': 0,
        }

    # Get installed modules
    modules_dir = Path(django_settings.MODULES_DIR)
    installed_module_ids = []
    if modules_dir.exists():
        for module_dir in modules_dir.iterdir():
            if module_dir.is_dir() and not module_dir.name.startswith('.'):
                installed_module_ids.append(module_dir.name.lstrip('_'))

    cloud_api_url = getattr(django_settings, 'CLOUD_API_URL', 'https://erplora.com')
    headers = {'Accept': 'application/json', 'X-Hub-Token': auth_token}

    try:
        # Fetch module details from Cloud API
        response = requests.get(
            f"{cloud_api_url}/api/marketplace/modules/{slug}/",
            headers=headers,
            timeout=30
        )

        if response.status_code == 404:
            return {
                'current_section': 'marketplace',
                'error': f'Module "{slug}" not found.',
                'cart_count': 0,
            }

        if response.status_code != 200:
            return {
                'current_section': 'marketplace',
                'error': f'Cloud API returned {response.status_code}',
                'cart_count': 0,
            }

        module = response.json()

        # Check if installed (compare both slug and module_id)
        is_installed = slug in installed_module_ids or module.get('module_id', '') in installed_module_ids

        # Check ownership (from API response or via check_ownership endpoint)
        is_owned = module.get('is_owned', False)
        if not is_owned:
            try:
                ownership_response = requests.get(
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

        # Get cart count
        cart = get_cart(request, 'modules')

        # Related modules (same category)
        related_modules = []
        try:
            related_response = requests.get(
                f"{cloud_api_url}/api/marketplace/modules/",
                headers=headers,
                params={'category': module.get('category'), 'limit': 3},
                timeout=10
            )
            if related_response.status_code == 200:
                related_data = related_response.json()
                related_list = related_data.get('results', related_data) if isinstance(related_data, dict) else related_data
                # Exclude current module
                related_modules = [m for m in related_list if m.get('slug') != slug][:3]
        except Exception:
            pass

        return {
            'current_section': 'marketplace',
            'page_title': module.get('name', 'Module Details'),
            'module': module,
            'is_installed': is_installed,
            'is_owned': is_owned,
            'is_free': is_free,
            'related_modules': related_modules,
            'back_url': reverse('marketplace:index'),
            'cart_count': len(cart.get('items', [])),
            'navigation': _marketplace_navigation('modules'),
        }

    except requests.exceptions.RequestException as e:
        return {
            'current_section': 'marketplace',
            'error': f'Failed to connect to Cloud: {str(e)}',
            'cart_count': 0,
        }


# --- Solutions views ---

SOLUTIONS_BLOCK_TYPES = [
    ('core', _('Core')), ('commerce', _('Commerce')), ('services', _('Services')),
    ('hospitality', _('Hospitality')), ('hr', _('HR')), ('finance', _('Finance')),
    ('operations', _('Operations')), ('marketing', _('Marketing')),
    ('utility', _('Utility')), ('compliance', _('Compliance')),
    ('specialized', _('Specialized')),
]


@login_required
@htmx_view('marketplace/pages/marketplace.html', 'marketplace/partials/solutions_content.html')
def solutions_index(request):
    """Functional blocks DataTable wrapper — content loads via HTMX from solutions_list."""
    cart = get_cart(request, 'modules')
    return {
        'current_section': 'marketplace',
        'page_title': _('Solutions'),
        'block_types': SOLUTIONS_BLOCK_TYPES,
        'cart_count': len(cart.get('items', [])),
        'navigation': _marketplace_navigation('modules'),
    }


def _fetch_solution_modules(slug, cloud_api_url):
    """Fetch module list for a single solution from Cloud API."""
    try:
        r = requests.get(
            f"{cloud_api_url}/api/marketplace/solutions/{slug}/",
            headers={'Accept': 'application/json'}, timeout=15,
        )
        if r.status_code == 200:
            return slug, r.json().get('modules', [])
    except Exception:
        pass
    return slug, []


@login_required
def solutions_list(request):
    """HTMX endpoint: Fetch and render solutions with DataTable features."""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from django.core.paginator import Paginator

    search_query = request.GET.get('q', '').strip()
    block_type_filter = request.GET.get('block_type', '').strip()
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

    cloud_api_url = _get_cloud_api_url()
    solutions = []
    try:
        response = requests.get(
            f"{cloud_api_url}/api/marketplace/solutions/",
            headers={'Accept': 'application/json'}, timeout=15,
        )
        if response.status_code == 200:
            solutions = response.json()
    except requests.exceptions.RequestException:
        pass

    installed_ids = set(_get_installed_module_ids())

    # Fetch module details for each solution in parallel
    if solutions:
        slugs_to_fetch = [s['slug'] for s in solutions if s.get('slug')]
        modules_by_slug = {}
        with ThreadPoolExecutor(max_workers=6) as executor:
            futures = {
                executor.submit(_fetch_solution_modules, slug, cloud_api_url): slug
                for slug in slugs_to_fetch
            }
            for future in as_completed(futures):
                slug, modules = future.result()
                modules_by_slug[slug] = modules

    for s in solutions:
        # Attach modules list and mark install status
        sol_modules = modules_by_slug.get(s.get('slug', ''), [])
        for m in sol_modules:
            m['is_installed'] = (
                m.get('module_id', '') in installed_ids
                or m.get('slug', '') in installed_ids
            )
        s['modules'] = sol_modules
        # Compact JSON for Alpine.js (only fields needed by toggleSolution/isSolutionFullySelected)
        s['modules_json'] = json.dumps([
            {'slug': m.get('slug', ''), 'is_installed': m.get('is_installed', False)}
            for m in sol_modules if not m.get('is_coming_soon')
        ])

        required_ids = s.get('required_module_ids', [])
        required_count = s.get('required_module_count', 0) or len(required_ids)
        installed_count = sum(1 for mid in required_ids if mid in installed_ids)
        s['installed_count'] = installed_count
        s['required_count'] = required_count
        s['all_installed'] = required_count > 0 and installed_count >= required_count
        s['partially_installed'] = installed_count > 0 and installed_count < required_count
        s.setdefault('all_modules_count', 0)
        s['detail_url'] = reverse('marketplace:solution_detail', kwargs={'slug': s.get('slug', '')})

    # Filters
    if search_query:
        q = search_query.lower()
        solutions = [s for s in solutions if q in s.get('name', '').lower() or q in s.get('tagline', '').lower()]
    if block_type_filter:
        types = [t.strip() for t in block_type_filter.split(',') if t.strip()]
        solutions = [s for s in solutions if s.get('block_type', '') in types]
    if status_filter:
        if status_filter == 'installed':
            solutions = [s for s in solutions if s['all_installed']]
        elif status_filter == 'partial':
            solutions = [s for s in solutions if s['partially_installed']]
        elif status_filter == 'available':
            solutions = [s for s in solutions if not s['all_installed'] and not s['partially_installed']]

    # Sort
    sort_map = {
        'name': lambda x: x.get('name', '').lower(),
        'modules': lambda x: x.get('all_modules_count', 0) or 0,
        'type': lambda x: x.get('block_type', ''),
    }
    solutions.sort(key=sort_map.get(sort_field, sort_map['name']), reverse=(sort_dir == 'desc'))

    paginator = Paginator(solutions, per_page)
    page_obj = paginator.get_page(page_number)

    html = render_to_string('marketplace/partials/solutions_grid.html', {
        'solutions': page_obj,
        'page_obj': page_obj,
        'current_view': current_view,
        'search_query': search_query,
        'block_type_filter': block_type_filter,
        'status_filter': status_filter,
        'sort_field': sort_field,
        'sort_dir': sort_dir,
        'per_page': per_page,
    }, request=request)
    return HttpResponse(html)


@login_required
def solutions_bulk_install(request):
    """POST: Install multiple blocks at once."""
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
    active_blocks = list(hub_config.selected_blocks or [])
    for slug in block_slugs:
        if slug not in active_blocks:
            active_blocks.append(slug)
    hub_config.selected_blocks = active_blocks
    hub_config.solution_slug = active_blocks[0] if active_blocks else ''
    hub_config.save()

    from apps.core.services.module_install_service import ModuleInstallService
    result = ModuleInstallService.install_block_modules(block_slugs, hub_config)

    if result.installed > 0:
        ModuleInstallService.run_post_install(
            load_all=True, run_migrations=True, schedule_restart=True,
        )

    # Create roles for all installed blocks
    if hub_config.hub_id:
        cloud_api_url = _get_cloud_api_url()
        for slug in block_slugs:
            try:
                resp = requests.get(
                    f"{cloud_api_url}/api/marketplace/solutions/{slug}/",
                    headers={'Accept': 'application/json'}, timeout=15,
                )
                if resp.status_code == 200:
                    roles_data = resp.json().get('roles', [])
                    if roles_data:
                        from apps.core.services.permission_service import PermissionService
                        PermissionService.create_solution_roles(str(hub_config.hub_id), roles_data)
            except Exception as e:
                logger.warning("Failed to create roles for block %s: %s", slug, e)

    return HttpResponse(json.dumps({
        'success': True,
        'installed': result.installed,
        'errors': result.errors,
        'requires_restart': result.installed > 0,
    }), content_type='application/json')


@login_required
def modules_bulk_install(request):
    """POST: Install multiple modules at once."""
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

    modules_to_install = [
        {
            'slug': m['slug'],
            'name': m.get('name', m['slug']),
            'download_url': m.get('download_url', f"{cloud_api_url}/api/marketplace/modules/{m['slug']}/download/"),
        }
        for m in modules if m.get('slug')
    ]

    # Resolve transitive dependencies
    modules_dir = Path(django_settings.MODULES_DIR)
    installed_ids = set()
    if modules_dir.exists():
        for d in modules_dir.iterdir():
            if d.is_dir() and not d.name.startswith('.'):
                installed_ids.add(d.name.lstrip('_'))

    all_slugs = {m['slug'] for m in modules_to_install}
    dep_modules = ModuleInstallService._resolve_dependencies(
        all_slugs, installed_ids, cloud_api_url, hub_token
    )
    if dep_modules:
        logger.info(
            "[BULK INSTALL] Adding %d dependency modules: %s",
            len(dep_modules), [m['slug'] for m in dep_modules],
        )
        modules_to_install.extend(dep_modules)

    logger.info(
        "[BULK INSTALL] Installing %d modules: %s",
        len(modules_to_install),
        [m['slug'] for m in modules_to_install],
    )

    result = ModuleInstallService.bulk_download_and_install(modules_to_install, hub_token)

    logger.info(
        "[BULK INSTALL] Result: installed=%d, errors=%s, results=%s",
        result.installed,
        result.errors,
        [(r.module_id, r.success, r.message) for r in (result.results or [])],
    )

    if result.installed > 0:
        ModuleInstallService.run_post_install(
            load_all=True, run_migrations=True, schedule_restart=True,
        )

        # Auto-create roles for newly installed modules
        installed_slugs = [m['slug'] for m in modules_to_install]
        _create_roles_for_installed_modules(installed_slugs)

    return HttpResponse(json.dumps({
        'success': True,
        'installed': result.installed,
        'errors': result.errors,
        'requires_restart': result.installed > 0,
    }), content_type='application/json')


@login_required
@htmx_view('marketplace/pages/marketplace.html', 'marketplace/partials/solution_detail_content.html')
def solution_detail(request, slug):
    """Block detail — shows modules, roles, and activate/deactivate button."""
    cloud_api_url = _get_cloud_api_url()
    installed_ids = _get_installed_module_ids()

    try:
        response = requests.get(
            f"{cloud_api_url}/api/marketplace/solutions/{slug}/",
            headers={'Accept': 'application/json'},
            timeout=15,
        )
        if response.status_code == 404:
            return {
                'current_section': 'marketplace',
                'error': _('Block not found.'),
                'navigation': _marketplace_navigation('modules'),
            }
        if response.status_code != 200:
            return {
                'current_section': 'marketplace',
                'error': f'Cloud API returned {response.status_code}',
                'navigation': _marketplace_navigation('modules'),
            }

        solution = response.json()

        # Check if this block is active
        from apps.configuration.models import HubConfig
        hub_config = HubConfig.get_config()
        active_blocks = set(hub_config.selected_blocks or [])
        is_block_active = slug in active_blocks

        # Split modules into required/optional and mark installed
        required_modules = []
        optional_modules = []
        all_installed = True
        for mod in solution.get('modules', []):
            mod['is_installed'] = mod.get('slug', '') in installed_ids or mod.get('module_id', '') in installed_ids
            if mod['role'] == 'required':
                required_modules.append(mod)
                if not mod['is_installed']:
                    all_installed = False
            else:
                optional_modules.append(mod)

        cart = get_cart(request, 'modules')

        return {
            'current_section': 'marketplace',
            'page_title': solution.get('name', 'Block'),
            'solution': solution,
            'required_modules': required_modules,
            'optional_modules': optional_modules,
            'all_installed': all_installed,
            'is_block_active': is_block_active,
            'back_url': reverse('marketplace:index'),
            'cart_count': len(cart.get('items', [])),
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
    """POST: Install all required modules from a solution."""
    if request.method != 'POST':
        return HttpResponse(status=405)

    cloud_api_url = _get_cloud_api_url()
    installed_ids = _get_installed_module_ids()

    try:
        # Fetch solution detail to get modules
        response = requests.get(
            f"{cloud_api_url}/api/marketplace/solutions/{slug}/",
            headers={'Accept': 'application/json'},
            timeout=15,
        )
        if response.status_code != 200:
            return HttpResponse(
                json.dumps({'success': False, 'error': 'Solution not found'}),
                content_type='application/json', status=404,
            )

        solution = response.json()
        required_modules = [
            m for m in solution.get('modules', [])
            if m['role'] == 'required' and m.get('slug', '') not in installed_ids and m.get('module_id', '') not in installed_ids
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
            ModuleInstallService.run_post_install(
                load_all=True, run_migrations=True,
                schedule_restart=True,
            )

            # Create solution roles
            roles_data = solution.get('roles', [])
            if roles_data and hub_config.hub_id:
                try:
                    from apps.core.services.permission_service import PermissionService
                    PermissionService.create_solution_roles(str(hub_config.hub_id), roles_data)
                except Exception as e:
                    logger.warning(f"Failed to create solution roles for {slug}: {e}")

        result = {
            'success': True,
            'installed': installed_count,
            'total': len(required_modules),
            'errors': errors,
            'requires_restart': installed_count > 0,
        }
        return HttpResponse(json.dumps(result), content_type='application/json')

    except requests.exceptions.RequestException as e:
        return HttpResponse(
            json.dumps({'success': False, 'error': str(e)}),
            content_type='application/json', status=500,
        )


@login_required
def block_toggle(request, slug):
    """POST: Activate or deactivate a functional block."""
    if request.method != 'POST':
        return HttpResponse(status=405)

    from apps.configuration.models import HubConfig
    hub_config = HubConfig.get_config()
    active_blocks = list(hub_config.selected_blocks or [])

    if slug in active_blocks:
        # Uninstall: remove from list
        active_blocks.remove(slug)
        hub_config.selected_blocks = active_blocks
        hub_config.solution_slug = active_blocks[0] if active_blocks else ''
        hub_config.save()
        return HttpResponse(
            json.dumps({'success': True, 'action': 'uninstalled', 'slug': slug, 'active_count': len(active_blocks)}),
            content_type='application/json',
        )
    else:
        # Install: add to list + install modules + create roles
        active_blocks.append(slug)
        hub_config.selected_blocks = active_blocks
        hub_config.solution_slug = active_blocks[0] if active_blocks else ''
        hub_config.save()

        # Install required modules for this block
        from apps.core.services.module_install_service import ModuleInstallService
        result = ModuleInstallService.install_block_modules([slug], hub_config)

        if result.installed > 0:
            ModuleInstallService.run_post_install(
                load_all=True, run_migrations=True,
                sync_permissions=bool(hub_config.hub_id),
                hub_id=str(hub_config.hub_id) if hub_config.hub_id else None,
                schedule_restart=True,
            )

        # Create roles for this block
        if hub_config.hub_id:
            cloud_api_url = _get_cloud_api_url()
            try:
                response = requests.get(
                    f"{cloud_api_url}/api/marketplace/solutions/{slug}/",
                    headers={'Accept': 'application/json'},
                    timeout=15,
                )
                if response.status_code == 200:
                    solution = response.json()
                    roles_data = solution.get('roles', [])
                    if roles_data:
                        from apps.core.services.permission_service import PermissionService
                        PermissionService.create_solution_roles(str(hub_config.hub_id), roles_data)
            except Exception as e:
                logger.warning(f"Failed to create roles for block {slug}: {e}")

        return HttpResponse(
            json.dumps({
                'success': True,
                'action': 'installed',
                'slug': slug,
                'active_count': len(active_blocks),
                'modules_installed': result.installed,
                'install_errors': result.errors,
                'requires_restart': result.installed > 0,
            }),
            content_type='application/json',
        )


# --- Business Types views (informational) ---

@login_required
@htmx_view('marketplace/pages/marketplace.html', 'marketplace/partials/business_types_content.html')
def business_types_index(request):
    """Business types list — browse by type to see recommended modules and roles."""
    industries = _fetch_industries_for_filters()

    cart = get_cart(request, 'modules')

    return {
        'current_section': 'marketplace',
        'page_title': _('Business Types'),
        'industries': industries,
        'cart_count': len(cart.get('items', [])),
        'navigation': _marketplace_navigation('business_types'),
    }


@login_required
@htmx_view('marketplace/pages/marketplace.html', 'marketplace/partials/business_type_detail_content.html')
def business_type_detail(request, slug):
    """Business type detail — shows recommended modules and roles (informational only)."""
    from apps.configuration.models import HubConfig

    hub_config = HubConfig.get_solo()
    cloud_api_url = getattr(django_settings, 'CLOUD_API_URL', 'https://erplora.com')
    auth_token = hub_config.hub_jwt or hub_config.cloud_api_token

    if not auth_token:
        return {
            'current_section': 'marketplace',
            'error': _('Hub not connected to Cloud. Please connect in Settings.'),
            'navigation': _marketplace_navigation('business_types'),
        }

    try:
        response = requests.get(
            f"{cloud_api_url}/api/marketplace/industries/{slug}/",
            headers={'Accept': 'application/json', 'X-Hub-Token': auth_token},
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

        # Mark installed modules
        installed_ids = _get_installed_module_ids()
        for mod in industry.get('modules', []):
            mod['is_installed'] = (
                mod.get('slug', '') in installed_ids
                or mod.get('module_id', '') in installed_ids
            )

        cart = get_cart(request, 'modules')

        return {
            'current_section': 'marketplace',
            'page_title': industry.get('name', _('Business Type')),
            'industry': industry,
            'back_url': reverse('marketplace:business_types'),
            'cart_count': len(cart.get('items', [])),
            'navigation': _marketplace_navigation('business_types'),
        }

    except requests.exceptions.RequestException as e:
        return {
            'current_section': 'marketplace',
            'error': f'Failed to connect to Cloud: {str(e)}',
            'navigation': _marketplace_navigation('business_types'),
        }


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

    cart = get_cart(request, 'modules')

    from apps.configuration.models import HubConfig
    hub_config = HubConfig.get_config()

    return {
        'current_section': 'marketplace',
        'page_title': _('Compliance'),
        'countries': countries,
        'hub_country': hub_config.country_code,
        'cart_count': len(cart.get('items', [])),
        'navigation': _marketplace_navigation('compliance'),
    }


@login_required
def compliance_detail(request, country_code):
    """Redirect to the main compliance page (accordion view)."""
    from django.shortcuts import redirect
    return redirect('marketplace:compliance')
