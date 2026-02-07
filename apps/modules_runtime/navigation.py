"""
Navigation helpers for module views.

Provides utilities to build module navigation context
and a decorator to inject it into views automatically.
"""
import json
from functools import wraps
from pathlib import Path
from django.conf import settings
from django.http import HttpResponse

from .loader import get_module_py


def get_module_navigation_items(module_id: str) -> list:
    """
    Get navigation items for a module, trying module.py first, then module.json.

    Returns list of nav dicts with keys: label, icon, id, url
    """
    # Try module.py first
    module_py = get_module_py(module_id)
    navigation = getattr(module_py, 'NAVIGATION', [])

    # Fallback to module.json if NAVIGATION is empty
    if not navigation:
        modules_dir = Path(settings.MODULES_DIR)
        # Try both enabled and disabled module names
        for name in [module_id, f'_{module_id}']:
            json_path = modules_dir / name / 'module.json'
            if json_path.exists():
                try:
                    with open(json_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    navigation = data.get('navigation', [])
                    break
                except Exception:
                    pass

    # Build items with resolved URLs
    nav_items = []
    for nav in navigation:
        item = dict(nav)
        view_name = item.get('view', item.get('id', ''))
        item['url'] = f"/m/{module_id}/{view_name}/" if view_name else f"/m/{module_id}/"
        # Convert lazy strings
        if hasattr(item.get('label'), '__str__'):
            item['label'] = str(item['label'])
        nav_items.append(item)

    return nav_items


def build_module_context(module_id: str, view_id: str) -> dict:
    """
    Build the standard module context for module_base.html.

    Returns dict with: navigation, page_title, module_id, current_view
    """
    navigation = get_module_navigation_items(module_id)

    # Mark active tab and find page title
    page_title = module_id.replace('_', ' ').title()
    for nav in navigation:
        nav['active'] = nav.get('id') == view_id
        if nav['active']:
            page_title = nav['label']

    return {
        'navigation': navigation,
        'page_title': page_title,
        'module_id': module_id,
        'current_view': view_id,
    }


def with_module_nav(module_id: str, view_id: str):
    """
    Decorator that injects module navigation context into view results.

    Composes with @htmx_view - place BEFORE @htmx_view in decorator stack.

    Usage:
        @login_required
        @with_module_nav('inventory', 'products')
        @htmx_view('inventory/pages/products.html', 'inventory/partials/products_content.html')
        def products_list(request):
            return {'products': Product.objects.all()}
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            result = view_func(request, *args, **kwargs)

            # Only inject into dict results (not HttpResponse)
            if isinstance(result, dict):
                module_ctx = build_module_context(module_id, view_id)
                # Don't overwrite existing keys from the view
                for key, value in module_ctx.items():
                    result.setdefault(key, value)

            return result

        return wrapper
    return decorator
