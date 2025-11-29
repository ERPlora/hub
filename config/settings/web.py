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
# SECURITY - PARENT_DOMAIN based configuration for SSO
# =============================================================================

# Parent domain for this instance (controls cookies and CORS)
# Examples:
#   INT:  PARENT_DOMAIN=int.erplora.com
#   PRE:  PARENT_DOMAIN=pre.erplora.com
#   PROD: PARENT_DOMAIN=erplora.com
PARENT_DOMAIN = config('PARENT_DOMAIN', default='erplora.com').strip()

# ALLOWED_HOSTS - allow parent domain and all subdomains
_allowed_hosts_env = config('ALLOWED_HOSTS', default='')
if _allowed_hosts_env:
    ALLOWED_HOSTS = [h.strip() for h in _allowed_hosts_env.split(',')]
else:
    ALLOWED_HOSTS = [
        PARENT_DOMAIN,
        f'*.{PARENT_DOMAIN}',
        'localhost',
        '127.0.0.1',
    ]

# -----------------------------------------------------------------------------
# COOKIES - Hub has its own session, reads Cloud's sessionid for SSO
# -----------------------------------------------------------------------------

# IMPORTANT: Hub uses a DIFFERENT session cookie name than Cloud
# - Cloud uses 'sessionid' (Django default)
# - Hub uses 'hubsessionid' to avoid conflicts
# - SSO middleware reads Cloud's 'sessionid' for authentication verification
# - Hub stores local session data (local_user_id, etc.) in 'hubsessionid'
SESSION_COOKIE_NAME = 'hubsessionid'

# Hub session cookie is scoped to this subdomain only (not shared)
# This prevents conflicts with Cloud's session
SESSION_COOKIE_DOMAIN = None  # Scoped to current subdomain (demo.int.erplora.com)
SESSION_COOKIE_SAMESITE = 'Lax'  # Standard security
SESSION_COOKIE_SECURE = True     # HTTPS only
SESSION_COOKIE_HTTPONLY = True

# CSRF cookies also scoped to this subdomain
CSRF_COOKIE_DOMAIN = None  # Scoped to current subdomain
CSRF_COOKIE_SAMESITE = 'Lax'
CSRF_COOKIE_SECURE = True

# CSRF trusted origins for the domain family
CSRF_TRUSTED_ORIGINS = [
    f'https://{PARENT_DOMAIN}',
    f'https://*.{PARENT_DOMAIN}',
]

# -----------------------------------------------------------------------------
# CORS - Allow cross-origin requests within domain family
# -----------------------------------------------------------------------------

# CORS base domains (can include multiple for global PROD that serves all)
# Example: CORS_BASE_DOMAINS=erplora.com,int.erplora.com,pre.erplora.com
CORS_BASE_DOMAINS = [
    d.strip() for d in config('CORS_BASE_DOMAINS', default=PARENT_DOMAIN).split(',') if d.strip()
]

# Allow all subdomains of each base domain
CORS_ALLOWED_ORIGIN_REGEXES = [
    rf'^https://.*\.{d.replace(".", r".")}$'
    for d in CORS_BASE_DOMAINS
]
# Also allow the base domains themselves
CORS_ALLOWED_ORIGIN_REGEXES += [
    rf'^https://{d.replace(".", r".")}$'
    for d in CORS_BASE_DOMAINS
]

CORS_ALLOW_CREDENTIALS = True  # Allow cookies in CORS requests

# =============================================================================
# CORS HEADERS - Required for cross-subdomain requests
# =============================================================================

INSTALLED_APPS += ['corsheaders']

# =============================================================================
# MIDDLEWARE - Add CORS, WhiteNoise and Cloud SSO for web deployment
# =============================================================================

# CORS middleware must be before CommonMiddleware
MIDDLEWARE.insert(0, 'corsheaders.middleware.CorsMiddleware')
# WhiteNoise right after SecurityMiddleware for static files
MIDDLEWARE.insert(2, 'whitenoise.middleware.WhiteNoiseMiddleware')
# Cloud SSO middleware after session middleware
MIDDLEWARE.insert(4, 'apps.core.middleware.CloudSSOMiddleware')

# =============================================================================
# STATIC FILES - WhiteNoise configuration for production
# =============================================================================

# WhiteNoise serves static files from STATIC_ROOT with compression and caching
STORAGES = {
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
}

# =============================================================================
# PLUGIN SECURITY - Strict for web
# =============================================================================

REQUIRE_PLUGIN_SIGNATURE = True
PLUGIN_AUTO_RELOAD = False
PLUGIN_STRICT_VALIDATION = True
DEVELOPMENT_MODE = False

# =============================================================================
# CLOUD API - JWT Authentication (Arquitectura Unificada Opción A)
# =============================================================================

# Cloud API URL for Hub-to-Cloud communication
CLOUD_API_URL = config('CLOUD_API_URL', default='https://erplora.com')

# Hub JWT token (generated by Cloud during deployment)
# This is a long-lived token (1 year) for Hub authentication
HUB_JWT = config('HUB_JWT', default='')

# Heartbeat configuration
HEARTBEAT_ENABLED = config('HEARTBEAT_ENABLED', default=True, cast=bool)
HEARTBEAT_INTERVAL = config('HEARTBEAT_INTERVAL', default=60, cast=int)  # seconds
COMMAND_POLL_INTERVAL = config('COMMAND_POLL_INTERVAL', default=300, cast=int)  # 5 minutes

# =============================================================================
# STARTUP INFO
# =============================================================================

if DEMO_MODE:
    print(f"[WEB] Hub: {HUB_NAME} ({HUB_ID}) - DEMO MODE (non-persistent)")
else:
    print(f"[WEB] Hub: {HUB_NAME} ({HUB_ID})")
print(f"[WEB] Data: {DATA_DIR}")
if HUB_JWT:
    print(f"[WEB] Cloud API: {CLOUD_API_URL} (JWT configured)")
