"""
Marketplace Views - Multi-store marketplace with sidebar filters and cart

Supports multiple store types:
- modules: Software modules from Cloud
- hubs: Hub instances (coming soon)
- components: Hardware components (coming soon)
- products: Third-party products (coming soon)
"""
import json
import requests
from pathlib import Path
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.conf import settings as django_settings
from django.urls import reverse

from apps.core.htmx import htmx_view
from apps.accounts.decorators import login_required


# Store type configurations
STORE_TYPES = {
    'modules': {
        'name': 'Modules',
        'name_es': 'Módulos',
        'icon': 'cube-outline',
        'api_endpoint': '/api/marketplace/modules/',
        'enabled': True,
        'filters': ['category', 'industry', 'type'],
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
    }


def _get_filters_for_store(store_type, language, request):
    """Get filter options based on store type"""
    from apps.configuration.models import HubConfig
    from config.module_categories import get_all_categories, get_all_industries

    filters = {}
    hub_config = HubConfig.get_solo()
    auth_token = hub_config.hub_jwt or hub_config.cloud_api_token

    if store_type == 'modules':
        # Categories and industries for modules
        categories = get_all_categories(language)
        industries = get_all_industries(language)

        if auth_token:
            cloud_api_url = getattr(django_settings, 'CLOUD_API_URL', 'https://erplora.com')
            headers = {'Accept': 'application/json', 'X-Hub-Token': auth_token}
            try:
                cat_response = requests.get(
                    f"{cloud_api_url}/api/marketplace/categories/",
                    headers=headers, params={'language': language}, timeout=10
                )
                if cat_response.status_code == 200:
                    cloud_categories = cat_response.json()
                    if cloud_categories:
                        categories = cloud_categories

                ind_response = requests.get(
                    f"{cloud_api_url}/api/marketplace/industries/",
                    headers=headers, params={'language': language}, timeout=10
                )
                if ind_response.status_code == 200:
                    cloud_industries = ind_response.json()
                    if cloud_industries:
                        industries = cloud_industries
            except Exception:
                pass

        filters['categories'] = categories
        filters['industries'] = industries
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
    """Add item to cart (HTMX endpoint)"""
    if request.method != 'POST':
        return HttpResponse(status=405)

    try:
        data = json.loads(request.body)
        item_id = data.get('item_id')
        item_name = data.get('item_name', '')
        item_price = float(data.get('item_price', 0))
        item_icon = data.get('item_icon', 'cube-outline')
        quantity = int(data.get('quantity', 1))
    except (json.JSONDecodeError, ValueError):
        return HttpResponse(status=400)

    if not item_id:
        return HttpResponse(status=400)

    cart = get_cart(request, store_type)

    # Check if item already in cart
    for item in cart['items']:
        if item['id'] == item_id:
            item['quantity'] += quantity
            break
    else:
        cart['items'].append({
            'id': item_id,
            'name': item_name,
            'price': item_price,
            'icon': item_icon,
            'quantity': quantity,
        })

    # Recalculate total
    cart['total'] = sum(item['price'] * item['quantity'] for item in cart['items'])
    save_cart(request, store_type, cart)

    # Return updated cart partial + badge OOB swap
    html = render_to_string('marketplace/partials/cart_content.html', {
        'cart': cart,
        'store_type': store_type,
    }, request=request)

    badge_html = f'''
    <span id="cart-badge" class="badge color-error" hx-swap-oob="true">
        {len(cart['items'])}
    </span>
    '''

    return HttpResponse(html + badge_html)


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
    badge_html = f'''
    <span id="cart-badge" class="badge color-error" hx-swap-oob="true" {'style="display:none"' if badge_count == 0 else ''}>
        {badge_count}
    </span>
    '''

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

    badge_html = '''
    <span id="cart-badge" class="badge color-error" hx-swap-oob="true" style="display:none">
        0
    </span>
    '''

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


# Products list with infinite scroll

@login_required
def products_list(request, store_type):
    """
    HTMX endpoint: Fetch and render products with infinite scroll support.
    Returns HTML partial with product cards.
    Supports filters: q (search), category, industry, type, cursor
    """
    from apps.configuration.models import HubConfig

    # Get filters from query params
    search_query = request.GET.get('q', '').strip()
    category_filter = request.GET.get('category', '').strip()
    industry_filter = request.GET.get('industry', '').strip()
    type_filter = request.GET.get('type', '').strip()
    cursor = request.GET.get('cursor', '')
    page_size = 12

    config = get_store_config(store_type)

    if store_type == 'modules':
        return _fetch_modules_list(request, search_query, category_filter, industry_filter, type_filter, cursor, page_size)
    elif store_type == 'hubs':
        return _fetch_hubs_list(request, search_query, cursor, page_size)
    else:
        # Coming soon stores
        html = render_to_string('marketplace/partials/coming_soon.html', {
            'store_type': store_type,
            'store_config': config,
        }, request=request)
        return HttpResponse(html)


def _fetch_modules_list(request, search_query, category_filter, industry_filter, type_filter, cursor, page_size):
    """Fetch modules from Cloud API"""
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
            modules = [m for m in modules if m.get('category') == category_filter]

        if industry_filter:
            modules = [m for m in modules if industry_filter in m.get('industries', [])]

        if type_filter:
            modules = [m for m in modules if m.get('module_type') == type_filter]

        # Mark installed and add URLs
        for module in modules:
            module['is_installed'] = module.get('slug', '') in installed_module_ids
            module['detail_url'] = reverse('marketplace:module_detail', kwargs={'slug': module.get('slug', '')})

        # Simple cursor-based pagination (using index)
        start_index = int(cursor) if cursor.isdigit() else 0
        end_index = start_index + page_size
        page_modules = modules[start_index:end_index]
        has_more = end_index < len(modules)
        next_cursor = str(end_index) if has_more else ''

        html = render_to_string('marketplace/partials/products_grid.html', {
            'products': page_modules,
            'store_type': 'modules',
            'has_more': has_more,
            'next_cursor': next_cursor,
            'search_query': search_query,
            'category_filter': category_filter,
            'industry_filter': industry_filter,
            'type_filter': type_filter,
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
        }

    except requests.exceptions.RequestException as e:
        return {
            'current_section': 'marketplace',
            'error': f'Failed to connect to Cloud: {str(e)}',
            'cart_count': 0,
        }
