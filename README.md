# ERPlora Hub

Aplicación de punto de venta (POS) local con sincronización en la nube.

## Requisitos

- Python 3.11+
- SQLite 3+ (incluido con Python)
- uv (gestor de paquetes Python)

## Instalación

```bash
# Clonar repositorio
cd hub

# Crear entorno virtual con uv
uv venv

# Activar entorno virtual
source .venv/bin/activate  # Linux/macOS
# o
.venv\Scripts\activate  # Windows

# Instalar dependencias
uv pip install -e ".[dev]"
```

## Configuración Inicial

Al iniciar por primera vez, el Hub mostrará un asistente de configuración donde:

1. **Conectar con Cloud**: Ingresar credenciales de usuario owner
2. **Auto-registro**: El Hub se registra automáticamente en Cloud
3. **Obtención de credenciales**: Cloud asigna:
   - `hub_id`: UUID único del Hub
   - `tunnel_port`: Puerto para túnel FRP
   - `tunnel_token`: Token permanente para autenticación

Estas credenciales se guardan en SQLite local y el Hub quedará listo para usar.

## Base de Datos

```bash
# Aplicar migraciones
python manage.py migrate
```

## Desarrollo

### Servidor de Desarrollo (Django runserver)

```bash
python manage.py runserver 8001
```

El Hub corre en puerto **8001** por defecto (Cloud usa 8000).

### Servicios Automáticos (Startup Tasks)

Al iniciar el servidor, el Hub ejecuta automáticamente:

1. **Check de actualizaciones** (background thread)
   - Verifica última versión disponible en Cloud
   - Endpoint: `GET /version/check/?current_version=X&os=Y`

2. **Cliente FRP** (background thread)
   - Establece túnel TCP hacia Cloud para acceso remoto
   - Conecta a `localhost:7100` (servidor FRP en Cloud)
   - Puerto asignado: `7102` (único por Hub)

3. **Cliente WebSocket** (background thread) ✅ **Importante**
   - Conecta a Cloud: `ws://localhost:8000/ws/hub/{hub_id}/?token={tunnel_token}`
   - Autentica con `tunnel_token` (credencial permanente del Hub)
   - **Envía heartbeats cada 30 segundos** → Cloud actualiza `last_heartbeat`
   - Recibe notificaciones de Cloud (plugin updates, user revocations)
   - **Requiere que Cloud esté corriendo con Daphne (ASGI)**, no con `runserver`

### Estado del Hub: Online/Offline

El Hub aparece como **"Online"** en el dashboard de Cloud cuando:
- ✅ WebSocket está conectado
- ✅ Cloud recibe heartbeats (últimos 5 minutos)

**Si el Hub aparece "Offline"**:
1. Verificar que Cloud está corriendo con **Daphne** (no `runserver`)
2. Verificar logs del Hub: `[INFO] ✅ WebSocket client started successfully`
3. Verificar logs de Cloud: `Hub {hub_id}: WebSocket connected (auth: tunnel_token)`

## Testing

```bash
# Todos los tests
pytest

# Tests específicos
pytest tests/unit
pytest tests/integration

# Con coverage
pytest --cov=apps --cov-report=html
```

## Build (PyInstaller)

```bash
# Generar ejecutable
python build.py

# Ejecutables generados en:
# - Windows: dist/ERPlora Hub/ERPlora Hub.exe
# - macOS: dist/ERPlora Hub.app
# - Linux: dist/ERPlora Hub/ERPlora Hub
```

Ver [docs/BUILD.md](../docs/BUILD.md) para más detalles sobre el proceso de build.

## Estructura del Proyecto

```
hub/
├── apps/                      # Aplicaciones Django
│   ├── core/                 # Configuración, startup, WebSocket client
│   │   ├── models.py        # HubConfig, LocalUser
│   │   ├── startup.py       # Tareas de inicio (FRP, WebSocket)
│   │   ├── websocket_client.py  # Cliente WebSocket para Cloud
│   │   └── frp_client.py    # Cliente FRP para túnel
│   ├── pos/                 # Punto de venta
│   ├── products/            # Productos e inventario
│   ├── sales/               # Ventas y reportes
│   ├── hardware/            # Impresora, cajón, scanner
│   └── plugins/             # Runtime de plugins
│
├── config/                   # Configuración Django
│   ├── settings.py          # Settings
│   ├── urls.py              # URLs principales
│   └── plugin_allowed_deps.py  # Dependencias permitidas para plugins
│
├── plugins/                  # Plugins instalados
│   └── installed/           # Directorio de plugins activos
│
├── templates/               # Templates Django
├── static/                  # Archivos estáticos
├── assets/                  # Assets para build (iconos, etc.)
├── main.py                  # Entry point para PyInstaller
├── main.spec                # Configuración PyInstaller
└── tests/                   # Tests
```

## Servicios de Background

### WebSocket Client

**Ubicación**: `apps/core/websocket_client.py`

**Funciones**:
- Conecta a Cloud vía WebSocket
- Envía heartbeat cada 30 segundos
- Recibe notificaciones en tiempo real

**Mensajes enviados** (Hub → Cloud):
```python
# Heartbeat
{
    "type": "heartbeat",
    "timestamp": "2025-01-11T10:23:00Z"
}

# Sincronización de usuarios
{
    "type": "user_sync",
    "users": [...]
}

# Plugin instalado
{
    "type": "plugin_installed",
    "plugin_id": "products",
    "version": "1.0.0"
}
```

**Mensajes recibidos** (Cloud → Hub):
```python
# Confirmación de heartbeat
{
    "type": "heartbeat_ack",
    "timestamp": "2025-01-11T10:23:00Z"
}

# Actualización de plugin disponible
{
    "type": "plugin_update_available",
    "plugin_id": "products",
    "version": "1.1.0"
}

# Usuario revocado
{
    "type": "user_revoked",
    "user_id": 123
}

# Solicitud de backup
{
    "type": "backup_request",
    "request_id": "abc-123"
}
```

### FRP Client

**Ubicación**: `apps/core/frp_client.py`

Establece túnel TCP hacia Cloud para acceso remoto al Hub:
- Servidor FRP: `localhost:7100`
- Puerto local: `8001` (Django)
- Puerto remoto: `7102` (asignado por Cloud)
- URL pública: `https://hub-{slug}.erplora.com`

### Update Manager

**Ubicación**: `apps/core/update_manager.py`

Verifica actualizaciones disponibles:
- Endpoint: `GET /version/check/?current_version=1.0.0&os=macos`
- Compara versión local con última disponible
- Notifica al usuario si hay actualización

## Sistema de Plugins

El Hub soporta plugins dinámicos con **25 dependencias pre-empaquetadas**.

**Dependencias permitidas**:
- `Pillow` - Imágenes
- `qrcode` - QR codes
- `python-barcode` - Códigos de barras
- `openpyxl` - Excel
- `reportlab` - PDFs
- `python-escpos` - Impresoras térmicas
- `lxml`, `signxml`, `zeep` - Facturación electrónica
- Y más...

Ver lista completa en [config/plugin_allowed_deps.py](config/plugin_allowed_deps.py).

**Instalación de plugin**:
1. Usuario descarga ZIP desde Cloud marketplace
2. Hub valida `plugin.json` (dependencias, versión)
3. Extrae en `plugins/installed/{plugin_id}/`
4. Runtime carga como Django app
5. Aplica migraciones
6. Plugin listo para usar

Ver [docs/PLUGINS.md](../docs/PLUGINS.md) para más detalles.

## Configuración Local

El Hub almacena su configuración en SQLite:

```python
# apps/core/models.py
class HubConfig(models.Model):
    hub_id = models.UUIDField()           # UUID del Hub
    tunnel_port = models.IntegerField()   # Puerto FRP
    tunnel_token = models.CharField()     # Token permanente
    is_configured = models.BooleanField() # Estado de configuración

    # Preferencias
    color_theme = models.CharField()      # default, blue
    dark_mode = models.BooleanField()
    auto_print = models.BooleanField()
```

## Offline Mode

El Hub funciona 100% offline después de la configuración inicial:
- Base de datos local (SQLite)
- Usuarios con PIN para login offline
- Sincronización on-demand cuando Cloud está disponible

**Sincronización**:
- **Proactiva**: Hub envía datos cuando Cloud está online
- **On-access**: Hub verifica permisos durante login con Cloud
- **Resiliente**: Fallback a estado local si Cloud no disponible

## Variables de Entorno

| Variable | Descripción | Ejemplo |
|----------|-------------|---------|
| `DEBUG` | Modo debug | `True` |
| `SECRET_KEY` | Secret key de Django | (generado) |
| `CLOUD_URL` | URL del Cloud | `http://localhost:8000` |
| `CLOUD_WS_URL` | URL WebSocket del Cloud | `ws://localhost:8000` |

## Troubleshooting

### Hub aparece Offline

**Problema**: Dashboard de Cloud muestra Hub como "Offline"

**Causas posibles**:
1. Cloud no está corriendo con Daphne (usa `runserver` que no soporta WebSockets)
2. WebSocket no puede conectar
3. Hub no está enviando heartbeats

**Solución**:
```bash
# 1. Verificar que Cloud corre con Daphne
cd ../cloud
daphne -b 127.0.0.1 -p 8000 config.asgi:application

# 2. Verificar logs del Hub
# Debe mostrar:
[INFO] ✅ WebSocket client started successfully
[DEBUG] Hub xxx: Heartbeat sent

# 3. Verificar logs de Cloud
# Debe mostrar:
Hub xxx: WebSocket connected (auth: tunnel_token)
```

### WebSocket no conecta

**Error**: `[ERROR] Hub xxx: WebSocket connection failed: HTTP 404`

**Causa**: Cloud está corriendo con `runserver` (WSGI) en lugar de Daphne (ASGI)

**Solución**: Detener `runserver` e iniciar con Daphne:
```bash
# Detener runserver
# Ctrl+C

# Iniciar con Daphne
daphne -b 127.0.0.1 -p 8000 config.asgi:application
```

### FRP no conecta

**Error**: `[ERROR] Failed to start FRP client`

**Causa**: Servidor FRP no está corriendo en Cloud

**Solución**: Verificar infraestructura local:
```bash
cd ../infra/local
docker-compose up -d frp-server
```

## Enlaces

- **Documentación completa**: [/docs](../docs)
- **CLAUDE.md**: [/CLAUDE.md](../CLAUDE.md) - Guía para desarrollo con Claude Code
- **Build Guide**: [/docs/BUILD.md](../docs/BUILD.md)
- **Plugin Development**: [/docs/PLUGINS.md](../docs/PLUGINS.md)
