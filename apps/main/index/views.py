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


def _render_icon_svg(icon_name):
    """Render an icon to SVG string using djicons for client-side use."""
    try:
        from djicons import icon as render_icon
        return str(render_icon(icon_name, size=28))
    except Exception:
        return ''


def get_modules_for_grid(menu_items):
    """
    Convert MODULE_MENU_ITEMS to a list suitable for the grid.
    Each module gets: id, label, icon, url, color, has_svg, svg_path, icon_svg
    """
    modules = []
    for item in menu_items:
        module_id = item.get('module_id', item.get('label', '').lower())
        icon_name = item.get('icon', 'cube-outline')
        modules.append({
            'id': module_id,
            'label': item.get('label', 'Module'),
            'icon': icon_name,
            'icon_svg': _render_icon_svg(icon_name),
            'url': item.get('url', '#'),
            'color': item.get('color', MODULE_COLORS.get(module_id, 'primary')),
            'has_svg': item.get('has_svg', False),
            'svg_path': item.get('svg_path', ''),
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
