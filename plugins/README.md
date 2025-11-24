# CPOS Hub - Plugin Development Guide

Este directorio es para **desarrollo de plugins**. Cada plugin es un Django app independiente con su propio repositorio git.

## 📋 Tabla de Contenidos

- [Arquitectura de Plugins](#arquitectura-de-plugins)
- [Estructura de un Plugin](#estructura-de-un-plugin)
- [Dashboard y Navegación](#dashboard-y-navegación)
- [Configuración Global vs Local](#configuración-global-vs-local)
- [Desarrollo Local](#desarrollo-local)
- [Management Commands](#management-commands)
- [Dependencias Permitidas](#dependencias-permitidas)
- [Persistencia de Datos](#persistencia-de-datos)
- [Firma Digital y Distribución](#firma-digital-y-distribución)
- [Buenas Prácticas](#buenas-prácticas)

---

## Arquitectura de Plugins

### Concepto General

Todos los plugins siguen una arquitectura estándar:

1. **Dashboard** (`index.html`) - Página principal con estadísticas y navegación interna
2. **Secciones internas** - Funcionalidad específica del plugin
3. **Configuración local** (opcional) - Solo si el plugin necesita settings específicos
4. **Herencia de configuración global** - Uso automático de HubConfig y StoreConfig

### Dos Modos de Operación

#### 🔧 Modo Desarrollo (`CPOS_DEV_MODE=true`)
- Plugins se cargan desde **dos ubicaciones**:
  1. `./plugins/` - Repositorios locales (desarrollo)
  2. `~/.cpos-hub/plugins/` - Plugins instalados
- Sin firma digital requerida
- Hot reload automático (detecta cambios)
- Validación relajada

#### 🚀 Modo Producción (PyInstaller Build)
- Plugins se cargan solo desde `~/.cpos-hub/plugins/`
- Firma digital **obligatoria** (RSA-SHA256)
- Sin hot reload
- Validación estricta

---

## Estructura de un Plugin

### Esquema Visual

```
plugin_name/
│
├── 📄 plugin.json                    # ⚠️ REQUERIDO - Metadata del plugin
├── 📄 __init__.py                    # ⚠️ REQUERIDO
├── 📄 apps.py                        # ⚠️ REQUERIDO - Django app config
├── 📄 models.py                      # Modelos de datos del plugin
├── 📄 views.py                       # Vistas del plugin
├── 📄 urls.py                        # ⚠️ REQUERIDO - Rutas del plugin
├── 📄 admin.py                       # Django admin (opcional)
├── 📄 forms.py                       # Formularios (opcional)
├── 📄 utils.py                       # Utilidades (opcional)
├── 📄 context_processors.py          # Context processors (opcional)
│
├── 📁 templates/
│   └── plugin_name/                  # ⚠️ Debe coincidir con plugin_id
│       ├── index.html                # ⚠️ REQUERIDO - Dashboard principal
│       ├── section1.html             # Secciones internas
│       ├── section2.html
│       ├── settings.html             # OPCIONAL - Solo si necesario
│       └── partials/                 # Partials para HTMX (opcional)
│           ├── table_partial.html
│           └── form_partial.html
│
├── 📁 static/
│   └── plugin_name/                  # ⚠️ Debe coincidir con plugin_id
│       ├── css/
│       │   └── styles.css
│       ├── js/
│       │   └── app.js
│       └── img/
│           └── icon.png
│
├── 📁 migrations/
│   └── __init__.py
│
├── 📁 management/
│   └── commands/
│       └── __init__.py
│
├── 📁 tests/
│   ├── __init__.py
│   ├── test_models.py
│   └── test_views.py
│
├── 📁 locale/                        # i18n (opcional)
│   └── es/
│       └── LC_MESSAGES/
│           ├── django.po
│           └── django.mo
│
└── 📄 README.md                      # Documentación del plugin
```

### Archivos Requeridos

#### 1. plugin.json

```json
{
  "plugin_id": "plugin_name",
  "name": "Plugin Name",
  "name_es": "Nombre del Plugin",
  "version": "1.0.0",
  "category": "inventory",
  "description": "Plugin description",
  "description_es": "Descripción del plugin",
  "author": "Your Name",
  "author_email": "email@example.com",
  "license": "MIT",
  "homepage": "https://github.com/user/plugin",

  "compatibility": {
    "min_cpos_version": "1.0.0",
    "max_cpos_version": "2.0.0",
    "django_version": "5.1.x"
  },

  "dependencies": {
    "python": [
      "Pillow>=10.0.0",
      "openpyxl>=3.1.0"
    ],
    "plugins": []
  },

  "menu": {
    "label": "Plugin Name",
    "label_es": "Nombre del Plugin",
    "icon": "cube-outline",
    "url": "/plugins/plugin_name/",
    "order": 10
  }
}
```

#### 2. urls.py

```python
from django.urls import path
from . import views

app_name = 'plugin_name'

urlpatterns = [
    # Dashboard (entrada principal)
    path('', views.dashboard, name='dashboard'),

    # Secciones internas
    path('section1/', views.section1_view, name='section1'),
    path('section1/create/', views.section1_create, name='section1_create'),
    path('section1/<int:pk>/edit/', views.section1_edit, name='section1_edit'),

    path('section2/', views.section2_view, name='section2'),

    path('reports/', views.reports_view, name='reports'),

    # Settings: OPCIONAL (solo si el plugin tiene configuración específica)
    path('settings/', views.settings_view, name='settings'),
]
```

---

## Dashboard y Navegación

### Dashboard Principal (index.html)

El dashboard es la **página de entrada** del plugin y debe contener:

1. **Estadísticas / KPIs** - Cards con métricas principales
2. **Navegación interna** - Botones/enlaces a secciones del plugin
3. **Resumen visual** - Vista general del estado actual

**Ejemplo de estructura:**

```django
{% extends "core/app_base.html" %}
{% load static %}

{% block content %}
<div class="p-4">
    <!-- 1. Page Header -->
    <div class="mb-6">
        <h1 class="text-3xl font-bold">Dashboard del Plugin</h1>
        <p class="text-sm mt-2">Descripción general</p>
    </div>

    <!-- 2. Stats Cards (KPIs) -->
    <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        <ion-card class="m-0">
            <ion-card-content class="p-6">
                <div class="flex items-center gap-4">
                    <div class="w-12 h-12 bg-primary/10 rounded-xl flex items-center justify-center">
                        <ion-icon name="cube-outline" class="text-2xl text-primary"></ion-icon>
                    </div>
                    <div>
                        <div class="text-sm text-medium">Total Items</div>
                        <div class="text-2xl font-semibold">{{ total_items }}</div>
                    </div>
                </div>
            </ion-card-content>
        </ion-card>

        <!-- Más stats cards... -->
    </div>

    <!-- 3. Navegación Interna (Acciones Rápidas) -->
    <div class="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-6">
        <ion-card class="m-0">
            <ion-card-header>
                <ion-card-title>Acciones Rápidas</ion-card-title>
            </ion-card-header>
            <ion-card-content>
                <div class="grid grid-cols-1 gap-3">
                    <ion-button expand="block" href="/plugins/plugin_name/section1/">
                        <ion-icon slot="start" name="list-outline"></ion-icon>
                        Ver Sección 1
                    </ion-button>
                    <ion-button expand="block" href="/plugins/plugin_name/section2/" fill="outline">
                        <ion-icon slot="start" name="albums-outline"></ion-icon>
                        Gestionar Sección 2
                    </ion-button>
                    <ion-button expand="block" href="/plugins/plugin_name/reports/" fill="outline">
                        <ion-icon slot="start" name="stats-chart-outline"></ion-icon>
                        Informes
                    </ion-button>
                    <!-- Settings: OPCIONAL -->
                    <ion-button expand="block" href="/plugins/plugin_name/settings/" fill="outline">
                        <ion-icon slot="start" name="settings-outline"></ion-icon>
                        Configuración
                    </ion-button>
                </div>
            </ion-card-content>
        </ion-card>

        <!-- 4. Resumen/Preview -->
        <ion-card class="m-0">
            <ion-card-header>
                <ion-card-title>Últimos Elementos</ion-card-title>
            </ion-card-header>
            <ion-card-content>
                <!-- Lista o tabla con últimos items -->
            </ion-card-content>
        </ion-card>
    </div>
</div>
{% endblock %}
```

### Vista del Dashboard (views.py)

```python
from django.shortcuts import render
from apps.accounts.decorators import login_required
from apps.configuration.models import HubConfig, StoreConfig

@login_required
def dashboard(request):
    """Dashboard principal del plugin con estadísticas y navegación"""

    # Obtener configuración global del Hub
    currency = HubConfig.get_value('currency', 'EUR')
    language = HubConfig.get_value('os_language', 'en')

    # Calcular estadísticas
    total_items = Item.objects.filter(is_active=True).count()
    active_items = Item.objects.filter(is_active=True, status='active').count()

    context = {
        'total_items': total_items,
        'active_items': active_items,
        'currency': currency,  # Opcional, ya disponible en templates
    }

    return render(request, 'plugin_name/index.html', context)
```

---

## Configuración Global vs Local

### Configuración Global del Hub (SIEMPRE usar)

**Todos los plugins** deben usar la configuración global del Hub en lugar de duplicarla.

#### En Python (views.py, models.py):

```python
from apps.configuration.models import HubConfig, StoreConfig

def any_view(request):
    # Obtener valores globales
    currency = HubConfig.get_value('currency', 'EUR')
    language = HubConfig.get_value('os_language', 'en')
    dark_mode = HubConfig.get_value('dark_mode', False)

    tax_rate = StoreConfig.get_value('tax_rate', 0.00)
    tax_included = StoreConfig.get_value('tax_included', True)
    business_name = StoreConfig.get_value('business_name', '')

    # Usar en cálculos
    if not tax_included:
        price_with_tax = product.price * (1 + tax_rate/100)
    else:
        price_with_tax = product.price
```

#### En Templates (automático via context processor):

```django
<!-- Acceso directo a configuración global -->
<p>Currency: {{ HUB_CONFIG.currency }}</p>
<p>Language: {{ HUB_CONFIG.os_language }}</p>
<p>Dark Mode: {{ HUB_CONFIG.dark_mode }}</p>

<p>Business: {{ STORE_CONFIG.business_name }}</p>
<p>Tax Rate: {{ STORE_CONFIG.tax_rate }}%</p>
<p>Tax Included: {{ STORE_CONFIG.tax_included }}</p>

<!-- Usar en Alpine.js -->
<script>
function productData() {
    return {
        currency: '{{ HUB_CONFIG.currency }}',
        taxRate: {{ STORE_CONFIG.tax_rate }},
        price: 100,

        get formattedPrice() {
            const symbols = {EUR: '€', USD: '$', GBP: '£'};
            const symbol = symbols[this.currency] || this.currency;
            return `${symbol}${this.price.toFixed(2)}`;
        }
    }
}
</script>
```

#### Configuraciones Globales Disponibles:

**HubConfig:**
- `currency` → 'EUR', 'USD', 'GBP', 'JPY', 'MXN', etc.
- `os_language` → 'en', 'es'
- `color_theme` → 'default', 'blue'
- `dark_mode` → True/False
- `auto_print` → True/False
- `hub_id` → UUID del Hub
- `cloud_api_token` → Token API Cloud

**StoreConfig:**
- `business_name` → Nombre del negocio
- `business_address` → Dirección
- `vat_number` → NIF/CIF/VAT ID
- `phone`, `email`, `website`
- `tax_rate` → Tasa de impuesto en % (ej: 21.00)
- `tax_included` → Si los precios incluyen impuestos
- `receipt_header`, `receipt_footer`

### Configuración Local del Plugin (OPCIONAL)

**Solo crear si el plugin necesita settings específicos** que no existen en HubConfig/StoreConfig.

#### Modelo de Configuración (models.py):

```python
from django.db import models

class PluginNameConfig(models.Model):
    """
    Configuración específica del plugin.
    Singleton pattern (solo una instancia con id=1).
    """
    # Configuración específica del plugin
    allow_some_feature = models.BooleanField(
        default=False,
        help_text='Enable/disable specific feature'
    )

    auto_generate_codes = models.BooleanField(
        default=True,
        help_text='Auto-generate codes for items'
    )

    alert_enabled = models.BooleanField(
        default=True,
        help_text='Show alerts for important events'
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = 'plugin_name'
        db_table = 'plugin_name_config'
        verbose_name = 'Plugin Configuration'

    def __str__(self):
        return "Plugin Configuration"

    @classmethod
    def get_config(cls):
        """Get or create config (singleton)"""
        config, _ = cls.objects.get_or_create(id=1)
        return config
```

#### Vista de Settings (views.py):

```python
import json
from django.shortcuts import render
from django.http import JsonResponse
from apps.accounts.decorators import login_required
from .models import PluginNameConfig

@login_required
def settings_view(request):
    """Vista de configuración del plugin"""
    config = PluginNameConfig.get_config()

    if request.method == "POST":
        try:
            # Parse JSON body
            data = json.loads(request.body)

            # Update config
            config.allow_some_feature = data.get('allow_some_feature', False)
            config.alert_enabled = data.get('alert_enabled', True)
            config.auto_generate_codes = data.get('auto_generate_codes', True)
            config.save()

            return JsonResponse({"success": True, "message": "Configuración guardada"})
        except Exception as e:
            return JsonResponse({"success": False, "error": str(e)}, status=400)

    # GET: mostrar formulario
    context = {
        'config': config,
        # HUB_CONFIG y STORE_CONFIG disponibles automáticamente
    }
    return render(request, 'plugin_name/settings.html', context)
```

#### Template de Settings (settings.html):

```django
{% extends "core/app_base.html" %}

{% block content %}
{% csrf_token %}
<div x-data="settingsApp()" x-init="init()" class="p-4">
    <ion-card class="m-4">
        <ion-card-header class="p-0">
            <ion-toolbar>
                <ion-buttons slot="start">
                    <ion-button href="/plugins/plugin_name/" fill="clear">
                        <ion-icon slot="icon-only" name="arrow-back-outline"></ion-icon>
                    </ion-button>
                </ion-buttons>
                <ion-title>Configuración del Plugin</ion-title>
            </ion-toolbar>
        </ion-card-header>

        <ion-card-content>
            <!-- Configuración específica del plugin -->
            <div class="mb-6">
                <div class="flex items-center justify-between">
                    <div class="flex-1">
                        <h3 class="font-semibold mb-1">Habilitar Feature</h3>
                        <p class="text-sm" style="color: var(--ion-color-medium);">
                            Descripción de la funcionalidad
                        </p>
                    </div>
                    <ion-toggle
                        x-ref="toggle_feature"
                        :checked="settings.allow_some_feature"
                        color="primary">
                    </ion-toggle>
                </div>
            </div>

            <div style="height: 1px; background: var(--ion-border-color); margin: 1.5rem 0;"></div>

            <!-- Info sobre configuración global (read-only) -->
            <div class="mt-6 p-4 rounded-lg" style="background: var(--ion-color-step-50);">
                <div class="flex items-start gap-2">
                    <ion-icon name="information-circle-outline" style="font-size: 20px;"></ion-icon>
                    <div>
                        <h4 class="font-semibold mb-2">Configuración Global del Hub</h4>
                        <p class="text-sm">Moneda: {{ HUB_CONFIG.currency }}</p>
                        <p class="text-sm">Impuestos: {{ STORE_CONFIG.tax_rate }}%</p>
                        <p class="text-sm mt-2" style="color: var(--ion-color-medium);">
                            Esta configuración se gestiona en Settings del Hub
                        </p>
                    </div>
                </div>
            </div>
        </ion-card-content>
    </ion-card>
</div>

<script>
function settingsApp() {
    return {
        settings: {
            allow_some_feature: {{ config.allow_some_feature|lower }},
            alert_enabled: {{ config.alert_enabled|lower }},
            auto_generate_codes: {{ config.auto_generate_codes|lower }}
        },

        init() {
            this.$nextTick(() => {
                const toggle = this.$refs.toggle_feature;
                if (toggle) {
                    toggle.addEventListener('ionChange', (e) => {
                        this.updateSetting('allow_some_feature', e.detail.checked);
                    });
                }
            });
        },

        async updateSetting(key, value) {
            this.settings[key] = value;

            try {
                const response = await fetch('{% url "plugin_name:settings" %}', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]').value
                    },
                    body: JSON.stringify(this.settings)
                });

                if (response.ok) {
                    this.showToast('Configuración guardada', 'success');
                } else {
                    throw new Error('Error al guardar');
                }
            } catch (error) {
                this.showToast('Error al guardar la configuración', 'danger');
                this.settings[key] = !value;  // Revert
            }
        },

        async showToast(message, color = 'primary') {
            const toast = document.createElement('ion-toast');
            toast.message = message;
            toast.duration = 2000;
            toast.color = color;
            toast.position = 'top';
            document.body.appendChild(toast);
            await toast.present();
        }
    }
}
</script>
{% endblock %}
```

### ¿Cuándo Crear Settings Page?

| Caso | Crear Settings? |
|------|----------------|
| Plugin solo lee/muestra datos | ❌ NO |
| Plugin tiene funcionalidad fija sin config | ❌ NO |
| Plugin usa solo config global (currency, tax) | ❌ NO |
| Plugin necesita activar/desactivar features | ✅ SÍ |
| Plugin tiene parámetros personalizables | ✅ SÍ |
| Plugin necesita config adicional específica | ✅ SÍ |

**Ejemplos:**
- **Inventory**: ✅ Settings (allow_negative_stock, barcode_enabled)
- **Reports**: ❌ NO settings (solo muestra datos)
- **POS**: ✅ Settings (auto_print, default_payment_method)
- **Customers**: ❌ NO settings (solo CRUD)

---

## Desarrollo Local

### 1. Crear un Nuevo Plugin

```bash
# Ubicarte en la carpeta hub
cd hub

# Activar entorno virtual
source .venv/bin/activate

# Crear plugin desde template
python manage.py create_plugin my_plugin --name "My Plugin" --author "Your Name"
```

### 2. Inicializar Git para el Plugin

```bash
cd plugins/my_plugin
git init
git add .
git commit -m "Initial commit"

# Opcional: crear repositorio remoto
git remote add origin https://github.com/user/cpos-plugin-my-plugin.git
git push -u origin main
```

### 3. Desarrollar el Plugin

```bash
# Editar modelos, vistas, templates
nano models.py
nano views.py
nano templates/my_plugin/index.html

# Crear migraciones
python manage.py makemigrations my_plugin

# Aplicar migraciones
python manage.py migrate my_plugin

# Ejecutar tests
pytest plugins/my_plugin/tests/
```

### 4. Probar en el Hub

```bash
# Iniciar Hub en desarrollo
python manage.py runserver 8001

# Acceder al plugin
# http://localhost:8001/plugins/my_plugin/
```

---

## Management Commands

### create_plugin - Crear Plugin

```bash
python manage.py create_plugin <plugin_id> [options]

# Opciones:
#   --name "Plugin Name"      # Nombre descriptivo
#   --author "Author Name"    # Nombre del autor
#   --description "Desc"      # Descripción corta

# Ejemplos:
python manage.py create_plugin inventory --name "Inventory Manager"
python manage.py create_plugin pos --name "Point of Sale" --author "Your Name"
```

### validate_plugin - Validar Plugin

```bash
python manage.py validate_plugin <plugin_id> [options]

# Opciones:
#   --strict    # Modo estricto (falla en warnings)

# Ejemplos:
python manage.py validate_plugin inventory
python manage.py validate_plugin inventory --strict
```

### sign_plugin - Firmar Plugin

```bash
python manage.py sign_plugin <plugin_id> [options]

# Opciones:
#   --key-file path/to/key.pem    # Clave privada RSA
#   --force                        # Re-firmar aunque ya tenga firma

# Ejemplos:
python manage.py sign_plugin inventory
python manage.py sign_plugin inventory --force
```

### package_plugin - Empaquetar Plugin

```bash
python manage.py package_plugin <plugin_id> [options]

# Opciones:
#   --output-dir path/      # Directorio de salida
#   --skip-validation       # Omitir validación

# Ejemplos:
python manage.py package_plugin inventory
python manage.py package_plugin inventory --output-dir ~/Desktop/
```

---

## Dependencias Permitidas

Los plugins pueden usar **25 librerías Python pre-empaquetadas**:

### Críticas (13)
- `Pillow>=10.0.0` - Imágenes
- `qrcode>=7.4.0` - QR codes
- `python-barcode>=0.15.0` - Códigos de barras
- `openpyxl>=3.1.0` - Excel
- `reportlab>=4.0.0` - PDFs
- `python-escpos>=3.0` - Impresoras térmicas
- `lxml>=5.0.0` - XML
- `xmltodict>=0.13.0` - XML parsing
- `signxml>=3.2.0` - Firmas digitales XML
- `cryptography>=42.0.0` - Cifrado
- `zeep>=4.2.0` - SOAP
- `requests>=2.31.0` - HTTP requests
- `websockets>=12.0` - WebSocket

### Importantes (10)
- `python-dateutil>=2.8.2`, `pytz>=2024.1`, `phonenumbers>=8.13.0`
- `stripe>=7.0.0` - Pagos
- `pandas>=2.1.0`, `numpy>=1.26.0` - Análisis
- `pyserial>=3.5` - Hardware
- `email-validator>=2.1.0`, `python-slugify>=8.0.0`, `pydantic>=2.5.0`

### Útiles (2)
- `beautifulsoup4>=4.12.0` - HTML parsing
- `PyPDF2>=3.0.0` - PDF manipulación

**Ver lista completa:** `hub/config/plugin_allowed_deps.py`

---

## Persistencia de Datos

### ⚠️ REGLA IMPORTANTE

**NO guardar datos dentro del directorio del plugin**. Los plugins se actualizan reemplazando el directorio completo.

### ✅ Ubicaciones Correctas

```python
from django.conf import settings
from pathlib import Path

# 1. Base de datos SQLite (mejor opción)
class Item(models.Model):
    name = models.CharField(max_length=255)
    # Los datos se guardan en ~/.cpos-hub/db/db.sqlite3

# 2. Archivos de datos (config, cache, exports)
data_dir = Path(settings.PLUGIN_DATA_ROOT) / 'my_plugin'
data_dir.mkdir(parents=True, exist_ok=True)

config_file = data_dir / 'config.json'
config_file.write_text(json.dumps({'setting': 'value'}))

# 3. Media files (imágenes, uploads)
class Item(models.Model):
    image = models.ImageField(upload_to='plugins/my_plugin/images/')
    # Se guarda en ~/.cpos-hub/media/plugins/my_plugin/images/
```

### Ubicaciones por Plataforma

| Plataforma | Base Dir |
|------------|----------|
| Windows | `C:\Users\<user>\AppData\Local\CPOSHub\` |
| macOS | `~/Library/Application Support/CPOSHub/` |
| Linux | `~/.cpos-hub/` |

---

## Firma Digital y Distribución

### 1. Desarrollo Local (Sin Firma)

```bash
python manage.py create_plugin my_plugin
python manage.py validate_plugin my_plugin
python manage.py runserver 8001
```

### 2. Preparar para Distribución

```bash
python manage.py validate_plugin my_plugin --strict
python manage.py sign_plugin my_plugin
python manage.py package_plugin my_plugin
```

### 3. Distribución

- **Cloud**: Subir a marketplace de ERPlora
- **GitHub Release**: Publicar como release
- **Directo**: Compartir ZIP

---

## Buenas Prácticas

### 1. Nombres de Tabla

```python
# ✅ BIEN - Con prefijo del plugin
class Item(models.Model):
    class Meta:
        db_table = 'my_plugin_item'

# ❌ MAL - Sin prefijo
class Item(models.Model):
    class Meta:
        db_table = 'item'  # Conflicto
```

### 2. Configuración Global

```python
# ✅ BIEN - Usar config global
currency = HubConfig.get_value('currency', 'EUR')

# ❌ MAL - Duplicar config global
class MyPluginConfig(models.Model):
    currency = models.CharField(...)  # NO!
```

### 3. Dashboard

```django
<!-- ✅ BIEN - Dashboard con navegación interna -->
<ion-card>
    <ion-card-header>Acciones Rápidas</ion-card-header>
    <ion-card-content>
        <ion-button href="/plugins/my_plugin/items/">Items</ion-button>
        <ion-button href="/plugins/my_plugin/reports/">Reports</ion-button>
        <ion-button href="/plugins/my_plugin/settings/">Settings</ion-button>
    </ion-card-content>
</ion-card>
```

### 4. Settings Page

```python
# ✅ Solo crear si el plugin necesita config específica
# ❌ NO crear si solo usa config global
```

---

## Recursos Adicionales

- **Documentación Django**: https://docs.djangoproject.com/
- **Ionic Framework**: https://ionicframework.com/docs/components
- **Alpine.js**: https://alpinejs.dev/
- **HTMX**: https://htmx.org/docs/

---

**Última actualización:** 2025-01-23
