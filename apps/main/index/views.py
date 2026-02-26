"""
Main Index Views - Dashboard home with iOS-style module grid
"""
from apps.core.htmx import htmx_view
from apps.accounts.decorators import login_required


# Default colors for modules without a specified color
MODULE_COLORS = {
    'inventory': 'primary',
    'sales': 'success',
    'cash_register': 'warning',
    'customers': 'tertiary',
    'loyalty': 'danger',
    'invoicing': 'secondary',
    'returns': 'medium',
    'verifactu': 'dark',
    'tables': 'primary',
    'sections': 'tertiary',
}


def get_modules_for_grid(menu_items):
    """
    Convert MODULE_MENU_ITEMS to a list suitable for the grid.
    Each module gets: id, label, icon, url, color, has_svg, svg_path
    """
    modules = []
    for item in menu_items:
        module_id = item.get('module_id', item.get('label', '').lower())
        modules.append({
            'id': module_id,
            'label': item.get('label', 'Module'),
            'icon': item.get('icon', 'cube-outline'),
            'url': item.get('url', '#'),
            'color': item.get('color', MODULE_COLORS.get(module_id, 'primary')),
            'has_svg': item.get('has_svg', False),
            'svg_path': item.get('svg_path', ''),
        })
    return modules


def _build_setup_alerts(menu_items):
    """Build onboarding alerts for the home page when setup steps are incomplete."""
    from django.urls import reverse
    from django.utils.translation import gettext as _
    from apps.configuration.models import StoreConfig

    alerts = []
    store_config = StoreConfig.get_config()

    # Alert 1: Business not configured
    if not store_config.business_name:
        alerts.append({
            'id': 'config',
            'icon': 'settings-outline',
            'title': _('Configure your business'),
            'description': _('Set your business name, address, tax info, language, and timezone.'),
            'link': reverse('main:settings'),
            'link_text': _('Go to Settings'),
            'color': 'warning',
        })

    # Alert 2: No modules installed
    if not menu_items:
        alerts.append({
            'id': 'modules',
            'icon': 'cube-outline',
            'title': _('Install modules'),
            'description': _('Visit the Marketplace to find modules for your business type.'),
            'link': reverse('marketplace:index'),
            'link_text': _('Browse Marketplace'),
            'color': 'primary',
        })

    # Alert 3: Roles not configured
    from apps.accounts.models import Role
    if not Role.objects.filter(source='custom').exists() and not Role.objects.filter(source='solution').exists():
        alerts.append({
            'id': 'roles',
            'icon': 'people-outline',
            'title': _('Set up roles'),
            'description': _('Create custom roles for your employees or install modules to auto-generate roles.'),
            'link': reverse('main:roles:list'),
            'link_text': _('Manage Roles'),
            'color': 'info',
        })

    return alerts


@login_required
@htmx_view('main/index/pages/index.html', 'main/index/partials/content.html')
def index(request):
    """Dashboard home page with iOS-style module grid"""
    from apps.modules_runtime.loader import module_loader
    menu_items = module_loader.get_menu_items()

    alerts = _build_setup_alerts(menu_items)

    return {
        'current_section': 'home',
        'page_title': 'Home',
        'modules': get_modules_for_grid(menu_items),
        'alerts': alerts,
    }
