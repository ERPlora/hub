"""
Decorators for module views.

Provides:
- @module_view: Automatic navigation and rendering for module views
- @require_active_subscription: Subscription verification
- @require_module_purchased: Purchase verification

Usage in module views:
    from apps.modules_runtime.decorators import module_view

    @module_view("inventory", "products")
    def products(request):
        return {'products': Product.objects.all()}
"""
import json
from functools import wraps
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from .subscription_checker import get_subscription_checker
from .loader import get_module_py, get_module_navigation
import logging

logger = logging.getLogger(__name__)


def require_active_subscription(view_func):
    """
    Decorator para views de módulos que requieren suscripción activa.

    Verifica que el módulo tenga una suscripción activa antes de ejecutar la vista.
    Si no hay suscripción activa, retorna un error.

    Usage:
        @require_active_subscription
        def my_view(request):
            ...
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        # Obtener module_id del módulo de la vista
        # El module_id está en el path del módulo: modules.{module_id}.views
        view_module = view_func.__module__
        parts = view_module.split('.')

        if 'modules' not in parts:
            logger.error(f"[SUBSCRIPTION] Decorator used outside module context: {view_module}")
            return JsonResponse({
                'error': 'Invalid module context'
            }, status=500)

        # Extraer module_id del módulo (e.g., modules.analytics.views -> analytics)
        try:
            module_index = parts.index('modules')
            module_slug = parts[module_index + 1]
        except (ValueError, IndexError):
            logger.error(f"[SUBSCRIPTION] Could not extract module_id from module: {view_module}")
            return JsonResponse({
                'error': 'Invalid module structure'
            }, status=500)

        # Verificar suscripción
        checker = get_subscription_checker()

        # Asumimos que es subscription type (el decorator solo se usa en módulos de suscripción)
        has_access = checker.verify_module_access(module_slug, module_type='subscription')

        if not has_access:
            logger.warning(
                f"[SUBSCRIPTION] Access denied to {view_module} - "
                f"subscription not active"
            )

            # Si es request AJAX, retornar JSON
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'error': 'Subscription required',
                    'message': 'This feature requires an active subscription. Please renew your subscription to continue.',
                    'subscription_required': True
                }, status=402)  # 402 Payment Required

            # Si es request normal, renderizar página de error
            return render(request, 'modules/subscription_required.html', {
                'module_slug': module_slug,
                'message': 'This feature requires an active subscription.'
            }, status=402)

        # Si tiene acceso, ejecutar vista normal
        return view_func(request, *args, **kwargs)

    return wrapper


def require_module_purchased(module_type='paid'):
    """
    Decorator para verificar que un módulo ha sido comprado.

    Args:
        module_type: 'paid' o 'subscription'

    Usage:
        @require_module_purchased(module_type='paid')
        def my_view(request):
            ...
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            # Obtener module_id del módulo
            view_module = view_func.__module__
            parts = view_module.split('.')

            if 'modules' not in parts:
                return JsonResponse({'error': 'Invalid module context'}, status=500)

            try:
                module_index = parts.index('modules')
                module_slug = parts[module_index + 1]
            except (ValueError, IndexError):
                return JsonResponse({'error': 'Invalid module structure'}, status=500)

            # Verificar acceso
            checker = get_subscription_checker()
            has_access = checker.verify_module_access(module_slug, module_type=module_type)

            if not has_access:
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({
                        'error': 'Purchase required',
                        'message': 'This feature requires purchasing the module.',
                        'purchase_required': True
                    }, status=402)

                return render(request, 'modules/purchase_required.html', {
                    'module_slug': module_slug,
                    'module_type': module_type
                }, status=402)

            return view_func(request, *args, **kwargs)

        return wrapper
    return decorator


def module_view(module_id: str, view_id: str, template_name: str = None):
    """
    Decorator for module views that handles navigation and rendering automatically.

    This decorator:
    1. Executes the view function to get context data
    2. Loads navigation from module.py
    3. Marks the active tab
    4. Detects if request is from same module (HTMX with X-Module-Id header)
    5. Renders with or without tabbar update accordingly

    Args:
        module_id: The module identifier (e.g., 'inventory', 'sections')
        view_id: The current view/tab identifier (e.g., 'products', 'categories')
        template_name: Optional custom template path. Defaults to '{module_id}/{view_id}.html'

    Usage:
        @module_view("inventory", "products")
        def products(request):
            return {'products': Product.objects.all()}

        # The decorator will:
        # - Add navigation, page_title, module_id to context
        # - Render inventory/products.html
        # - Include tabbar update script if coming from different module
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            # 1. Execute the original view function
            result = view_func(request, *args, **kwargs)

            # If already an HttpResponse, return as-is
            if isinstance(result, HttpResponse):
                return result

            # 2. Get module configuration
            module_py = get_module_py(module_id)
            navigation = get_module_navigation(module_id)

            # 3. Mark active tab
            for nav in navigation:
                nav['active'] = nav['id'] == view_id

            # 4. Build context
            context = result if isinstance(result, dict) else {}

            # Get module name (handle lazy translation)
            module_name = getattr(module_py, 'MODULE_NAME', module_id.title())
            if hasattr(module_name, '__str__'):
                module_name = str(module_name)

            # Get page title from navigation or module name
            page_title = next(
                (nav['label'] for nav in navigation if nav['id'] == view_id),
                module_name
            )

            context.update({
                'module_id': module_id,
                'module_name': module_name,
                'navigation': navigation,
                'navigation_json': json.dumps(navigation),
                'current_view': view_id,
                'page_title': page_title,
            })

            # 5. Determine rendering mode based on request context
            is_htmx = request.headers.get('HX-Request') == 'true'
            client_module = request.headers.get('X-Module-Id', '')
            same_module = client_module == module_id

            # Should we render the tabbar update script?
            # - Yes if: full page load OR coming from different module
            # - No if: HTMX request from same module (tab navigation)
            context['render_tabbar'] = not (is_htmx and same_module)

            # 6. Determine template
            tpl = template_name or f"{module_id}/{view_id}.html"

            return render(request, tpl, context)

        return wrapper
    return decorator
