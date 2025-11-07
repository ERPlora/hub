# CPOS Hub - Aplicación POS Local

Aplicación Point of Sale local empaquetada con PyInstaller que se ejecuta standalone en Windows, macOS y Linux.

---

## 🎯 Descripción

CPOS Hub es una aplicación Django local que funciona como punto de venta (POS). Se auto-registra en el Cloud y mantiene sincronización en tiempo real.

**Características principales:**
- 💾 Base de datos local SQLite (funciona offline)
- 🔌 Sistema de plugins extensible  
- 🖨️ Soporte para hardware POS (impresora, scanner, cajón)
- 🔄 Sincronización automática con Cloud cuando hay conexión
- 🌐 Acceso remoto vía túnel FRP
- 📦 Empaquetado como ejecutable standalone (PyInstaller)

**Stack tecnológico:**
- Django 5.2.7
- SQLite
- Ionic 8 (Web Components) + Alpine.js + HTMX para UI
- PyInstaller 6.16.0 para empaquetado
- pywebview 6.1 para navegador embebido
- Python 3.11+

---

## 📁 Estructura del Proyecto

```
hub/
├── apps/                      # Django apps
│   ├── core/                 # Configuración, auto-registro, startup
│   │   ├── models.py         # HubConfig (singleton)
│   │   ├── tests/            # Tests TDD
│   │   └── services/         # RegistrationService, etc.
│   │
│   ├── pos/                  # Punto de venta, ventas, caja
│   ├── products/             # Gestión de productos, inventario
│   ├── sales/                # Historial de ventas, reportes
│   ├── plugins/              # Runtime de plugins, loader dinámico
│   ├── hardware/             # Servicios de impresora, scanner, cajón
│   └── sync/                 # Sincronización con Cloud
│
├── config/                    # Configuración Django
│   ├── settings.py           # Settings (SQLite)
│   ├── urls.py
│   └── wsgi.py
│
├── plugins/                   # Plugins instalados (dinámico)
│
├── templates/                 # Templates Ionic + HTMX
│
├── static/                    # Archivos estáticos
│
├── db.sqlite3                # Base de datos local (generado)
│
├── main.py                   # Entry point para PyInstaller
├── main.spec                 # PyInstaller spec file
│
├── manage.py                 # Django management
│
├── pyproject.toml            # Dependencias Python (uv)
│
├── pytest.ini                # Configuración pytest
├── conftest.py               # Fixtures globales de pytest
├── docs/                      # Documentación
│   ├── README.md             # Este archivo
│   ├── BUILDING.md           # Guía de build
│   ├── TESTING.md            # Guía de testing
│   ├── CHANGELOG.md          # Historial de cambios
│   ├── CLOUD.md              # Documentación de Cloud
│   ├── PLUGIN_DEPENDENCIES.md       # Arquitectura de plugins
│   └── PLUGIN_LIBRARIES_COMPLETE.md # Catálogo de 25 librerías
│
├── config/                    # Configuración adicional
│   └── plugin_allowed_deps.py # Whitelist de librerías de plugins
│
├── pyi_hooks/                 # Hooks personalizados PyInstaller
│   └── hook-django.py         # Hook Django
│
└── .venv/                     # Virtual environment (uv)
```

---

## 🚀 Setup Local (Desarrollo)

### Requisitos

- Python 3.11+
- uv (package manager)

### Instalación de uv

```bash
# macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

### 1. Crear virtual environment e instalar dependencias

```bash
cd hub
uv venv                    # Crea .venv automáticamente
source .venv/bin/activate  # Linux/macOS
# o
.venv\Scripts\activate     # Windows

uv pip install -e .        # Instala desde pyproject.toml (incluye las 25 librerías)
```

### 2. Configurar base de datos

```bash
python manage.py migrate
```

### 3. Crear superuser local (opcional)

```bash
python manage.py createsuperuser
```

### 4. Ejecutar servidor de desarrollo

```bash
python manage.py runserver 8001
```

Acceder a: http://127.0.0.1:8001

### Gestión de Dependencias

Las dependencias están definidas en `pyproject.toml`:
- **Core Hub**: Django, pywebview, pyinstaller, etc.
- **25 librerías de plugins**: Pillow, qrcode, reportlab, etc. (pre-empaquetadas)

```bash
# Actualizar dependencias
uv pip install -e .

# Ver dependencias instaladas
uv pip list
```

---

## 🔧 Configuración Inicial (Primera Vez)

Cuando el Hub se ejecuta por primera vez:

1. **Wizard de configuración** se muestra automáticamente
2. Usuario **owner** ingresa:
   - Email del Cloud
   - Password del Cloud
   - Nombre del Hub (ej: "Tienda Principal")
3. Hub se auto-registra en Cloud:
   - Obtiene JWT del owner (`POST /api/auth/login/`)
   - Se registra usando ese JWT (`POST /api/hubs/register/`)
   - Cloud asigna y retorna: `hub_id`, `tunnel_port`, `tunnel_token`
4. Hub guarda en `HubConfig` (SQLite):
   - `hub_id`, `tunnel_port`, `tunnel_token` (credenciales del HUB)
   - **NO guarda** tokens JWT del usuario (son temporales)
5. Hub marca como configurado y arranca servicios

---

## 🚀 Arranque del Hub (Después de configurado)

Cada vez que el Hub arranca:

1. **Lee `HubConfig` de SQLite**
   - Verifica si `is_configured = True`
   - Verifica si tiene `tunnel_token`

2. **Si está configurado → Conexión automática**
   - Se conecta al Cloud vía WebSocket usando `tunnel_token`
   - Cloud ve WebSocket activo → marca Hub como "online"
   - **NO necesita tokens JWT de usuario** para conectarse
   - El `tunnel_token` es la credencial permanente del Hub

3. **Inicia servicios locales**
   - Cliente FRP (túnel TCP)
   - Cliente WebSocket (heartbeat cada 30s)
   - Servicios de hardware (impresora, scanner, cajón)

4. **Si NO está configurado**
   - Muestra wizard de configuración
   - Usuario owner configura por primera vez

---

## 📡 Comunicación con Cloud

### Auto-registro

```python
# POST https://cpos.app/api/hubs/register/
# Headers: Authorization: Bearer {jwt_token_del_owner}
# Body:
{
    "name": "Tienda Principal",
    "address": "Calle 123, Ciudad"  # opcional
}

# Response:
{
    "hub_id": "uuid",
    "slug": "tienda-principal-abc123",
    "tunnel_port": 7001,
    "tunnel_token": "secret_token_uuid"
}
```

### Conexión WebSocket

```
wss://cpos.app/ws/hub/{hub_id}/?token={tunnel_token}

# Mensaje heartbeat cada 30s:
{
    "type": "heartbeat",
    "timestamp": "2025-01-28T10:30:00Z"
}
```

**IMPORTANTE**: 
- Hub usa `tunnel_token` para conectarse (NO tokens JWT de usuario)
- `tunnel_token` es la credencial permanente del Hub
- Tokens JWT de usuario son temporales y NO se guardan en HubConfig

---

## 🗄️ Modelo HubConfig

### Campos principales

```python
class HubConfig(models.Model):
    """Configuración del Hub (Singleton)"""
    
    # Identificación
    hub_id = UUIDField()              # Asignado por Cloud
    name = CharField()                # "Mi Tienda"
    
    # Conexión Cloud
    cloud_url = URLField()            # "https://cpos.app"
    
    # Credenciales del HUB (NO de usuario)
    tunnel_token = CharField()        # Token permanente
    tunnel_port = IntegerField()      # Puerto FRP (7001-7100)
    
    # Estado
    is_configured = BooleanField()
    configured_at = DateTimeField()
```

### Métodos

- `get_config()` - Obtener singleton
- `mark_as_configured()` - Marcar como configurado
- `is_registered()` - Verificar si tiene hub_id
- `has_tunnel_credentials()` - Verificar credenciales
- `can_connect_to_cloud()` - Verificar si puede conectarse

---

## 🔌 Sistema de Plugins

Los plugins son Django apps que se cargan dinámicamente. El Hub viene con **25 librerías Python pre-empaquetadas** que los plugins pueden usar sin necesidad de instalación adicional.

### Librerías Pre-empaquetadas (25)

El Hub incluye estas librerías para que los plugins las usen:

**Imágenes & Media:**
- `Pillow` - Procesamiento de imágenes
- `qrcode` - Generación de códigos QR
- `python-barcode` - Códigos de barras (EAN, UPC, Code128)

**Office & Reportes:**
- `openpyxl` - Export/import Excel
- `reportlab` - Generación de PDFs
- `PyPDF2` - Manipulación de PDFs

**Facturación Electrónica:**
- `lxml` - Procesamiento XML
- `xmltodict` - Parsing XML a diccionarios
- `signxml` - Firmas digitales XML
- `cryptography` - Cifrado y certificados
- `zeep` - Cliente SOAP (APIs Hacienda/SAT/AFIP)

**Hardware:**
- `python-escpos` - Impresoras térmicas ESC/POS
- `pyserial` - Comunicación serial (básculas, cajones, displays)

**Network:**
- `requests` - HTTP requests
- `websockets` - Cliente WebSocket

**Pagos:**
- `stripe` - Integración con Stripe

**Data & Analysis:**
- `pandas` - Análisis de datos
- `numpy` - Computación numérica

**Utils:**
- `python-dateutil` - Manejo de fechas
- `pytz` - Zonas horarias
- `phonenumbers` - Validación de teléfonos
- `email-validator` - Validación de emails
- `python-slugify` - Generación de slugs
- `pydantic` - Validación de datos
- `beautifulsoup4` - Parsing HTML

Ver documentación completa: [PLUGIN_LIBRARIES_COMPLETE.md](PLUGIN_LIBRARIES_COMPLETE.md)

### Estructura de un plugin

```
plugins/
└── mi-plugin/
    ├── plugin.json           # Metadata + dependencias
    ├── __init__.py
    ├── models.py
    ├── views.py
    ├── urls.py
    ├── templates/
    └── migrations/
```

### plugin.json

```json
{
  "plugin_id": "products",
  "name": "Products Manager",
  "version": "1.0.0",
  "dependencies": {
    "python": [
      "Pillow>=10.0.0",
      "openpyxl>=3.1.0"
    ]
  }
}
```

### Instalación de plugin

1. Usuario descarga plugin desde Hub UI
2. Hub descarga ZIP desde Cloud API
3. **Valida dependencias** (solo permite las 25 librerías whitelisted)
4. Extrae en `plugins/`
5. Runtime carga automáticamente (librerías ya están empaquetadas)
6. Aplica migraciones
7. Plugin disponible en menú

**Ventajas**:
- ✅ Instalación instantánea (sin pip install)
- ✅ Seguridad (solo librerías permitidas)
- ✅ Offline-first (librerías ya incluidas)
- ✅ No requiere compilación

---

## 🖨️ Hardware

### Impresora térmica (ESC/POS)
```python
from apps.hardware.services import PrinterService

printer = PrinterService()
printer.print_receipt(sale)
```

### Scanner de códigos de barras
```python
from apps.hardware.services import ScannerService

scanner = ScannerService()
scanner.on_scan(callback)
```

### Cajón de dinero
```python
from apps.hardware.services import CashDrawerService

drawer = CashDrawerService()
drawer.open()
```

---

## 🧪 Testing

### Ejecutar tests

```bash
# Todos los tests
pytest

# Tests de core
pytest apps/core/tests/

# Tests con verbose
pytest -v

# Tests por marker
pytest -m unit
pytest -m core

# Coverage
pytest --cov=apps --cov-report=html
open htmlcov/index.html
```

### Markers disponibles

```python
@pytest.mark.unit          # Tests unitarios
@pytest.mark.integration   # Tests de integración
@pytest.mark.core          # Tests de core app
@pytest.mark.pos           # Tests de POS
@pytest.mark.plugins       # Tests de plugins
```

### Estado actual de tests

```bash
# HubConfig model tests
15 passed in 0.11s

# Total tests por app
apps/core/tests/ - 17 tests (15 models + 2 placeholders)
apps/pos/tests/ - 2 tests (placeholders)
apps/products/tests/ - 2 tests (placeholders)
apps/sales/tests/ - 2 tests (placeholders)
apps/plugins/tests/ - 2 tests (placeholders)
apps/hardware/tests/ - 2 tests (placeholders)
apps/sync/tests/ - 2 tests (placeholders)
```

Ver [docs/TESTING.md](docs/TESTING.md) para guía completa.

---

## 📦 Build (PyInstaller)

### Build Local

```bash
# 1. Crear base de datos (REQUERIDO)
python manage.py migrate --noinput

# 2. Generar ejecutable
pyinstaller main.spec --clean

# Output:
# - dist/main/main.exe (Windows)
# - dist/CPOS Hub.app (macOS)
# - dist/main/main (Linux)
```

### Build Automático (GitHub Actions)

Ver [docs/BUILDING.md](BUILDING.md) para información completa sobre:
- Prereleases automáticas en staging (`v0.8.0-rc.1`)
- Releases finales manuales en main (`v0.8.0`)
- Workflow de desarrollo en develop

---

## 🔒 Seguridad

- **Credenciales del Hub**: `tunnel_token` guardado en SQLite
- **Base de datos local**: SQLite con permisos restrictivos
- **Modo offline**: Funciona sin conexión, sincroniza cuando vuelve online
- **Tokens JWT de usuario**: NO se guardan (son temporales)

---

## 🐛 Troubleshooting

### Hub no se conecta al Cloud

1. Verificar conexión a internet
2. Revisar credenciales en HubConfig
3. Ver logs: `logs/hub.log`
4. Verificar que `tunnel_token` existe

```python
# Verificar configuración
python manage.py shell
>>> from apps.core.models import HubConfig
>>> config = HubConfig.get_config()
>>> print(config.can_connect_to_cloud())
>>> print(config.tunnel_token)
```

### Hardware no detectado

1. Verificar drivers instalados
2. Revisar permisos USB
3. Ver logs de hardware: `python manage.py test_hardware`

### Error en sincronización

1. Verificar heartbeat activo
2. Ver estado de WebSocket
3. Forzar sincronización: `python manage.py force_sync`

### Tests fallan

```bash
# Limpiar pytest cache
pytest --cache-clear

# Recrear base de datos
python manage.py migrate --run-syncdb

# Ver output completo
pytest -vv --tb=long
```

---

## 📚 Documentación adicional

- [docs/TESTING.md](docs/TESTING.md) - Guía completa de testing
- [docs/CHANGELOG.md](docs/CHANGELOG.md) - Historial de cambios
- [docs/CLOUD.md](docs/CLOUD.md) - Documentación de Cloud
- [../CLAUDE.md](../CLAUDE.md) - Arquitectura del proyecto
- [../TODO.md](../TODO.md) - Roadmap y tareas
- [../docs/](../docs/) - Documentación técnica

---

## 🤝 Contribuir

Este es un proyecto con **TDD obligatorio**:

1. Escribir tests PRIMERO
2. Ejecutar tests (deben fallar - RED)
3. Implementar código mínimo
4. Ejecutar tests (deben pasar - GREEN)
5. Refactorizar
6. Coverage mínimo: 80%

---

**Última actualización**: 2025-01-07
**Versión Django**: 5.2.7
**Python**: 3.11+
**PyInstaller**: 6.16.0
