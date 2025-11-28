"""
ERPlora Hub - Web/Docker Settings

Configuración para despliegue en Docker/Cloud.
Este es el entorno default para Dockerfile.

Variables de entorno requeridas:
  - HUB_NAME: Nombre del Hub (ej: mi-tienda)
  - HUB_ID: UUID del Hub (ej: abc123)
  - HUB_VOLUME_PATH: Ruta del volumen externo (desde modelo Cloud)

Estructura en disco (modo normal - persistente):
  {HUB_VOLUME_PATH}/{HUB_NAME}-{HUB_ID}/
  ├── db/db.sqlite3
  ├── media/
  ├── plugins/
  ├── logs/
  ├── backups/
  ├── reports/
  └── temp/

Modo DEMO (DEMO_MODE=true):
  - Datos almacenados en /app/data/ (dentro del contenedor)
  - NO persistente - se pierde al reiniciar contenedor
  - Sin problemas de permisos con volúmenes externos
  - Ideal para demos y testing
"""

from .base import *
from pathlib import Path

# =============================================================================
# DEPLOYMENT
# =============================================================================

DEPLOYMENT_MODE = 'web'
DEBUG = config('DEBUG', default=False, cast=bool)
OFFLINE_ENABLED = False
CLOUD_SYNC_REQUIRED = True

# =============================================================================
# DEMO MODE - Non-persistent data inside container
# =============================================================================

DEMO_MODE = config('DEMO_MODE', default=False, cast=bool)

# =============================================================================
# HUB IDENTITY (from Cloud database model)
# =============================================================================

HUB_NAME = config('HUB_NAME', default='hub')
HUB_ID = config('HUB_ID', default='default')

# =============================================================================
# PATHS - Conditional based on DEMO_MODE
# =============================================================================

if DEMO_MODE:
    # Demo mode: data inside container (non-persistent, no permission issues)
    DATA_DIR = Path('/app/data')
    HUB_FOLDER_NAME = 'demo'
    print(f"[WEB] DEMO MODE: Data stored in /app/data/ (non-persistent)")
else:
    # Production mode: data on external volume (persistent)
    HUB_VOLUME_PATH = Path(config('HUB_VOLUME_PATH', default='/app'))
    HUB_FOLDER_NAME = f"{HUB_NAME}-{HUB_ID}"
    DATA_DIR = HUB_VOLUME_PATH / HUB_FOLDER_NAME

DATA_DIR.mkdir(parents=True, exist_ok=True)

# Database
DATABASE_DIR = DATA_DIR / 'db'
DATABASE_DIR.mkdir(parents=True, exist_ok=True)
DATABASES['default']['NAME'] = DATABASE_DIR / 'db.sqlite3'

# Media
MEDIA_ROOT = DATA_DIR / 'media'
MEDIA_ROOT.mkdir(parents=True, exist_ok=True)

# Plugins
PLUGINS_DIR = DATA_DIR / 'plugins'
PLUGINS_DIR.mkdir(parents=True, exist_ok=True)
PLUGINS_ROOT = PLUGINS_DIR
PLUGIN_DISCOVERY_PATHS = [PLUGINS_DIR]

# Logs
LOGS_DIR = DATA_DIR / 'logs'
LOGS_DIR.mkdir(parents=True, exist_ok=True)
LOGGING['handlers']['file']['filename'] = str(LOGS_DIR / 'hub.log')

# Backups
BACKUPS_DIR = DATA_DIR / 'backups'
BACKUPS_DIR.mkdir(parents=True, exist_ok=True)

# Reports
REPORTS_DIR = DATA_DIR / 'reports'
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

# Temp
TEMP_DIR = DATA_DIR / 'temp'
TEMP_DIR.mkdir(parents=True, exist_ok=True)

# Plugin data (outside PLUGINS_DIR to avoid being detected as a plugin)
PLUGIN_DATA_ROOT = DATA_DIR / 'plugin_data'
PLUGIN_DATA_ROOT.mkdir(parents=True, exist_ok=True)
PLUGIN_MEDIA_ROOT = MEDIA_ROOT / 'plugins'
PLUGIN_MEDIA_ROOT.mkdir(parents=True, exist_ok=True)

# =============================================================================
# SECURITY - Configurable via environment
# =============================================================================

# ALLOWED_HOSTS from environment (comma-separated) or defaults
_allowed_hosts_env = config('ALLOWED_HOSTS', default='')
if _allowed_hosts_env:
    ALLOWED_HOSTS = [h.strip() for h in _allowed_hosts_env.split(',')]
else:
    ALLOWED_HOSTS = [
        '*.erplora.com',
        '*.int.erplora.com',
        '*.pre.erplora.com',
        'erplora.com',
        'localhost',
        '127.0.0.1',
    ]

# CSRF_TRUSTED_ORIGINS from environment (comma-separated) or defaults
_csrf_origins_env = config('CSRF_TRUSTED_ORIGINS', default='')
if _csrf_origins_env:
    CSRF_TRUSTED_ORIGINS = [o.strip() for o in _csrf_origins_env.split(',')]
else:
    CSRF_TRUSTED_ORIGINS = [
        'https://erplora.com',
        'https://*.erplora.com',
        'https://*.int.erplora.com',
        'https://*.pre.erplora.com',
    ]

CSRF_COOKIE_SECURE = True

SESSION_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True

# =============================================================================
# MIDDLEWARE - Add Cloud SSO for web deployment
# =============================================================================

MIDDLEWARE.insert(2, 'apps.core.middleware.CloudSSOMiddleware')

# =============================================================================
# PLUGIN SECURITY - Strict for web
# =============================================================================

REQUIRE_PLUGIN_SIGNATURE = True
PLUGIN_AUTO_RELOAD = False
PLUGIN_STRICT_VALIDATION = True
DEVELOPMENT_MODE = False

if DEMO_MODE:
    print(f"[WEB] Hub: {HUB_NAME} ({HUB_ID}) - DEMO MODE (non-persistent)")
else:
    print(f"[WEB] Hub: {HUB_NAME} ({HUB_ID})")
print(f"[WEB] Data: {DATA_DIR}")
