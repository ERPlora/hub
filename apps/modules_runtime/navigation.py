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
from django.template.loader import render_to_string

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
        # dashboard maps to module root (empty path)
        if view_name == 'dashboard':
            item['url'] = f"/m/{module_id}/"
        elif view_name:
            item['url'] = f"/m/{module_id}/{view_name}/"
        else:
            item['url'] = f"/m/{module_id}/"
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
    Decorator that injects module navigation into view responses.

    Attaches module context to request._module_nav so @htmx_view can pick it up.
    For HTMX responses, also appends an OOB tabbar swap to update the footer.

    Place BEFORE @htmx_view in decorator stack:

        @login_required
        @with_module_nav('inventory', 'products')
        @htmx_view('inventory/pages/products.html', 'inventory/partials/products_content.html')
        def products_list(request):
            return {'products': Product.objects.all()}
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            module_ctx = build_module_context(module_id, view_id)

            # Attach to request so @htmx_view can merge it into template context
            request._module_nav = module_ctx

            result = view_func(request, *args, **kwargs)

            if isinstance(result, dict):
                # If @htmx_view wasn't used, merge directly
                for key, value in module_ctx.items():
                    result.setdefault(key, value)
                return result

            # Post-htmx_view: result is HttpResponse
            # Append OOB tabbar for HTMX requests so footer updates
            is_htmx = request.headers.get('HX-Request')
            if is_htmx and isinstance(result, HttpResponse):
                content_type = result.get('Content-Type', '')
                if 'text/html' in content_type:
                    oob_html = render_to_string(
                        'partials/tabbar_oob.html',
                        module_ctx,
                        request=request,
                    )
                    result.content = result.content + oob_html.encode('utf-8')

                # Also merge pageTitle into existing HX-Trigger
                page_title = module_ctx.get('page_title')
                if page_title:
                    existing = result.get('HX-Trigger', '')
                    try:
                        triggers = json.loads(existing) if existing else {}
                    except (json.JSONDecodeError, TypeError):
                        triggers = {}
                    triggers['pageTitle'] = str(page_title)
                    result['HX-Trigger'] = json.dumps(triggers)

            return result

        return wrapper
    return decorator
