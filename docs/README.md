# ERPlora Hub - Sistema POS

ERPlora Hub es el sistema Point of Sale (POS) de ERPlora, disponible en dos modalidades de despliegue.

---

## 🎯 Descripción

ERPlora Hub es una aplicación Django que funciona como punto de venta (POS). Puede desplegarse de dos formas:

### Opción 1: Cloud Hub (PAGO)
- Contenedor Docker desplegado en Cloud
- SQLite en volumen Docker persistente
- Acceso vía navegador web
- URL única: `erplora.com/hubs/{hub-id}`
- Suscripción mensual

### Opción 2: Desktop Hub (GRATUITO)
- App descargable empaquetada con PyInstaller
- SQLite en PC del usuario (permanente)
- WebView (pywebview) en modo kiosk
- Funciona 100% offline después de setup inicial

**Características comunes:**
- 💾 Base de datos local SQLite (funciona offline)
- 🔌 Sistema de plugins extensible
- 🖨️ Impresión 100% web (window.print)
- 🔄 Sincronización opcional con Cloud vía HTTP API
- 📦 Marketplace único de plugins

**Stack tecnológico:**
- Django 5.1
- SQLite
- Ionic 8 (Web Components) + Alpine.js + HTMX para UI
- PyInstaller (solo para versión Desktop)
- Python 3.11+

---

## 📁 Estructura del Proyecto

```
hub/
├── apps/                      # Django apps (5 apps core)
│   ├── accounts/             # Autenticación local (LocalUser, PIN)
│   ├── configuration/        # Configuración global (HubConfig, StoreConfig)
│   ├── core/                 # Utilidades core (sin modelos)
│   ├── plugins_runtime/      # Sistema de plugins, loader dinámico
│   └── sync/                 # Sincronización con Cloud
│
├── config/                    # Configuración Django
│   ├── settings.py           # Settings (SQLite)
│   ├── urls.py
│   └── plugin_allowed_deps.py # Whitelist de librerías de plugins
│
├── plugins/                   # Plugins instalados (dinámico)
│   ├── .template/            # Template para nuevos plugins
│   └── ...                   # Plugins activos/inactivos
│
├── templates/                 # Templates Ionic + HTMX
├── static/                    # Archivos estáticos
├── locale/                    # Traducciones i18n
│
├── main.py                   # Entry point para PyInstaller (Desktop)
├── main.spec                 # PyInstaller spec file (Desktop)
├── Dockerfile                # Para despliegue Cloud
│
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
source .venv/bin/activate  # Linux/macOS
# o
.venv\Scripts\activate     # Windows

# Instalar dependencias
uv pip install -e ".[dev]"

# Configurar base de datos
python manage.py migrate

# Ejecutar servidor de desarrollo
python manage.py runserver 8001
```

Acceder a: http://127.0.0.1:8001

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

## 🔌 Sistema de Plugins

Los plugins son Django apps que se cargan dinámicamente. El Hub incluye **25 librerías Python pre-empaquetadas**.

### Activación por Filesystem

| Prefijo | Estado | Descripción |
|---------|--------|-------------|
| `plugin_name/` | **Activo** | Se carga automáticamente |
| `_plugin_name/` | **Inactivo** | Visible pero no se carga |
| `.plugin_name/` | **Oculto** | No se muestra en UI |

### Librerías Pre-empaquetadas (25)

**Imágenes & Media:** Pillow, qrcode, python-barcode

**Office & Reportes:** openpyxl, reportlab, PyPDF2

**Facturación Electrónica:** lxml, xmltodict, signxml, cryptography, zeep

**Hardware:** python-escpos, pyserial

**Network:** requests, websockets

**Pagos:** stripe

**Data & Analysis:** pandas, numpy

**Utils:** python-dateutil, pytz, phonenumbers, email-validator, python-slugify, pydantic, beautifulsoup4

Ver documentación completa: [PLUGIN_LIBRARIES_COMPLETE.md](PLUGIN_LIBRARIES_COMPLETE.md)

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

### Desktop (PyInstaller)

```bash
# Crear base de datos
python manage.py migrate --noinput

# Generar ejecutable
pyinstaller main.spec --clean

# Output:
# - Windows: dist/main/main.exe
# - macOS: dist/CPOS Hub.app
# - Linux: dist/main/main
```

**GitHub Actions:** Los builds de Desktop se generan automáticamente en push a `staging`.

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
- **Plugins**: Solo librerías whitelisted permitidas

---

## 📚 Documentación

| Documento | Descripción |
|-----------|-------------|
| [CLOUD.md](CLOUD.md) | Comunicación Hub ↔ Cloud |
| [GLOBAL_CONFIGURATION.md](GLOBAL_CONFIGURATION.md) | Sistema de configuración |
| [PLUGIN_DEPENDENCIES.md](PLUGIN_DEPENDENCIES.md) | Arquitectura de plugins |
| [PLUGIN_LIBRARIES_COMPLETE.md](PLUGIN_LIBRARIES_COMPLETE.md) | 25 librerías permitidas |
| [PLUGIN_ACTIVATION_FLOW.md](PLUGIN_ACTIVATION_FLOW.md) | Flujo de activación |
| [PLUGIN_RUNTIME_ANALYSIS.md](PLUGIN_RUNTIME_ANALYSIS.md) | Análisis del runtime |
| [PLUGIN_SUBSCRIPTION_USAGE.md](PLUGIN_SUBSCRIPTION_USAGE.md) | Sistema de suscripciones |
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
- Crear plugins para el ecosistema
- Servicios de consultoría

### ❌ Usos Prohibidos
- Ofrecer como SaaS/PaaS
- Crear plataforma POS competidora
- Revender o sublicenciar

### 🔄 Conversión a Open Source
Después del **2030-01-07**, se convierte en **Apache License 2.0**.

---

**Última actualización**: 2025-11-30
**Django**: 5.1
**Python**: 3.11+
