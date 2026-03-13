"""
ERPlora Hub - Web/Docker Settings

Configuración para despliegue en Docker (App Runner on AWS).

Variables de entorno (configuradas durante deploy):
  - HUB_ID: UUID del Hub
  - HUB_NAME: Nombre del Hub (subdomain)
  - DATABASE_URL: PostgreSQL connection string (Aurora Serverless v2 or direct)
  - AWS_* : S3 credentials (optional on AWS — IAM role provides them)

Storage structure (shared per organization via AWS_LOCATION env var):

  S3 orgs/{org_prefix}/:
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
DEBUG = False  # Never enable DEBUG in production

# =============================================================================
# HUB IDENTITY (from Cloud database, passed via env vars during deploy)
# =============================================================================

HUB_ID = config('HUB_ID')  # Required - UUID del Hub
HUB_NAME = config('HUB_NAME', default='hub')

# =============================================================================
# DATA PATHS — Fixed container path, bind-mounted from host NVMe
# =============================================================================
# docker-compose mounts a volume → /app/data
# Inside the container we always use /app/data (deterministic, no env dependency)

DATA_DIR = Path('/app/data')
DATA_DIR.mkdir(parents=True, exist_ok=True)

# =============================================================================
# DATABASE - PostgreSQL (required)
# =============================================================================

DATABASE_URL = config('DATABASE_URL')
import dj_database_url
DATABASES = {'default': dj_database_url.parse(DATABASE_URL)}

# Modules - uses base.py config (MODULES_DIR from DataPaths or env var)
# In Docker: /app/modules/ by default, can be overridden via MODULES_DIR env var

# =============================================================================
# S3 STORAGE - AWS S3
# =============================================================================

# On AWS: IAM role provides credentials automatically (no keys needed)
AWS_ACCESS_KEY_ID = config('AWS_ACCESS_KEY_ID', default='')
AWS_SECRET_ACCESS_KEY = config('AWS_SECRET_ACCESS_KEY', default='')
AWS_STORAGE_BUCKET_NAME = config('AWS_STORAGE_BUCKET_NAME', default='erplora')
AWS_S3_REGION_NAME = config('AWS_S3_REGION_NAME', default='eu-west-1')
AWS_LOCATION = config('AWS_LOCATION', default=f'hubs/{HUB_ID}')  # Shared per org (orgs/{org_prefix})
AWS_DEFAULT_ACL = None  # Bucket uses ownership-enforced ACLs
AWS_S3_OBJECT_PARAMETERS = {'CacheControl': 'max-age=86400'}
AWS_S3_FILE_OVERWRITE = False
AWS_QUERYSTRING_AUTH = False
AWS_S3_USE_SSL = True
AWS_S3_VERIFY = True

# Custom S3 endpoint (optional, for S3-compatible services)
_s3_endpoint = config('AWS_S3_ENDPOINT_URL', default='')
if _s3_endpoint:
    AWS_S3_ENDPOINT_URL = _s3_endpoint
    AWS_S3_SIGNATURE_VERSION = 's3v4'

# Django storages configuration
INSTALLED_APPS += ['storages']
if _s3_endpoint:
    MEDIA_URL = f'{_s3_endpoint}/{AWS_STORAGE_BUCKET_NAME}/{AWS_LOCATION}/'
else:
    MEDIA_URL = f'https://{AWS_STORAGE_BUCKET_NAME}.s3.{AWS_S3_REGION_NAME}.amazonaws.com/{AWS_LOCATION}/'

# Local temp directory for processing (ephemeral, inside container)
MEDIA_ROOT = Path('/tmp/hub_media')
MEDIA_ROOT.mkdir(parents=True, exist_ok=True)

# S3 paths for Hub data (all under orgs/{org_prefix}/)
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

# ALLOWED_HOSTS - App Runner handles domain routing via custom domains
ALLOWED_HOSTS = ['*']

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

# HTTPS security headers
SECURE_HSTS_SECONDS = 31536000  # 1 year
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_SSL_REDIRECT = False  # App Runner handles TLS termination
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
X_FRAME_OPTIONS = 'DENY'

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
# MIDDLEWARE - Add CORS, WhiteNoise for web deployment
# =============================================================================

# CORS middleware must be before CommonMiddleware
MIDDLEWARE.insert(0, 'corsheaders.middleware.CorsMiddleware')
# WhiteNoise right after SecurityMiddleware for static files
MIDDLEWARE.insert(2, 'whitenoise.middleware.WhiteNoiseMiddleware')

# Enable CSRF protection in production (disabled in base.py for desktop mode)
# Insert CsrfViewMiddleware after CommonMiddleware
_common_idx = MIDDLEWARE.index('django.middleware.common.CommonMiddleware')
MIDDLEWARE.insert(_common_idx + 1, 'django.middleware.csrf.CsrfViewMiddleware')

# Cloud SSO middleware (cookie-based SSO across subdomains).
# On AWS (App Runner), Hubs have independent auth (trusted device + PIN or Cloud API login).
# Only enabled when a custom S3 endpoint is set (non-standard deployment).
if _s3_endpoint:
    # After insert(0, CORS) and insert(2, WhiteNoise), SessionMiddleware is at index 4
    # So we insert at 5 to place CloudSSO right after Session
    MIDDLEWARE.insert(5, 'apps.core.middleware.CloudSSOMiddleware')

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

# Cloud API URL for all Hub → Cloud communication (API calls + browser redirects)
CLOUD_API_URL = config('CLOUD_API_URL', default='https://erplora.com')
CLOUD_PUBLIC_URL = CLOUD_API_URL

# =============================================================================
# CACHE — Database-backed (shared across App Runner instances)
# =============================================================================
# Override FileBasedCache from base.py — DB cache works across instances
# and ensures rate limiting (PIN attempts) is consistent.
# Requires: python manage.py createcachetable (run once during deploy)

CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.db.DatabaseCache',
        'LOCATION': 'django_cache',
        'TIMEOUT': 300,
    }
}

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

# =============================================================================
# MODULES — Override base.py paths for NVMe structure
# =============================================================================

MODULES_DIR = DATA_DIR / 'modules'
MODULES_DIR.mkdir(parents=True, exist_ok=True)
MODULES_ROOT = MODULES_DIR
MODULE_DISCOVERY_PATHS = [MODULES_DIR]

import sys
if MODULES_DIR.exists() and str(MODULES_DIR) not in sys.path:
    sys.path.insert(0, str(MODULES_DIR))

# Load modules and their templates (pass MODULES_DIR explicitly since
# base.py's global points to /app/modules/, not /app/data/modules/)
load_modules(MODULES_DIR)
load_module_templates(MODULES_DIR)

# =============================================================================
# STARTUP INFO
# =============================================================================

_db_name = DATABASES['default'].get('NAME', DATABASE_URL.split('/')[-1] if '/' in DATABASE_URL else 'unknown')
print(f"[HUB] {HUB_NAME} ({HUB_ID}) [AWS]")
print(f"[HUB] Database: PostgreSQL - {_db_name}")
print(f"[HUB] Data: {DATA_DIR}")
print(f"[HUB] S3: {AWS_STORAGE_BUCKET_NAME}/{AWS_LOCATION}/")
