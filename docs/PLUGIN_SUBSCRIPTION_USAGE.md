# Plugin Subscription Usage Guide

Guía para desarrolladores de plugins sobre cómo implementar verificación de compra y suscripciones.

## Tipos de Plugins

ERPlora soporta 3 tipos de plugins:

1. **Free** - Gratis, sin verificación
2. **Paid** - Pago único, verificado en instalación
3. **Subscription** - Suscripción mensual, verificado en runtime

## Configuración en plugin.json

```json
{
  "plugin_id": "multi_device",
  "name": "Multi-Device Support",
  "version": "1.0.0",
  "plugin_type": "subscription",
  "price": 9.99,
  "cloud_plugin_id": 123,  // ID del plugin en Cloud
  ...
}
```

## Verificación de Suscripciones en Views

### Opción 1: Decorator (Recomendado)

```python
# plugins/multi_device/views.py
from apps.plugins_runtime.decorators import require_active_subscription
from django.shortcuts import render

@require_active_subscription
def sync_devices(request):
    """
    Esta vista solo se ejecuta si la suscripción está activa.
    Si no está activa, retorna error 402 automáticamente.
    """
    # Tu lógica aquí
    return render(request, 'multi_device/sync.html')
```

### Opción 2: Verificación Manual

```python
# plugins/my_plugin/views.py
from apps.plugins_runtime.subscription_checker import get_subscription_checker
from django.shortcuts import render
from django.http import JsonResponse

def premium_feature(request):
    checker = get_subscription_checker()

    # Verificar acceso
    has_access = checker.verify_plugin_access(
        plugin_slug='multi_device',
        plugin_type='subscription'
    )

    if not has_access:
        return JsonResponse({
            'error': 'Subscription required',
            'message': 'Please subscribe to use this feature'
        }, status=402)

    # Feature está disponible
    return render(request, 'my_plugin/premium.html')
```

### Opción 3: Verificación Detallada

```python
# plugins/my_plugin/views.py
from apps.plugins_runtime.subscription_checker import get_subscription_checker
from django.shortcuts import render

def advanced_feature(request):
    checker = get_subscription_checker()

    # Obtener estado detallado de suscripción
    status = checker.check_subscription_status(plugin_id=123)

    if not status.get('has_active_subscription'):
        context = {
            'error': 'Subscription not active',
            'status': status.get('subscription_status'),
            'period_end': status.get('current_period_end')
        }
        return render(request, 'my_plugin/subscription_error.html', context)

    # Suscripción activa
    return render(request, 'my_plugin/feature.html')
```

## Verificación en API Endpoints

```python
# plugins/my_plugin/api.py
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from apps.plugins_runtime.subscription_checker import get_subscription_checker

@api_view(['POST'])
def api_premium_action(request):
    checker = get_subscription_checker()

    has_access = checker.verify_plugin_access('my_plugin', 'subscription')

    if not has_access:
        return Response({
            'error': 'Subscription required'
        }, status=status.HTTP_402_PAYMENT_REQUIRED)

    # Procesar request
    return Response({'success': True})
```

## Cache de Estado de Suscripciones

El sistema cachea el estado de suscripciones por **5 minutos** para evitar requests excesivos a Cloud.

### Limpiar Cache Manualmente

```python
from apps.plugins_runtime.subscription_checker import get_subscription_checker

checker = get_subscription_checker()

# Limpiar cache de un plugin específico
checker.clear_cache(plugin_id=123)

# Limpiar todo el cache
checker.clear_cache()
```

## Respuestas del Sistema

### Suscripción Activa

```json
{
  "has_active_subscription": true,
  "subscription_status": "active",
  "current_period_end": 1737388800,
  "cancel_at_period_end": false
}
```

### Suscripción Inactiva

```json
{
  "has_active_subscription": false,
  "subscription_status": "canceled"
}
```

### Sin Conexión a Internet

```json
{
  "has_active_subscription": false,
  "subscription_status": "offline",
  "error": "No internet connection"
}
```

## Templates de Error

El sistema incluye templates por defecto para errores de suscripción:

- `plugins/subscription_required.html` - Suscripción requerida
- `plugins/purchase_required.html` - Compra requerida

Puedes sobrescribirlos en tu plugin:

```django
<!-- plugins/my_plugin/templates/plugins/subscription_required.html -->
{% extends "core/app_base.html" %}

{% block content %}
<div style="text-align: center; padding: 48px;">
    <ion-icon name="lock-closed-outline" style="font-size: 64px; color: var(--ion-color-warning);"></ion-icon>
    <h2>Subscription Required</h2>
    <p>{{ message }}</p>
    <ion-button href="/plugins/marketplace/">
        Subscribe Now
    </ion-button>
</div>
{% endblock %}
```

## Flujo Completo de Suscripción

1. **Usuario navega a marketplace** → `/plugins/marketplace/`
2. **Click en plugin de suscripción** → Muestra precio mensual
3. **Click "Subscribe"** → Crea Stripe Checkout session
4. **Redirect a Stripe** → Usuario completa pago
5. **Webhook procesa pago** → Cloud crea PluginPurchase
6. **Usuario retorna a Hub** → Puede instalar plugin
7. **Plugin instalado** → Features requieren verificación online
8. **Usuario usa feature** → Decorator verifica suscripción
9. **Cache por 5 min** → Reduce latencia en requests subsecuentes

## Ejemplo Completo: Multi-Device Plugin

```python
# plugins/multi_device/views.py
from apps.plugins_runtime.decorators import require_active_subscription
from django.shortcuts import render
from django.http import JsonResponse
import json

@require_active_subscription
def dashboard(request):
    """Dashboard principal - requiere suscripción activa"""
    return render(request, 'multi_device/dashboard.html')

@require_active_subscription
def sync_data(request):
    """API para sincronizar datos - requiere suscripción activa"""
    if request.method == 'POST':
        # Sincronizar con Cloud
        data = json.loads(request.body)
        # ... lógica de sync
        return JsonResponse({'success': True})

    return JsonResponse({'error': 'Method not allowed'}, status=405)

def check_status(request):
    """Endpoint público para verificar estado"""
    from apps.plugins_runtime.subscription_checker import get_subscription_checker

    checker = get_subscription_checker()
    status = checker.check_subscription_status(plugin_id=123)

    return JsonResponse(status)
```

## Best Practices

1. **Usar decorator siempre que sea posible** - Más limpio y mantenible
2. **Cachear wisely** - No limpiar cache innecesariamente
3. **Manejar offline gracefully** - Informar al usuario si no hay internet
4. **UX clara** - Mostrar mensajes claros cuando falta suscripción
5. **Verificar solo features premium** - Features básicas pueden ser free
6. **Logging apropiado** - Loggear intentos de acceso sin suscripción

## Troubleshooting

### "Subscription not active" aunque pagué

- Verificar que el webhook de Stripe se procesó correctamente
- Limpiar cache: `checker.clear_cache(plugin_id=X)`
- Verificar en Cloud admin que existe `PluginPurchase` con status='completed'

### "No internet connection" constante

- Verificar `CLOUD_API_URL` en settings
- Verificar que `hub_config.cloud_api_token` existe
- Verificar firewall no bloquea requests HTTP

### Cache no se limpia

- Cache usa Django cache backend (settings.CACHES)
- Verificar que cache backend está funcionando
- Usar Redis en producción para mejor performance

## Testing

```python
# plugins/my_plugin/tests.py
from django.test import TestCase
from apps.plugins_runtime.subscription_checker import get_subscription_checker
from unittest.mock import patch

class SubscriptionTests(TestCase):

    @patch('requests.get')
    def test_active_subscription(self, mock_get):
        # Mock Cloud API response
        mock_get.return_value.json.return_value = {
            'has_active_subscription': True,
            'subscription_status': 'active'
        }
        mock_get.return_value.ok = True

        checker = get_subscription_checker()
        has_access = checker.verify_plugin_access('my_plugin', 'subscription')

        self.assertTrue(has_access)

    @patch('requests.get')
    def test_inactive_subscription(self, mock_get):
        # Mock inactive subscription
        mock_get.return_value.json.return_value = {
            'has_active_subscription': False,
            'subscription_status': 'canceled'
        }
        mock_get.return_value.ok = True

        checker = get_subscription_checker()
        has_access = checker.verify_plugin_access('my_plugin', 'subscription')

        self.assertFalse(has_access)
```

## Referencias

- **Cloud API**: `/api/plugins/{id}/subscription-status/`
- **Hub Checker**: `apps.plugins_runtime.subscription_checker`
- **Decorators**: `apps.plugins_runtime.decorators`
- **Cache**: Django cache framework
- **Stripe**: webhooks procesados en Cloud
