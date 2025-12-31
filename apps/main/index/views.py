"""
Main Index Views - Dashboard home with iOS-style module grid
"""
import json
from django.shortcuts import redirect
from django.utils import timezone
from datetime import timedelta
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
    Each module gets: id, label, icon, url, color
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
        })
    return modules


@login_required
@htmx_view('main/index/pages/index.html', 'main/index/partials/content.html')
def index(request):
    """Dashboard home page with iOS-style module grid"""
    # Get modules from module loader (same source as context processor)
    from apps.modules_runtime.loader import module_loader
    menu_items = module_loader.get_menu_items()

    # Convert to grid-friendly format
    modules = get_modules_for_grid(menu_items)

    return {
        'current_section': 'home',
        'page_title': 'Home',
        'modules': modules,
        'modules_json': json.dumps(modules),
    }
