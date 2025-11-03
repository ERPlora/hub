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
- Django 5.2
- SQLite
- Ionic 8 (Web Components) + HTMX para UI
- PyInstaller para empaquetado
- pywebview para navegador embebido

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
│
├── manage.py                 # Django management
│
├── requirements.txt          # Dependencias Python
│
├── pytest.ini                # Configuración pytest
├── conftest.py               # Fixtures globales de pytest
├── TESTING.md                # Guía de testing
│
└── venv/                     # Virtual environment
```

---

## 🚀 Setup Local (Desarrollo)

### 1. Activar virtual environment

```bash
cd hub
source venv/bin/activate  # Linux/macOS
# o
venv\Scripts\activate  # Windows
```

### 2. Instalar dependencias

```bash
pip install -r requirements.txt
```

### 3. Configurar base de datos

```bash
python manage.py migrate
```

### 4. Crear superuser local (opcional)

```bash
python manage.py createsuperuser
```

### 5. Ejecutar servidor de desarrollo

```bash
python manage.py runserver 8001
```

Acceder a: http://127.0.0.1:8001

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

Los plugins son Django apps que se cargan dinámicamente.

### Estructura de un plugin

```
plugins/
└── mi-plugin/
    ├── plugin.json           # Metadata
    ├── __init__.py
    ├── models.py
    ├── views.py
    ├── urls.py
    ├── templates/
    └── migrations/
```

### Instalación de plugin

1. Usuario descarga plugin desde Hub UI
2. Hub descarga ZIP desde Cloud API
3. Extrae en `plugins/`
4. Runtime carga automáticamente
5. Aplica migraciones
6. Plugin disponible en menú

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

Ver [TESTING.md](TESTING.md) para guía completa.

---

## 📦 Build (PyInstaller)

```bash
# Generar ejecutable
python build.py

# Output:
# - dist/cpos-hub.exe (Windows)
# - dist/cpos-hub.app (macOS)
# - dist/cpos-hub (Linux)
```

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

- [TESTING.md](TESTING.md) - Guía completa de testing
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

**Última actualización**: 2025-01-28
**Versión Django**: 5.2
**Python**: 3.14+
