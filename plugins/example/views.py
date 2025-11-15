"""
Vistas del plugin Example Plugin.

Este módulo demuestra cómo crear vistas para plugins en CPOS Hub.

Características clave:
- Usa @login_required para proteger vistas
- Pasa contexto a los templates
- Renderiza templates desde plugins/example/templates/example/
"""

from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from apps.accounts.decorators import login_required


@login_required
def index(request):
    """
    Vista principal del plugin Example.

    Renderiza una página con ejemplos interactivos usando:
    - Ionic 8 components (cards, buttons, forms, tabs)
    - Alpine.js para reactividad (contador, formulario, tabs)
    - HTMX para interacciones AJAX

    Args:
        request: HttpRequest object

    Returns:
        HttpResponse: Template renderizado con contexto

    Template:
        example/index.html

    Context:
        plugin_name (str): Nombre del plugin
        version (str): Versión del plugin
        features (list): Lista de características
    """
    context = {
        'plugin_name': 'Example Plugin',
        'version': '0.1.0',
        'features': [
            'Ionic 8 Components',
            'Alpine.js Reactivity',
            'HTMX Interactivity',
            'Responsive Design',
            'Interactive Examples'
        ]
    }
    return render(request, 'example/index.html', context)


# Ejemplo de API endpoint
@login_required
@require_http_methods(["GET"])
def api_status(request):
    """
    Ejemplo de API endpoint.

    Retorna el estado del plugin en formato JSON.
    Útil para llamadas AJAX con HTMX o Alpine.js.

    Args:
        request: HttpRequest object

    Returns:
        JsonResponse: Estado del plugin

    Example:
        GET /example/api/status/

        Response:
        {
            "success": true,
            "plugin": "example",
            "version": "0.1.0",
            "status": "active"
        }
    """
    return JsonResponse({
        'success': True,
        'plugin': 'example',
        'version': '0.1.0',
        'status': 'active'
    })


# Agregar más vistas según necesites:
# - Formularios (crear, editar, eliminar)
# - APIs REST
# - Vistas de administración
# - Reportes
# - etc.
