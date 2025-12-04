# ERPlora Hub

Sistema POS (Point of Sale) modular Django desplegado como contenedores Docker.

## Arquitectura

Cada Hub es un **contenedor Docker independiente** con:
- Django 5.1 + SQLite (base de datos propia)
- Volumen Docker persistente para datos
- Desplegado y gestionado vía Dokploy
- Acceso vía `erplora.com/hubs/{hub-id}`

## Requisitos (Desarrollo Local)

- Python 3.11+
- SQLite 3+ (incluido con Python)
- uv (gestor de paquetes Python)

## Instalación (Desarrollo)

```bash
cd hub

# Crear entorno virtual con uv
uv venv
source .venv/bin/activate  # Linux/macOS

# Instalar dependencias
uv pip install -e ".[dev]"

# Aplicar migraciones
python manage.py migrate

# Servidor de desarrollo
python manage.py runserver 8001
```

El Hub corre en puerto **8001** por defecto (Cloud Portal usa 8000).

## Estructura del Proyecto

```
hub/
├── apps/                      # Aplicaciones Django
│   ├── accounts/             # LocalUser, autenticación con PIN
│   ├── configuration/        # HubConfig, StoreConfig (singleton)
│   ├── plugins/              # Plugin model, runtime manager
│   ├── sync/                 # Cloud API client (HTTP)
│   └── core/                 # Utilidades compartidas
│
├── config/                   # Configuración Django
│   ├── settings.py
│   ├── urls.py
│   └── plugin_allowed_deps.py
│
├── plugins/                  # Plugins instalados
│   ├── .template/           # Template base para nuevos plugins
│   └── ...                  # Plugins activos
│
├── templates/               # Django templates (Ionic + HTMX)
├── static/                  # CSS/JS
├── Dockerfile               # Build para Dokploy
├── docker-compose.yml       # Deploy config
└── pyproject.toml           # Dependencias (uv)
```

## Configuración del Hub

El Hub almacena su configuración en SQLite:

```python
# apps/configuration/models.py
class HubConfig(models.Model):
    hub_id = models.UUIDField()           # UUID único del Hub
    cloud_api_token = models.CharField()  # Token para Cloud API
    is_configured = models.BooleanField() # Estado de configuración

    # Preferencias
    currency = models.CharField()         # EUR, USD, etc.
    color_theme = models.CharField()      # default, blue
    dark_mode = models.BooleanField()
    auto_print = models.BooleanField()

class StoreConfig(models.Model):
    business_name = models.CharField()    # Nombre del negocio
    tax_rate = models.DecimalField()      # Tasa de impuestos
    # ... más campos de configuración
```

## Docker Deployment

### Variables de Entorno

```bash
# Identificación (inyectadas por Dokploy)
HUB_ID=a1b2c3d4-e5f6-7890-abcd-ef1234567890

# Conexión con Cloud
CLOUD_API_URL=https://erplora.com/api
CLOUD_API_TOKEN=jwt_token_del_hub

# Django
DEBUG=false
SECRET_KEY=auto_generated_or_from_env
ALLOWED_HOSTS=erplora.com
```

### Build Local (Docker)

```bash
# Build imagen
docker build -t erplora/hub:latest .

# Test local
docker run -d \
  -p 8001:8000 \
  -e HUB_ID=test-hub-123 \
  -e DEBUG=True \
  erplora/hub:latest
```

### Volúmenes Persistentes

```
/app/data/{HUB_ID}/
├── db/
│   └── db.sqlite3        # Base de datos
├── media/                # Archivos subidos
├── logs/                 # Logs de la aplicación
├── backups/              # Backups automáticos
└── temp/                 # Archivos temporales
```

## Sistema de Plugins

El Hub soporta plugins dinámicos con dependencias pre-aprobadas.

**Dependencias permitidas**:
- `Pillow` - Imágenes
- `qrcode` - QR codes
- `python-barcode` - Códigos de barras
- `openpyxl` - Excel
- `reportlab` - PDFs
- Y más...

Ver lista completa en [config/plugin_allowed_deps.py](config/plugin_allowed_deps.py).

**Gestión de plugins**:
- Activar: mover de `_plugin_name/` a `plugin_name/`
- Desactivar: mover de `plugin_name/` a `_plugin_name/`
- Ocultar: prefijar con `.` (`.plugin_name/`)

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

## Stack Tecnológico

| Componente | Tecnología |
|------------|------------|
| Backend | Django 5.1 |
| Database | SQLite |
| Frontend | Ionic 8 (iOS mode) + Alpine.js + HTMX |
| Autenticación | LocalUser con PIN + JWT (Cloud API) |
| Deployment | Docker + Dokploy |

## Enlaces

- **Arquitectura**: [/docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md)
- **CLAUDE.md**: [/CLAUDE.md](../CLAUDE.md)
- **Plugin Development**: [/docs/plugins.md](../docs/plugins.md)
