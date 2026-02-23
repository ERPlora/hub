"""
Marketplace Views - Multi-store marketplace with sidebar filters and cart

Tabs:
- Modules: Software modules from Cloud marketplace
- Solutions: Pre-configured module bundles
- Compliance: Country-specific required modules
"""
import json
import requests
from pathlib import Path
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.conf import settings as django_settings
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from apps.core.htmx import htmx_view
from apps.accounts.decorators import login_required


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
            'url': reverse('marketplace:solutions'),
            'icon': 'briefcase-outline',
            'label': str(_('Solutions')),
            'active': active_tab == 'solutions',
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


def _get_filters_for_store(store_type, language, request):
    """Get filter options based on store type"""
    from apps.configuration.models import HubConfig

    filters = {}
    hub_config = HubConfig.get_solo()
    auth_token = hub_config.hub_jwt or hub_config.cloud_api_token

    if store_type == 'modules':
        # Build grouped categories and industries (local fallback)
        categories_grouped = _build_grouped_categories(language)
        industries_grouped = _build_grouped_industries(language)

        # Try fetching grouped data from Cloud API
        if auth_token:
            cloud_api_url = getattr(django_settings, 'CLOUD_API_URL', 'https://erplora.com')
            headers = {'Accept': 'application/json', 'X-Hub-Token': auth_token}
            try:
                cat_response = requests.get(
                    f"{cloud_api_url}/api/marketplace/categories/grouped/",
                    headers=headers, params={'language': language}, timeout=10
                )
                if cat_response.status_code == 200:
                    cloud_data = cat_response.json()
                    if cloud_data:
                        categories_grouped = cloud_data

                ind_response = requests.get(
                    f"{cloud_api_url}/api/marketplace/industries/grouped/",
                    headers=headers, params={'language': language}, timeout=10
                )
                if ind_response.status_code == 200:
                    cloud_data = ind_response.json()
                    if cloud_data:
                        industries_grouped = cloud_data
            except Exception:
                pass

        filters['categories_grouped'] = categories_grouped
        filters['industries_grouped'] = industries_grouped
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

    # Check if item already in cart
    for item in cart['items']:
        if item['id'] == item_id:
            item['quantity'] += quantity
            break
    else:
        cart['items'].append({
            'id': item_id,
            'module_id': module_id,
            'name': item_name,
            'price': item_price,
            'icon': item_icon,
            'module_type': item_type,
            'quantity': quantity,
        })

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
    badge_html = (
        f'<span id="cart-badge" class="badge badge-sm color-error" hx-swap-oob="true"'
        f'{" style=\"display:none\"" if badge_count == 0 else ""}'
        f'>{badge_count}</span>'
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
    category_filter = request.GET.get('category', '').strip()
    industry_filter = request.GET.get('industry', '').strip()
    type_filter = request.GET.get('type', '').strip()
    sort_field = request.GET.get('sort', 'name')
    sort_dir = request.GET.get('dir', 'asc')
    current_view = request.GET.get('view', 'cards')
    per_page = int(request.GET.get('per_page', 12))
    if per_page not in MARKETPLACE_PER_PAGE_CHOICES:
        per_page = 12
    page_number = request.GET.get('page', 1)

    config = get_store_config(store_type)

    if store_type == 'modules':
        return _fetch_modules_list(request, search_query, category_filter, industry_filter, type_filter, sort_field, sort_dir, current_view, per_page, page_number)
    elif store_type == 'hubs':
        return _fetch_hubs_list(request, search_query, '', 12)
    else:
        # Coming soon stores
        html = render_to_string('marketplace/partials/coming_soon.html', {
            'store_type': store_type,
            'store_config': config,
        }, request=request)
        return HttpResponse(html)


def _fetch_modules_list(request, search_query, category_filter, industry_filter, type_filter, sort_field, sort_dir, current_view, per_page, page_number):
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

        if category_filter:
            cat_values = [c.strip() for c in category_filter.split(',') if c.strip()]
            if cat_values:
                # functions is a list; match if any function is in the selected values
                modules = [m for m in modules if any(
                    f in cat_values for f in m.get('functions', [m.get('category', '')])
                )]

        if industry_filter:
            ind_values = [i.strip() for i in industry_filter.split(',') if i.strip()]
            if ind_values:
                modules = [m for m in modules if any(iv in m.get('industries', []) for iv in ind_values)]

        if type_filter:
            modules = [m for m in modules if m.get('module_type') == type_filter]

        # Mark installed and add URLs
        for module in modules:
            module['is_installed'] = module.get('slug', '') in installed_module_ids
            module['detail_url'] = reverse('marketplace:module_detail', kwargs={'slug': module.get('slug', '')})

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
            'category_filter': category_filter,
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

        # Check if installed
        is_installed = slug in installed_module_ids

        # Check ownership
        is_owned = False
        try:
            ownership_response = requests.get(
                f"{cloud_api_url}/api/marketplace/ownership/{module.get('id', '')}/",
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

@login_required
@htmx_view('marketplace/pages/marketplace.html', 'marketplace/partials/solutions_content.html')
def solutions_index(request):
    """Solutions list — pre-configured module bundles from Cloud."""
    cloud_api_url = _get_cloud_api_url()
    solutions = []

    try:
        response = requests.get(
            f"{cloud_api_url}/api/marketplace/solutions/",
            headers={'Accept': 'application/json'},
            timeout=15,
        )
        if response.status_code == 200:
            solutions = response.json()
    except requests.exceptions.RequestException:
        pass

    cart = get_cart(request, 'modules')

    return {
        'current_section': 'marketplace',
        'page_title': _('Solutions'),
        'solutions': solutions,
        'cart_count': len(cart.get('items', [])),
        'navigation': _marketplace_navigation('solutions'),
    }


@login_required
@htmx_view('marketplace/pages/marketplace.html', 'marketplace/partials/solution_detail_content.html')
def solution_detail(request, slug):
    """Solution detail — shows modules + install button."""
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
                'error': _('Solution not found.'),
                'navigation': _marketplace_navigation('solutions'),
            }
        if response.status_code != 200:
            return {
                'current_section': 'marketplace',
                'error': f'Cloud API returned {response.status_code}',
                'navigation': _marketplace_navigation('solutions'),
            }

        solution = response.json()

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
            'page_title': solution.get('name', 'Solution'),
            'solution': solution,
            'required_modules': required_modules,
            'optional_modules': optional_modules,
            'all_installed': all_installed,
            'back_url': reverse('marketplace:solutions'),
            'cart_count': len(cart.get('items', [])),
            'navigation': _marketplace_navigation('solutions'),
        }

    except requests.exceptions.RequestException as e:
        return {
            'current_section': 'marketplace',
            'error': f'Failed to connect to Cloud: {str(e)}',
            'navigation': _marketplace_navigation('solutions'),
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

        # Install each module via the Hub's internal install API
        installed_count = 0
        errors = []
        from apps.configuration.models import HubConfig
        hub_config = HubConfig.get_solo()
        auth_token = hub_config.hub_jwt or hub_config.cloud_api_token

        for mod in required_modules:
            try:
                # Call the Hub's own install endpoint internally
                install_response = requests.post(
                    f"http://localhost:{request.META.get('SERVER_PORT', '8000')}/modules/api/marketplace/install/",
                    json={
                        'module_slug': mod['slug'],
                        'download_url': f"{cloud_api_url}/api/marketplace/modules/{mod.get('slug')}/download/",
                    },
                    headers={
                        'X-CSRFToken': request.META.get('CSRF_COOKIE', ''),
                        'Cookie': request.META.get('HTTP_COOKIE', ''),
                    },
                    timeout=120,
                )
                if install_response.status_code == 200:
                    installed_count += 1
                else:
                    errors.append(f"{mod['name']}: {install_response.status_code}")
            except Exception as e:
                errors.append(f"{mod['name']}: {str(e)}")

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


# --- Compliance views ---

@login_required
@htmx_view('marketplace/pages/marketplace.html', 'marketplace/partials/compliance_content.html')
def compliance_index(request):
    """Country compliance list — legal requirements by country."""
    cloud_api_url = _get_cloud_api_url()
    countries = []

    try:
        response = requests.get(
            f"{cloud_api_url}/api/marketplace/compliance/",
            headers={'Accept': 'application/json'},
            timeout=15,
        )
        if response.status_code == 200:
            countries = response.json()
    except requests.exceptions.RequestException:
        pass

    cart = get_cart(request, 'modules')

    return {
        'current_section': 'marketplace',
        'page_title': _('Compliance'),
        'countries': countries,
        'cart_count': len(cart.get('items', [])),
        'navigation': _marketplace_navigation('compliance'),
    }


@login_required
@htmx_view('marketplace/pages/marketplace.html', 'marketplace/partials/compliance_detail_content.html')
def compliance_detail(request, country_code):
    """Country compliance detail — required modules for a specific country."""
    cloud_api_url = _get_cloud_api_url()
    installed_ids = _get_installed_module_ids()

    try:
        response = requests.get(
            f"{cloud_api_url}/api/marketplace/compliance/{country_code}/",
            headers={'Accept': 'application/json'},
            timeout=15,
        )
        if response.status_code == 404:
            return {
                'current_section': 'marketplace',
                'error': _('Country not found.'),
                'navigation': _marketplace_navigation('compliance'),
            }
        if response.status_code != 200:
            return {
                'current_section': 'marketplace',
                'error': f'Cloud API returned {response.status_code}',
                'navigation': _marketplace_navigation('compliance'),
            }

        country = response.json()

        # Mark installed modules
        all_installed = True
        for mod in country.get('modules', []):
            mod['is_installed'] = mod.get('slug', '') in installed_ids or mod.get('module_id', '') in installed_ids
            if mod.get('is_mandatory') and not mod['is_installed']:
                all_installed = False

        cart = get_cart(request, 'modules')

        return {
            'current_section': 'marketplace',
            'page_title': country.get('country_name', 'Compliance'),
            'country': country,
            'all_installed': all_installed,
            'back_url': reverse('marketplace:compliance'),
            'cart_count': len(cart.get('items', [])),
            'cloud_api_url': cloud_api_url,
            'navigation': _marketplace_navigation('compliance'),
        }

    except requests.exceptions.RequestException as e:
        return {
            'current_section': 'marketplace',
            'error': f'Failed to connect to Cloud: {str(e)}',
            'navigation': _marketplace_navigation('compliance'),
        }
