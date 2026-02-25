"""
Context processors for core app
"""
from django.conf import settings


def cloud_url(request):
    """
    Add CLOUD_URL to template context
    """
    return {
        'CLOUD_URL': settings.CLOUD_API_URL
    }


def module_menu_items(request):
    """
    Add module menu items to template context
    """
    from apps.modules_runtime.loader import module_loader

    # Only load modules if user is authenticated
    if 'local_user_id' in request.session:
        menu_items = module_loader.get_menu_items()
    else:
        menu_items = []

    return {
        'MODULE_MENU_ITEMS': menu_items
    }


def hub_config_context(request):
    """
    Add hub_config and store_config to template context.

    This makes both HubConfig (language, currency, theme) and StoreConfig
    (business data) available in all templates without having to explicitly
    pass them in each view.
    """
    from apps.configuration.models import HubConfig, StoreConfig

    return {
        'hub_config': HubConfig.get_config(),
        'store_config': StoreConfig.get_config()
    }


def deployment_config(request):
    """
    Expose deployment configuration to templates.

    Makes DEPLOYMENT_MODE and related settings available in templates:
    - {{ DEPLOYMENT_MODE }} - 'local' or 'web'
    - {{ IS_LOCAL_DEPLOYMENT }} - True if local (desktop app)
    - {{ IS_WEB_DEPLOYMENT }} - True if web (browser)
    - {{ LOCAL_PRINT_SERVICE_URL }} - URL for local print service
    """
    deployment_mode = getattr(settings, 'DEPLOYMENT_MODE', 'local')

    return {
        'DEPLOYMENT_MODE': deployment_mode,
        'IS_LOCAL_DEPLOYMENT': deployment_mode == 'local',
        'IS_WEB_DEPLOYMENT': deployment_mode == 'web',
        'LOCAL_PRINT_SERVICE_URL': getattr(settings, 'LOCAL_PRINT_SERVICE_URL', 'http://localhost:8080'),
    }


def navigation_context(request):
    """
    Provide back button navigation context.

    Determines the appropriate back URL based on current path:
    - Home (/): No back button
    - Module main page (/m/{module}/): Back to home (/)
    - Module sub-page (/m/{module}/detail/): Back to module main (/m/{module}/)
    - System pages (/settings/, /files/, etc.): Back to home (/)
    - Sub-pages of system (/employees/add/): Back to parent (/employees/)

    Template variables:
    - {{ back_url }} - URL to navigate back to (None if at home)
    - {{ is_home }} - True if at home page
    - {{ is_module_page }} - True if in a module
    - {{ current_module }} - Module ID if in a module
    """
    import re

    path = request.path

    # Home page - no back button
    if path == '/':
        return {
            'back_url': None,
            'is_home': True,
            'is_module_page': False,
            'current_module': None,
        }

    # Module pages: /m/{module_id}/...
    module_match = re.match(r'^/m/([^/]+)(/.*)?$', path)
    if module_match:
        module_id = module_match.group(1)
        sub_path = module_match.group(2) or ''

        # Module main page (/m/sales/) -> back to home
        if sub_path in ('', '/'):
            return {
                'back_url': '/',
                'is_home': False,
                'is_module_page': True,
                'current_module': module_id,
            }

        # Module sub-page (/m/sales/detail/123/) -> back to module main
        return {
            'back_url': f'/m/{module_id}/',
            'is_home': False,
            'is_module_page': True,
            'current_module': module_id,
        }

    # System pages with sub-paths
    # e.g., /employees/add/ -> back to /employees/
    # e.g., /settings/ -> back to /
    parts = [p for p in path.split('/') if p]

    if len(parts) > 1:
        # Has sub-path, go to parent
        parent_path = '/' + '/'.join(parts[:-1]) + '/'
        return {
            'back_url': parent_path,
            'is_home': False,
            'is_module_page': False,
            'current_module': None,
        }

    # Top-level system page (/settings/, /files/, /modules/) -> back to home
    return {
        'back_url': '/',
        'is_home': False,
        'is_module_page': False,
        'current_module': None,
    }


def module_context(request):
    """
    Provide module context for tabbar rendering.

    Extracts module_id from URL pattern /m/{module_id}/...
    and attempts to extract current_view from the URL name.

    Template variables:
    - {{ current_module_id }} - Current module ID (e.g., 'inventory', 'sales')
    - {{ current_view }} - Current view within module (e.g., 'dashboard', 'products')

    The tabbar component uses these to:
    1. Load tabs from module.py using current_module_id
    2. Highlight the active tab using current_view
    """
    import re

    path = request.path

    # Extract module_id from /m/{module_id}/...
    module_match = re.match(r'^/m/([^/]+)(/.*)?$', path)
    if not module_match:
        return {
            'current_module_id': '',
            'current_view': '',
        }

    module_id = module_match.group(1)
    sub_path = module_match.group(2) or ''

    # Try to extract current_view from URL name
    # URL names typically follow pattern: {module}:{view}
    # e.g., 'inventory:products_list' -> 'products'
    # e.g., 'inventory:dashboard' -> 'dashboard'
    current_view = 'dashboard'  # Default

    try:
        resolver_match = request.resolver_match
        if resolver_match and resolver_match.url_name:
            url_name = resolver_match.url_name
            # Common patterns: 'dashboard', 'products_list', 'categories_index', etc.
            # Simplify to base view name
            view_name = url_name.replace('_list', '').replace('_index', '').replace('_detail', '')
            current_view = view_name
    except Exception:
        pass

    return {
        'current_module_id': module_id,
        'current_view': current_view,
    }
