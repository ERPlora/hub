"""
ERPlora Hub - Web/Docker Settings

Configuración para despliegue en Docker/Cloud.
Desplegado automáticamente via Coolify API cuando el cliente compra un Hub.

Variables de entorno (configuradas por Cloud durante deploy):
  - HUB_ID: UUID del Hub (ej: 1aba6e2f-777b-450d-9818-edc2bd0a93c4)
  - HUB_NAME: Nombre del Hub (ej: mi-tienda)
  - AWS_* : Credenciales S3

Estructura de almacenamiento (todo automático via HUB_ID):

  Docker Volume /app/data/{HUB_ID}/:
    - db/db.sqlite3 - Base de datos SQLite

  S3 hubs/{HUB_ID}/:
    - logs/        - Logs de aplicación
    - backups/     - Backups de BD
    - temp/        - Archivos temporales
    - plugin_data/ - Datos de plugins
    - reports/     - Reportes generados
    - media/       - Archivos subidos (Django media)
"""

from .base import *
from pathlib import Path

# =============================================================================
# DEPLOYMENT
# =============================================================================

DEPLOYMENT_MODE = 'web'
DEBUG = config('DEBUG', default=False, cast=bool)

# =============================================================================
# HUB IDENTITY (from Cloud database, passed via env vars during deploy)
# =============================================================================

HUB_ID = config('HUB_ID')  # Required - UUID del Hub
HUB_NAME = config('HUB_NAME', default='hub')

# =============================================================================
# PATHS - Local storage for SQLite (persistent via Docker Volume)
# =============================================================================

# Data directory - /app/data is a Docker Volume shared by all Hubs on this server
# Each Hub uses HUB_ID as subfolder to isolate its database
DATA_DIR = Path('/app/data')
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Database (SQLite) - isolated by HUB_ID folder
# Structure: /app/data/{HUB_ID}/db/db.sqlite3
DATABASE_DIR = DATA_DIR / HUB_ID / 'db'
DATABASE_DIR.mkdir(parents=True, exist_ok=True)
DATABASES['default']['NAME'] = DATABASE_DIR / 'db.sqlite3'

# Plugins - stored locally in container (distributed from Cloud marketplace)
# Coolify deploys with latest plugins from GitHub repo
PLUGINS_DIR = BASE_DIR / 'plugins'
PLUGINS_ROOT = PLUGINS_DIR
PLUGIN_DISCOVERY_PATHS = [PLUGINS_DIR]

# =============================================================================
# S3 STORAGE - Hetzner Object Storage (hubs/{HUB_ID}/)
# =============================================================================

AWS_ACCESS_KEY_ID = config('AWS_ACCESS_KEY_ID')
AWS_SECRET_ACCESS_KEY = config('AWS_SECRET_ACCESS_KEY')
AWS_STORAGE_BUCKET_NAME = config('AWS_STORAGE_BUCKET_NAME', default='erplora')
AWS_S3_ENDPOINT_URL = config('AWS_S3_ENDPOINT_URL', default='https://fsn1.your-objectstorage.com')
AWS_S3_REGION_NAME = config('AWS_S3_REGION_NAME', default='eu-central')
AWS_LOCATION = f'hubs/{HUB_ID}'  # Each Hub has its own S3 folder
AWS_DEFAULT_ACL = 'public-read'
AWS_S3_OBJECT_PARAMETERS = {'CacheControl': 'max-age=86400'}
AWS_S3_SIGNATURE_VERSION = 's3v4'
AWS_S3_FILE_OVERWRITE = False
AWS_QUERYSTRING_AUTH = False
AWS_S3_USE_SSL = True
AWS_S3_VERIFY = True

# Django storages configuration
INSTALLED_APPS += ['storages']
MEDIA_URL = f'{AWS_S3_ENDPOINT_URL}/{AWS_STORAGE_BUCKET_NAME}/{AWS_LOCATION}/'

# Local temp directory for processing (ephemeral, inside container)
MEDIA_ROOT = Path('/tmp/hub_media')
MEDIA_ROOT.mkdir(parents=True, exist_ok=True)

# S3 paths for Hub data (all under hubs/{HUB_ID}/)
S3_LOGS_PREFIX = 'logs'
S3_BACKUPS_PREFIX = 'backups'
S3_TEMP_PREFIX = 'temp'
S3_PLUGIN_DATA_PREFIX = 'plugin_data'
S3_REPORTS_PREFIX = 'reports'

# Local temp paths for code that needs filesystem access
LOGS_DIR = MEDIA_ROOT / 'logs'
LOGS_DIR.mkdir(parents=True, exist_ok=True)
BACKUPS_DIR = MEDIA_ROOT / 'backups'
BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
TEMP_DIR = MEDIA_ROOT / 'temp'
TEMP_DIR.mkdir(parents=True, exist_ok=True)
PLUGIN_DATA_ROOT = MEDIA_ROOT / 'plugin_data'
PLUGIN_DATA_ROOT.mkdir(parents=True, exist_ok=True)
REPORTS_DIR = MEDIA_ROOT / 'reports'
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

# Logging to local file (ephemeral)
LOGGING['handlers']['file']['filename'] = str(LOGS_DIR / 'hub.log')

# Plugin media
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
# STATIC & MEDIA STORAGE BACKENDS
# =============================================================================

STORAGES = {
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
    "default": {
        "BACKEND": "storages.backends.s3boto3.S3Boto3Storage",
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

print(f"[HUB] {HUB_NAME} ({HUB_ID})")
print(f"[HUB] Database: {DATABASES['default']['NAME']}")
print(f"[HUB] S3: {AWS_STORAGE_BUCKET_NAME}/{AWS_LOCATION}/")
