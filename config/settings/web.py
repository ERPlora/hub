"""
ERPlora Hub - Web/Docker Settings

Configuración para despliegue en Docker/Cloud.
Desplegado automáticamente via Dokploy API cuando el cliente compra un Hub.

Variables de entorno (configuradas por Cloud durante deploy):
  - HUB_ID: UUID del Hub
  - HUB_NAME: Nombre del Hub (subdomain)
  - DATABASE_URL: PostgreSQL connection (Hub plan - shared per org)
  - DATABASE_PATH: SQLite path (Starter plan - isolated per hub)
  - AWS_* : Credenciales S3

Database Configuration:
  - Starter plan: SQLite per Hub (DATABASE_PATH)
    Each Hub has its own isolated database.

  - Hub plan: PostgreSQL per Organization (DATABASE_URL)
    All Hubs in the same organization share one PostgreSQL database.
    Products, clients, and inventory are shared across stores.

Storage structure (automatic via HUB_ID):

  Docker Volume /app/data/:
    - db/db.sqlite3 - SQLite (Starter plan only)

  S3 hubs/{HUB_ID}/:
    - backups/     - Database backups
    - module_data/ - Module data
    - reports/     - Generated reports
    - media/       - Uploaded files (Django media)

  Container (ephemeral):
    - /tmp/hub_media/ - Temporary processing files
    - Logs via stdout/stderr (Docker captures automatically)
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
# DATABASE - PostgreSQL (Hub plan) or SQLite (Starter plan)
# =============================================================================

# Cloud deploys Hubs with one of:
#   - DATABASE_URL: PostgreSQL for Hub plan (shared per organization)
#   - DATABASE_PATH: SQLite for Starter plan (isolated per Hub)

DATABASE_URL = config('DATABASE_URL', default='')
DATABASE_PATH = config('DATABASE_PATH', default='')

if DATABASE_URL:
    # Hub plan: PostgreSQL (shared database for all Hubs in organization)
    import dj_database_url
    DATABASES = {
        'default': dj_database_url.parse(DATABASE_URL)
    }
    # Data directory for other local files (logs, temp, etc.)
    DATA_DIR = Path('/app/data')
else:
    # Starter plan: SQLite (isolated database per Hub)
    # Data directory - /app/data is mounted as Docker Volume
    DATA_DIR = Path('/app/data')

    # Database (SQLite) - inside the Hub's data directory
    if DATABASE_PATH:
        # Use explicit path from Cloud deployment
        db_path = Path(DATABASE_PATH)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        DATABASES['default']['NAME'] = db_path
    else:
        # Default fallback
        DATABASE_DIR = DATA_DIR / 'db'
        DATABASE_DIR.mkdir(parents=True, exist_ok=True)
        DATABASES['default']['NAME'] = DATABASE_DIR / 'db.sqlite3'

# Modules - uses base.py config (MODULES_DIR from DataPaths or env var)
# In Docker: /app/modules/ by default, can be overridden via MODULES_DIR env var

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
# Note: logs go to Docker stdout/stderr, not S3
S3_BACKUPS_PREFIX = 'backups'
S3_TEMP_PREFIX = 'temp'
S3_MODULE_DATA_PREFIX = 'module_data'
S3_REPORTS_PREFIX = 'reports'

# Local temp paths for code that needs filesystem access
BACKUPS_DIR = MEDIA_ROOT / 'backups'
BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
TEMP_DIR = MEDIA_ROOT / 'temp'
TEMP_DIR.mkdir(parents=True, exist_ok=True)
MODULE_DATA_ROOT = MEDIA_ROOT / 'module_data'
MODULE_DATA_ROOT.mkdir(parents=True, exist_ok=True)
REPORTS_DIR = MEDIA_ROOT / 'reports'
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

# =============================================================================
# LOGGING - Console only (Docker captures stdout/stderr)
# =============================================================================

# Remove file handler - Docker logs capture everything
LOGGING['handlers'].pop('file', None)

# Update loggers to use only console
LOGGING['root']['handlers'] = ['console']
LOGGING['loggers']['django']['handlers'] = ['console']
LOGGING['loggers']['apps']['handlers'] = ['console']

# Module media
MODULE_MEDIA_ROOT = MEDIA_ROOT / 'modules'
MODULE_MEDIA_ROOT.mkdir(parents=True, exist_ok=True)

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
# MODULE SECURITY - Strict for web
# =============================================================================

REQUIRE_MODULE_SIGNATURE = True
MODULE_AUTO_RELOAD = False
MODULE_STRICT_VALIDATION = True
DEVELOPMENT_MODE = False

# =============================================================================
# CLOUD API - JWT Authentication (Arquitectura Unificada Opción A)
# =============================================================================

# Cloud API URL for Hub-to-Cloud communication
# Read from CLOUD_BASE_URL (consistent with Cloud) or fallback to CLOUD_API_URL for backwards compatibility
CLOUD_API_URL = config('CLOUD_BASE_URL', default=config('CLOUD_API_URL', default='https://erplora.com'))

# Hub JWT token (generated by Cloud during deployment)
# This is a long-lived token (1 year) for Hub authentication
HUB_JWT = config('HUB_JWT', default='')

# Cloud Sync configuration
# WebSocket is preferred (real-time), HTTP polling is fallback
CLOUD_SYNC_ENABLED = config('CLOUD_SYNC_ENABLED', default=True, cast=bool)
CLOUD_SYNC_WEBSOCKET = config('CLOUD_SYNC_WEBSOCKET', default=True, cast=bool)

# HTTP polling intervals (used when WebSocket is disabled)
HEARTBEAT_INTERVAL = config('HEARTBEAT_INTERVAL', default=60, cast=int)  # seconds
COMMAND_POLL_INTERVAL = config('COMMAND_POLL_INTERVAL', default=30, cast=int)  # seconds

# =============================================================================
# STARTUP INFO
# =============================================================================

_db_type = 'PostgreSQL' if DATABASE_URL else 'SQLite'
_db_name = DATABASES['default'].get('NAME', DATABASE_URL.split('/')[-1] if DATABASE_URL else 'unknown')
print(f"[HUB] {HUB_NAME} ({HUB_ID})")
print(f"[HUB] Database: {_db_type} - {_db_name}")
print(f"[HUB] S3: {AWS_STORAGE_BUCKET_NAME}/{AWS_LOCATION}/")
