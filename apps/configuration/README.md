# Configuration App - Singleton Pattern + Cache

Sistema de configuración global para Hub usando patrón Singleton + Caché.

## Características

✅ **Singleton Pattern**: Solo una instancia de configuración en la base de datos
✅ **Caché automático**: 1 hora de duración, invalidación automática al guardar
✅ **Acceso global**: Disponible en código Python y en templates
✅ **API conveniente**: Métodos para acceder a campos individuales o completos
✅ **Type-safe**: Con type hints para mejor autocompletado

## Modelos Disponibles

- **`HubConfig`**: Configuración del Hub (credenciales, idioma, tema, moneda)
- **`StoreConfig`**: Configuración de la tienda (datos fiscales, recibos)

---

## Uso en Código Python (Views, Utils, etc.)

### 1. Obtener la instancia completa

```python
from apps.configuration.models import HubConfig, StoreConfig

# Opción 1: Método recomendado
hub_config = HubConfig.get_solo()
store_config = StoreConfig.get_solo()

# Opción 2: Alias para compatibilidad
hub_config = HubConfig.get_config()
```

### 2. Obtener un campo específico

```python
# Con valor por defecto
currency = HubConfig.get_value('currency', 'EUR')
is_configured = HubConfig.get_value('is_configured', False)
dark_mode = HubConfig.get_value('dark_mode', False)

# Store config
business_name = StoreConfig.get_value('business_name', 'My Store')
tax_rate = StoreConfig.get_value('tax_rate', 0.21)
```

### 3. Actualizar un campo

```python
# Actualizar un solo campo
HubConfig.set_value('currency', 'EUR')
HubConfig.set_value('dark_mode', True)

StoreConfig.set_value('business_name', 'Mi Tienda')
StoreConfig.set_value('tax_rate', 21.00)
```

### 4. Actualizar múltiples campos

```python
# Actualizar varios campos a la vez (más eficiente)
HubConfig.update_values(
    currency='EUR',
    dark_mode=True,
    auto_print=False
)

StoreConfig.update_values(
    business_name='Mi Tienda',
    tax_rate=21.00,
    tax_included=True
)
```

### 5. Obtener todos los valores como diccionario

```python
# Útil para serialización o debugging
hub_config_dict = HubConfig.get_all_values()
print(hub_config_dict)
# {
#     'hub_id': UUID('...'),
#     'cloud_api_token': '...',
#     'is_configured': True,
#     'currency': 'EUR',
#     'dark_mode': False,
#     ...
# }
```

---

## Uso en Templates

Las configuraciones están disponibles automáticamente en todos los templates via context processor.

### Variables disponibles

- `{{ HUB_CONFIG }}` - Instancia completa de HubConfig
- `{{ STORE_CONFIG }}` - Instancia completa de StoreConfig

### Ejemplos

```django
<!-- Acceso directo a campos -->
<p>Currency: {{ HUB_CONFIG.currency }}</p>
<p>Dark Mode: {{ HUB_CONFIG.dark_mode }}</p>
<p>Business Name: {{ STORE_CONFIG.business_name }}</p>
<p>Tax Rate: {{ STORE_CONFIG.tax_rate }}%</p>

<!-- Condicionales -->
{% if HUB_CONFIG.is_configured %}
    <p>Hub is configured!</p>
{% else %}
    <p>Please configure your hub</p>
{% endif %}

{% if HUB_CONFIG.dark_mode %}
    <body class="dark-theme">
{% else %}
    <body class="light-theme">
{% endif %}

<!-- Usar en atributos -->
<div data-currency="{{ HUB_CONFIG.currency }}">
    <span class="price">{{ product.price }}</span>
</div>
```

---

## API Reference

### `SingletonConfigMixin`

Mixin base que proporciona toda la funcionalidad singleton + caché.

#### Métodos de clase

- **`get_solo()`**: Obtiene la instancia singleton (con caché)
- **`get_config()`**: Alias para compatibilidad
- **`get_value(field_name, default=None)`**: Obtiene un campo específico
- **`set_value(field_name, value)`**: Actualiza un campo
- **`update_values(**kwargs)`**: Actualiza múltiples campos
- **`get_all_values()`**: Devuelve todos los campos como dict

#### Comportamiento del caché

- **Timeout**: 1 hora (configurable via `CACHE_TIMEOUT`)
- **Invalidación automática**: Al hacer `save()`
- **Cache key**: `config_{modelname}_instance`

#### Protecciones

- Solo permite una instancia con `id=1`
- Previene eliminación accidental (requiere `force_delete=True`)
- Manejo de errores robusto con valores por defecto

---

## Ejemplos Completos

### View con acceso a configuración

```python
from django.shortcuts import render
from apps.configuration.models import HubConfig, StoreConfig

def dashboard_view(request):
    # Acceso directo (no es necesario pasar al context, ya está disponible)
    currency = HubConfig.get_value('currency')

    # O puedes obtener la instancia completa para lógica compleja
    hub_config = HubConfig.get_solo()

    if not hub_config.is_configured:
        return redirect('configuration:setup')

    context = {
        'current_currency': currency,
        # HUB_CONFIG y STORE_CONFIG ya están disponibles en template
    }
    return render(request, 'dashboard.html', context)
```

### Actualizar configuración desde vista

```python
from django.http import JsonResponse
from apps.configuration.models import HubConfig

def update_theme(request):
    if request.method == 'POST':
        dark_mode = request.POST.get('dark_mode') == 'true'

        # Actualizar configuración
        success = HubConfig.set_value('dark_mode', dark_mode)

        if success:
            return JsonResponse({'success': True})
        else:
            return JsonResponse({'success': False, 'error': 'Failed to update'})
```

### Signal para reaccionar a cambios

```python
from django.db.models.signals import post_save
from django.dispatch import receiver
from apps.configuration.models import HubConfig

@receiver(post_save, sender=HubConfig)
def on_hub_config_change(sender, instance, **kwargs):
    # Hacer algo cuando cambia la configuración
    print(f"Config updated: currency={instance.currency}")

    # El caché ya se invalidó automáticamente
    # Puedes hacer otras acciones aquí
```

---

## Testing

```python
from apps.configuration.models import HubConfig

def test_hub_config_singleton():
    # Obtener instancia
    config1 = HubConfig.get_solo()
    config2 = HubConfig.get_solo()

    # Verificar que es la misma instancia
    assert config1.id == config2.id == 1

    # Actualizar valor
    HubConfig.set_value('currency', 'EUR')

    # Verificar que se actualizó
    assert HubConfig.get_value('currency') == 'EUR'

    # Obtener todos los valores
    all_values = HubConfig.get_all_values()
    assert 'currency' in all_values
    assert all_values['currency'] == 'EUR'
```

---

## Performance

- **Primera llamada**: Query a base de datos + guardar en caché
- **Llamadas subsecuentes**: Servido desde caché (sin query)
- **Duración del caché**: 1 hora
- **Invalidación**: Automática al guardar

El sistema está optimizado para lectura frecuente y escritura ocasional, que es el caso típico de configuración de aplicación.
