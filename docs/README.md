# ERPlora Hub - Sistema POS

ERPlora Hub es el sistema Point of Sale (POS) de ERPlora, desplegado como aplicación web.

---

## 🎯 Descripción

ERPlora Hub es una aplicación Django que funciona como punto de venta (POS). Se despliega como contenedor Docker via Dokploy.

- Contenedor Docker desplegado via Dokploy
- Acceso via navegador web
- URL unica: `{subdomain}.erplora.com` (ej: `mi-tienda.erplora.com`)

**Características:**
- 💾 Base de datos SQLite (funciona offline)
- 🔌 Sistema de modules extensible
- 🖨️ Impresión 100% web (window.print)
- 🔄 Sincronización opcional con Cloud vía HTTP API
- 📦 Marketplace único de modules

**Stack tecnológico:**
- Django 5.1
- SQLite
- Alpine.js + HTMX para UI
- Python 3.11+

---

## 📁 Estructura del Proyecto

```
hub/
├── apps/                      # Django apps (5 apps core)
│   ├── accounts/             # Autenticación local (LocalUser, PIN)
│   ├── configuration/        # Configuración global (HubConfig, StoreConfig)
│   ├── core/                 # Utilidades core (sin modelos)
│   ├── modules_runtime/      # Sistema de modules, loader dinámico
│   └── sync/                 # Sincronización con Cloud
│
├── config/                    # Configuración Django
│   ├── settings.py           # Settings (SQLite)
│   ├── urls.py
│   └── module_allowed_deps.py # Whitelist de librerías de modules
│
├── modules/                   # Modules instalados (dinámico)
│   ├── .template/            # Template para nuevos modules
│   └── ...                   # Modules activos/inactivos
│
├── templates/                 # Templates UX v3 + HTMX
├── static/                    # Archivos estáticos
├── locale/                    # Traducciones i18n
│
├── Dockerfile                # Para despliegue Cloud
├── manage.py                 # Django management
├── pyproject.toml            # Dependencias Python (uv)
└── pytest.ini                # Configuración pytest
```

---

## 🚀 Setup Local (Desarrollo)

### Requisitos

- Python 3.11+
- uv (package manager)

### Instalación

```bash
cd hub

# Crear virtual environment
uv venv
source .venv/bin/activate

# Instalar dependencias
uv pip install -e ".[dev]"

# Configurar base de datos
python manage.py migrate

# Ejecutar servidor de desarrollo
python manage.py runserver
```

Acceder a: http://127.0.0.1:8000

---

## 🔧 Configuración Inicial

Cuando el Hub se ejecuta por primera vez:

1. **Wizard de configuración** se muestra automáticamente
2. Usuario **owner** ingresa credenciales de Cloud (email/password)
3. Hub se auto-registra en Cloud vía HTTP API
4. Cloud asigna: `hub_id`, `cloud_api_token`
5. Hub guarda credenciales en `HubConfig` (SQLite)
6. Owner configura datos de la tienda en `StoreConfig`

Después de configurado, el Hub funciona **100% offline** para operaciones normales.

---

## 📡 Comunicación con Cloud

El Hub usa **HTTP REST API** para comunicación con Cloud:

| Endpoint | Uso |
|----------|-----|
| `POST /api/auth/login/` | Login de usuarios |
| `POST /api/hubs/register/` | Auto-registro del Hub |
| `POST /api/hubs/{id}/users/register/` | Registrar usuario en Hub |
| `GET /api/hubs/{id}/users/check/{email}/` | Verificar acceso de usuario |

**Sincronización:** Sistema "sync-on-access" - verifica usuarios on-demand, no proactivamente.


Ver documentación completa: [CLOUD.md](CLOUD.md)

---

## 🔌 Sistema de Modules

Los modules son Django apps que se cargan dinámicamente. El Hub incluye **25 librerías Python pre-empaquetadas**.

### Configuración de Módulos

Cada módulo define su configuración en `module.py`:

```python
from django.utils.translation import gettext_lazy as _

MODULE_ID = "inventory"
MODULE_NAME = _("Inventory")
MODULE_ICON = "icon.svg"  # SVG/PNG in static/icons/ (fallback: default icon)
MODULE_VERSION = "1.0.0"
MODULE_CATEGORY = "inventory"

MENU = {
    "label": _("Inventory"),
    "icon": "icon.svg",  # Same as MODULE_ICON
    "order": 10,
    "show": True,
}

NAVIGATION = [
    {"id": "dashboard", "label": _("Overview"), "icon": "grid-outline", "view": ""},
    {"id": "products", "label": _("Products"), "icon": "cube-outline", "view": "products"},
]

DEPENDENCIES = []
SETTINGS = {}
PERMISSIONS = ["inventory.view_product", "inventory.add_product"]
```

Ver documentación completa: [MODULE_ICONS.md](MODULE_ICONS.md)

### Iconos de Módulos

Los módulos pueden usar iconos SVG personalizados. Fuente recomendada: [React Icons](https://react-icons.github.io/react-icons/)

- **Prioridad**: SVG local > PNG local > Default icon (MODULE_ICON) > Fallback
- **Ubicación**: `{module}/static/icons/icon.svg`

Ver documentación: [MODULE_ICONS.md](MODULE_ICONS.md)

### Activación por Filesystem

| Prefijo | Estado | Descripción |
|---------|--------|-------------|
| `module_name/` | **Activo** | Se carga automáticamente |
| `_module_name/` | **Inactivo** | Visible pero no se carga |
| `.module_name/` | **Oculto** | No se muestra en UI |

### Librerías Pre-empaquetadas (25)

**Imágenes & Media:** Pillow, qrcode, python-barcode

**Office & Reportes:** openpyxl, reportlab, PyPDF2

**Facturación Electrónica:** lxml, xmltodict, signxml, cryptography, zeep

**Hardware:** python-escpos, pyserial

**Network:** requests, websockets

**Pagos:** stripe

**Data & Analysis:** pandas, numpy

**Utils:** python-dateutil, pytz, phonenumbers, email-validator, python-slugify, pydantic, beautifulsoup4

---

## ⚙️ Configuración Global

Sistema Singleton + Cache para configuración:

### HubConfig
Configuración del Hub: `hub_id`, `cloud_api_token`, `currency`, `dark_mode`, etc.

### StoreConfig
Configuración de tienda: `business_name`, `tax_rate`, `receipt_header`, etc.

```python
# En views
from apps.configuration.models import HubConfig, StoreConfig

currency = HubConfig.get_value('currency', 'EUR')
tax_rate = StoreConfig.get_value('tax_rate', 0.00)
```

```django
<!-- En templates (automático) -->
{{ HUB_CONFIG.currency }}
{{ STORE_CONFIG.business_name }}
```

Ver documentación completa: [GLOBAL_CONFIGURATION.md](GLOBAL_CONFIGURATION.md)

---

## 🧪 Testing

```bash
# Todos los tests
pytest

# Tests por marker
pytest -m unit
pytest -m integration

# Coverage
pytest --cov=apps --cov-report=html
```

Ver documentación completa: [TESTING.md](TESTING.md)

---

## 📦 Despliegue

### Cloud (Docker)

```bash
# Build de imagen
docker build -t erplora/hub:latest .

# El despliegue se hace via Dokploy
# Cada Hub es un contenedor independiente con SQLite
```

---

## 🖨️ Sistema de Impresión

Impresión **100% web** usando `window.print()`:

- Modal Print Preview antes de imprimir
- Compatible con cualquier impresora del sistema
- Estilos CSS para tickets (80mm) y facturas (A4)

Ver documentación completa: [PRINTING_SYSTEM.md](PRINTING_SYSTEM.md)

---

## 🔒 Seguridad

- **Credenciales del Hub**: `cloud_api_token` guardado en SQLite
- **Base de datos local**: SQLite con permisos restrictivos
- **Modo offline**: Funciona sin conexión después de setup
- **Tokens JWT**: Temporales, NO se guardan permanentemente
- **Modules**: Solo librerías whitelisted permitidas

---

## 📚 Documentación

| Documento | Descripción |
|-----------|-------------|
| [CLOUD.md](CLOUD.md) | Comunicación Hub ↔ Cloud |
| [GLOBAL_CONFIGURATION.md](GLOBAL_CONFIGURATION.md) | Sistema de configuración |
| [ROLES_AND_PERMISSIONS.md](ROLES_AND_PERMISSIONS.md) | Sistema de roles y permisos |
| [MODULE_ICONS.md](MODULE_ICONS.md) | Sistema de iconos SVG |
| [MODULE_ACTIVATION_FLOW.md](MODULE_ACTIVATION_FLOW.md) | Flujo de activación |
| [MODULE_RUNTIME_ANALYSIS.md](MODULE_RUNTIME_ANALYSIS.md) | Análisis del runtime |
| [MODULE_SUBSCRIPTION_USAGE.md](MODULE_SUBSCRIPTION_USAGE.md) | Sistema de suscripciones |
| [PRINTING_SYSTEM.md](PRINTING_SYSTEM.md) | Sistema de impresión |
| [TESTING.md](TESTING.md) | Guía de testing |
| [TRANSLATIONS.md](TRANSLATIONS.md) | Sistema i18n |
| [CHANGELOG.md](CHANGELOG.md) | Historial de cambios |

---

## 📄 Licencia

ERPlora Hub está licenciado bajo **Business Source License 1.1 (BUSL-1.1)**.

### ✅ Usos Permitidos (GRATIS)
- Uso interno en negocios
- Uso personal y educativo
- Crear modules para el ecosistema
- Servicios de consultoría

### ❌ Usos Prohibidos
- Ofrecer como SaaS/PaaS
- Crear plataforma POS competidora
- Revender o sublicenciar

### 🔄 Conversión a Open Source
Después del **2036-01-02**, se convierte en **Apache License 2.0**.

---

**Última actualización**: 2026-01-02
**Django**: 5.1
**Python**: 3.11+
