# Toast Helper - JavaScript Utility

Helper JavaScript para mostrar notificaciones toast de Ionic de forma consistente.

## Instalación

Incluir el script en el template:

```django
{% load static %}
<script src="{% static 'components/toast_helper/toast-helper.js' %}"></script>
```

## Uso

### Función Principal: `showToast()`

```javascript
showToast(message, color, duration, position)
```

**Parámetros:**
- `message` (string, requerido): Mensaje a mostrar
- `color` (string, opcional): Color del toast (default: 'primary')
  - Opciones: `success`, `danger`, `warning`, `primary`, `secondary`, `tertiary`, `dark`, `light`
- `duration` (number, opcional): Duración en milisegundos (default: 2000)
- `position` (string, opcional): Posición del toast (default: 'bottom')
  - Opciones: `top`, `bottom`, `middle`

### Ejemplos Básicos

```javascript
// Toast básico (primary, 2 segundos)
showToast('Operation completed');

// Toast de éxito
showToast('Hub registered successfully!', 'success');

// Toast de error con duración personalizada
showToast('Failed to connect', 'danger', 5000);

// Toast warning en la parte superior
showToast('Connection unstable', 'warning', 3000, 'top');
```

### Shortcuts con el Objeto `Toast`

Para mayor conveniencia, usa los shortcuts:

```javascript
// Success toast
Toast.success('Saved successfully!');

// Error toast
Toast.error('Failed to save');

// Warning toast
Toast.warning('Connection lost', 3000);

// Info toast
Toast.info('Loading data...');
```

## Ejemplos de Uso en Templates

### 1. Confirmación de Acción (Alpine.js)

```html
<script>
function hubApp() {
    return {
        async registerHub() {
            try {
                const response = await fetch('/api/hubs/register/', {
                    method: 'POST',
                    body: JSON.stringify(this.formData)
                });

                if (response.ok) {
                    Toast.success('Hub registered successfully!');
                    window.location.href = '/hubs/';
                } else {
                    Toast.error('Failed to register hub');
                }
            } catch (error) {
                Toast.error('Network error occurred');
            }
        }
    }
}
</script>
```

### 2. Add to Cart (Marketplace)

```javascript
async addToCart(pluginId) {
    try {
        await fetch(`/api/plugins/${pluginId}/cart/`, { method: 'POST' });
        Toast.success('Added to cart');
        this.cartCount++;
    } catch (error) {
        Toast.error('Failed to add to cart');
    }
}
```

### 3. Save Settings

```javascript
async saveSettings() {
    try {
        const response = await fetch('/settings/save/', {
            method: 'POST',
            body: new FormData(document.getElementById('settings-form'))
        });

        if (response.ok) {
            Toast.success('Settings saved successfully');
        } else {
            Toast.warning('Some settings could not be saved');
        }
    } catch (error) {
        Toast.error('Failed to save settings');
    }
}
```

### 4. Plugin Activation/Deactivation

```javascript
async togglePlugin(pluginId, isActive) {
    const action = isActive ? 'activate' : 'deactivate';

    try {
        await fetch(`/api/plugins/${pluginId}/${action}/`, { method: 'POST' });
        Toast.success(`Plugin ${isActive ? 'activated' : 'deactivated'}`);
    } catch (error) {
        Toast.error(`Failed to ${action} plugin`);
    }
}
```

## Colores Disponibles

| Color | Uso Sugerido |
|-------|--------------|
| `success` | Operación exitosa, confirmación |
| `danger` | Error, fallo, eliminación |
| `warning` | Advertencia, precaución |
| `primary` | Información general, neutral |
| `secondary` | Información secundaria |
| `dark` | Notificación importante |
| `light` | Notificación sutil |

## Ubicaciones de Uso

### Cloud (10+ ocurrencias)
- `marketplace.html`: add to cart, remove from cart, install plugin
- `profile/index.html`: save success, save error
- `hubs/hub_list.html`: register hub success/error
- `plugins/installed.html`: activate/deactivate plugin

### Hub (8+ ocurrencias)
- `plugins.html`: install, activate, deactivate, uninstall
- `settings.html`: save preferences, save error, reset defaults

## Ventajas

✅ **Consistencia**: Todas las notificaciones usan el mismo estilo
✅ **DRY**: Evita duplicar código de toast en cada template
✅ **Mantenible**: Cambios en un solo lugar
✅ **Fácil de usar**: API simple y shortcuts
✅ **Cleanup automático**: Remueve el elemento del DOM después de cerrarse

## Ahorro de Código

**Antes** (6 líneas por cada toast):
```javascript
const toast = document.createElement('ion-toast');
toast.message = 'Success!';
toast.duration = 2000;
toast.color = 'success';
document.body.appendChild(toast);
await toast.present();
```

**Después** (1 línea):
```javascript
Toast.success('Success!');
```

**Estimado:** ~120 líneas eliminadas en 18+ ubicaciones
