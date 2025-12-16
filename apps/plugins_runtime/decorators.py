"""
Decorators for plugin views to enforce subscription checks.

Usage in plugin views:
    from apps.plugins_runtime.decorators import require_active_subscription

    @require_active_subscription
    def my_premium_view(request):
        # This view only executes if subscription is active
        ...
"""
from functools import wraps
from django.http import JsonResponse
from django.shortcuts import render
from .subscription_checker import get_subscription_checker
import logging

logger = logging.getLogger(__name__)


def require_active_subscription(view_func):
    """
    Decorator para views de plugins que requieren suscripción activa.

    Verifica que el plugin tenga una suscripción activa antes de ejecutar la vista.
    Si no hay suscripción activa, retorna un error.

    Usage:
        @require_active_subscription
        def my_view(request):
            ...
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        # Obtener plugin_id del módulo de la vista
        # El plugin_id está en el path del módulo: plugins.{plugin_id}.views
        view_module = view_func.__module__
        parts = view_module.split('.')

        if 'plugins' not in parts:
            logger.error(f"[SUBSCRIPTION] Decorator used outside plugin context: {view_module}")
            return JsonResponse({
                'error': 'Invalid plugin context'
            }, status=500)

        # Extraer plugin_id del módulo (e.g., plugins.analytics.views -> analytics)
        try:
            plugin_index = parts.index('plugins')
            plugin_slug = parts[plugin_index + 1]
        except (ValueError, IndexError):
            logger.error(f"[SUBSCRIPTION] Could not extract plugin_id from module: {view_module}")
            return JsonResponse({
                'error': 'Invalid plugin structure'
            }, status=500)

        # Verificar suscripción
        checker = get_subscription_checker()

        # Asumimos que es subscription type (el decorator solo se usa en plugins de suscripción)
        has_access = checker.verify_plugin_access(plugin_slug, plugin_type='subscription')

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
            return render(request, 'plugins/subscription_required.html', {
                'plugin_slug': plugin_slug,
                'message': 'This feature requires an active subscription.'
            }, status=402)

        # Si tiene acceso, ejecutar vista normal
        return view_func(request, *args, **kwargs)

    return wrapper


def require_plugin_purchased(plugin_type='paid'):
    """
    Decorator para verificar que un plugin ha sido comprado.

    Args:
        plugin_type: 'paid' o 'subscription'

    Usage:
        @require_plugin_purchased(plugin_type='paid')
        def my_view(request):
            ...
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            # Obtener plugin_id del módulo
            view_module = view_func.__module__
            parts = view_module.split('.')

            if 'plugins' not in parts:
                return JsonResponse({'error': 'Invalid plugin context'}, status=500)

            try:
                plugin_index = parts.index('plugins')
                plugin_slug = parts[plugin_index + 1]
            except (ValueError, IndexError):
                return JsonResponse({'error': 'Invalid plugin structure'}, status=500)

            # Verificar acceso
            checker = get_subscription_checker()
            has_access = checker.verify_plugin_access(plugin_slug, plugin_type=plugin_type)

            if not has_access:
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({
                        'error': 'Purchase required',
                        'message': 'This feature requires purchasing the plugin.',
                        'purchase_required': True
                    }, status=402)

                return render(request, 'plugins/purchase_required.html', {
                    'plugin_slug': plugin_slug,
                    'plugin_type': plugin_type
                }, status=402)

            return view_func(request, *args, **kwargs)

        return wrapper
    return decorator
