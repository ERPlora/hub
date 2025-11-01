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

---

## 📁 Estructura del Proyecto

```
hub/
├── apps/                      # Django apps
│   ├── core/                 # Configuración, auto-registro, startup
│   ├── pos/                  # Punto de venta, ventas, caja
│   ├── products/             # Gestión de productos, inventario
│   ├── sales/                # Historial de ventas, reportes
│   ├── plugins/              # Runtime de plugins, loader dinámico
│   ├── hardware/             # Servicios de impresora, scanner, cajón
│   └── sync/                 # Sincronización con Cloud
│
├── config/                    # Configuración Django
│   ├── settings.py
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
2. Usuario ingresa:
   - Email del Cloud
   - Password del Cloud
   - Nombre del Hub (ej: "Tienda Principal")
3. Hub se auto-registra en Cloud:
   - Obtiene JWT (`POST /api/auth/login/`)
   - Se registra (`POST /api/hubs/register/`)
   - Recibe: hub_id, tunnel_port, tunnel_token
4. Hub guarda credenciales en SQLite local
5. Hub inicia servicios:
   - Cliente FRP (túnel)
   - Cliente WebSocket (notificaciones)
   - Heartbeat cada 30 segundos

---

## 📡 Comunicación con Cloud

### Auto-registro
```python
# POST https://cpos.app/api/hubs/register/
# Headers: Authorization: Bearer {jwt_token}
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
    "tunnel_token": "secret_token_uuid",
    "public_key": "-----BEGIN PUBLIC KEY-----..."
}
```

### Heartbeat
```python
# WebSocket: wss://cpos.app/ws/hub/{hub_id}/?token={tunnel_token}
# Mensaje cada 30s:
{
    "type": "heartbeat",
    "timestamp": "2025-01-28T10:30:00Z"
}
```

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

```bash
# Todos los tests
pytest

# Tests unitarios
pytest apps/core/tests/

# Con coverage
pytest --cov=apps --cov-report=html
```

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

- **Tokens JWT**: Validados con clave pública RSA del Cloud
- **Base de datos local**: SQLite con permisos restrictivos
- **Modo offline**: Funciona sin conexión, sincroniza cuando vuelve online
- **Tunnel token**: Único por hub, usado para FRP y WebSocket

---

## 🐛 Troubleshooting

### Hub no se conecta al Cloud
1. Verificar conexión a internet
2. Revisar credenciales en configuración
3. Ver logs: `logs/hub.log`
4. Reiniciar servicios: `python manage.py restart_services`

### Hardware no detectado
1. Verificar drivers instalados
2. Revisar permisos USB
3. Ver logs de hardware: `python manage.py test_hardware`

### Error en sincronización
1. Verificar heartbeat activo
2. Ver estado de WebSocket: `/api/status`
3. Forzar sincronización: `python manage.py force_sync`

---

## 📚 Documentación adicional

- [Desarrollo de plugins](../docs/plugins.md)
- [Configuración de hardware](../docs/hardware.md)
- [API de sincronización](../docs/sync.md)

---

**Última actualización**: 2025-01-28
