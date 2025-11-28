# ERPlora Hub - Plugins

Los plugins son Django apps que extienden la funcionalidad del Hub. Se gestionan por **filesystem**, no por base de datos.

## Convención de Nombres

| Prefijo | Estado | Descripción |
|---------|--------|-------------|
| `plugin_name/` | **Activo** | Se carga automáticamente al iniciar |
| `_plugin_name/` | **Inactivo** | Visible en UI pero no se carga |
| `.plugin_name/` | **Oculto** | No se muestra en UI |

**Ejemplo:**
```
plugins/
├── inventory/        # Activo - se carga
├── _customers/       # Inactivo - visible pero no carga
├── _sales/           # Inactivo
└── .template/        # Oculto - template base
```

## Activar/Desactivar Plugins

Desde la UI (`/plugins/`):
- Click **Activate** → renombra `_plugin` a `plugin`
- Click **Deactivate** → renombra `plugin` a `_plugin`

El servidor se reinicia automáticamente para aplicar cambios.

## Estructura de un Plugin

```
plugin_name/
├── plugin.json          # Metadata (requerido)
├── __init__.py          # Django app init
├── apps.py              # AppConfig
├── models.py            # Modelos
├── views.py             # Vistas
├── urls.py              # URLs (montadas en /plugins/plugin_name/)
├── templates/
│   └── plugin_name/
│       └── index.html   # Template principal
├── static/
│   └── plugin_name/
│       ├── css/
│       └── js/
└── migrations/
    └── __init__.py
```

## plugin.json

Archivo de metadata requerido:

```json
{
  "plugin_id": "inventory",
  "name": "Inventory Manager",
  "name_es": "Gestión de Inventario",
  "version": "1.0.0",
  "description": "Product and stock management",
  "description_es": "Gestión de productos y stock",
  "author": "ERPlora Team",
  "category": "inventory",
  "icon": "cube-outline",

  "menu": {
    "label": "Inventory",
    "label_es": "Inventario",
    "icon": "cube-outline",
    "url": "/plugins/inventory/",
    "order": 10
  },

  "dependencies": {
    "python": ["Pillow>=10.0.0"],
    "plugins": []
  },

  "compatibility": {
    "min_erplora_version": "1.0.0"
  }
}
```

### Campos Importantes

| Campo | Descripción |
|-------|-------------|
| `plugin_id` | ID único, debe coincidir con nombre del directorio |
| `name` / `name_es` | Nombre del plugin (multiidioma) |
| `icon` | Icono de Ionicons (ej: `cube-outline`) |
| `menu.icon` | Icono en el menú (alternativa si no hay `icon` raíz) |
| `menu.order` | Orden en el menú (menor = primero) |

## URLs

Los plugins se montan automáticamente en `/plugins/{plugin_id}/`:

```python
# urls.py
from django.urls import path
from . import views

app_name = 'inventory'

urlpatterns = [
    path('', views.index, name='index'),
    path('products/', views.products, name='products'),
    path('categories/', views.categories, name='categories'),
]
```

## Vistas

Usa el decorador `@login_required` de accounts:

```python
from django.shortcuts import render
from apps.accounts.decorators import login_required

@login_required
def index(request):
    return render(request, 'inventory/index.html')
```

## Templates

Extiende `core/app_base.html`:

```django
{% extends "core/app_base.html" %}
{% load static %}

{% block content %}
<div class="p-4">
    <h1>Inventory</h1>
</div>
{% endblock %}
```

## Configuración Global

Accede a la configuración del Hub:

```python
from apps.configuration.models import HubConfig, StoreConfig

currency = HubConfig.get_value('currency', 'EUR')
tax_rate = StoreConfig.get_value('tax_rate', 0.00)
business_name = StoreConfig.get_value('business_name', '')
```

En templates (automático):
```django
{{ HUB_CONFIG.currency }}
{{ STORE_CONFIG.business_name }}
{{ STORE_CONFIG.tax_rate }}
```

## Almacenamiento de Datos

Los plugins tienen acceso a dos directorios para almacenar datos, ambos definidos en settings:

### PLUGIN_DATA_ROOT (Datos internos del plugin)

Directorio para datos internos del plugin (configuraciones, cache, archivos temporales):

```python
from django.conf import settings

# Crear subdirectorio para tu plugin
plugin_data_dir = settings.PLUGIN_DATA_ROOT / 'mi_plugin'
plugin_data_dir.mkdir(parents=True, exist_ok=True)

# Guardar archivo de configuración
config_file = plugin_data_dir / 'config.json'
config_file.write_text('{"setting": "value"}')
```

**Ubicación por entorno:**
- **Web/Docker**: `{DATA_DIR}/plugin_data/`
- **Linux**: `~/.erplora-hub/plugin_data/`
- **macOS**: `~/Library/Application Support/ERPloraHub/plugin_data/`
- **Windows**: `%LOCALAPPDATA%\ERPloraHub\plugin_data\`

### PLUGIN_MEDIA_ROOT (Archivos media públicos)

Directorio para archivos media accesibles via HTTP (imágenes, documentos):

```python
from django.conf import settings

# Crear subdirectorio para tu plugin
plugin_media_dir = settings.PLUGIN_MEDIA_ROOT / 'mi_plugin'
plugin_media_dir.mkdir(parents=True, exist_ok=True)

# Guardar imagen subida
image_path = plugin_media_dir / 'logo.png'
```

**URL pública**: `/media/plugins/mi_plugin/logo.png`

### Ejemplo de uso en modelo

```python
from django.db import models
from django.conf import settings

class ProductImage(models.Model):
    product = models.ForeignKey('Product', on_delete=models.CASCADE)
    image = models.ImageField(upload_to='plugins/products/images/')

    # Las imágenes se guardan en MEDIA_ROOT/plugins/products/images/
```

### Importante

- **NO crear carpetas dentro de PLUGINS_DIR** - serían detectadas como plugins
- Usar siempre `settings.PLUGIN_DATA_ROOT` o `settings.PLUGIN_MEDIA_ROOT`
- Crear subdirectorios con el nombre del plugin para evitar colisiones

## Dependencias Python Permitidas

- **Imágenes**: `Pillow`
- **Excel**: `openpyxl`
- **PDF**: `reportlab`, `PyPDF2`
- **Códigos**: `qrcode`, `python-barcode`
- **HTTP**: `requests`
- **Fechas**: `python-dateutil`, `pytz`

Ver lista completa en `config/plugin_allowed_deps.py`.

## Desarrollo

```bash
cd hub

# Crear plugin desde template
cp -r plugins/.template plugins/mi_plugin

# Editar plugin.json
nano plugins/mi_plugin/plugin.json

# Crear migraciones
python manage.py makemigrations mi_plugin
python manage.py migrate mi_plugin

# Probar
python manage.py runserver 8001
# http://localhost:8001/plugins/mi_plugin/
```

## Flujo de Carga

1. Django inicia
2. `local.py` escanea `plugins/` buscando directorios sin prefijo `_`
3. Añade plugins activos a `INSTALLED_APPS`
4. `plugins_runtime.py` registra URLs en `/plugins/{id}/`
5. Plugin disponible

---

**Última actualización:** 2025-11-28
