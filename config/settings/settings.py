"""
ERPlora Hub - Unified Settings

Single configuration file for all environments (local development + Docker/Cloud).
Environment differences are controlled via environment variables, not separate files.

Data Structure (identical in local and Docker):
    /data/hubs/{HUB_ID}/
    ├── db/db.sqlite3      - SQLite database (Starter plan)
    ├── modules/           - Installed modules
    ├── media/             - Uploaded files (local only; S3 in production)
    ├── logs/              - Application logs
    ├── backups/           - Database backups
    └── reports/           - Generated reports

Environment Variables:
    HUB_ID          - Hub UUID (default: 'local' for development)
    HUB_NAME        - Hub subdomain (default: 'hub')
    VOLUME_PATH     - NVMe root path (default: '/data')
    DATABASE_URL    - PostgreSQL connection (Hub plan, overrides SQLite)
    DATABASE_PATH   - SQLite path (auto-derived from VOLUME_PATH/HUB_ID)
    PARENT_DOMAIN   - Set to enable web features (SSO, CORS, WhiteNoise)
    AWS_ACCESS_KEY_ID - Set to enable S3 storage
    DEBUG           - Enable debug mode (default: true when DEPLOYMENT_MODE=local)
"""

import sys
import os
import secrets
from pathlib import Path
from decouple import config


def _ensure_dir(path: Path) -> Path:
    """Create directory if possible, silently skip if not (e.g. read-only FS)."""
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    return path


# =============================================================================
# PATHS
# =============================================================================

BASE_DIR = Path(__file__).resolve().parent.parent.parent

# =============================================================================
# DEPLOYMENT
# =============================================================================

DEPLOYMENT_MODE = config('DEPLOYMENT_MODE', default='local')
DEBUG = config('DEBUG', default=str(DEPLOYMENT_MODE == 'local'), cast=bool)
DEVELOPMENT_MODE = config('ERPLORA_DEV_MODE', default=str(DEPLOYMENT_MODE == 'local'), cast=bool)
OFFLINE_ENABLED = True
CLOUD_SYNC_REQUIRED = False
DEMO_MODE = False

# =============================================================================
# HUB IDENTITY
# =============================================================================

HUB_ID = config('HUB_ID', default='local')
HUB_NAME = config('HUB_NAME', default='hub')
HUB_LOCAL_PORT = config('HUB_LOCAL_PORT', default=8001, cast=int)
HUB_VERSION = "1.0.0"

# =============================================================================
# SECURITY
# =============================================================================


def get_or_create_secret_key():
    """Get SECRET_KEY from environment or generate and persist one."""
    secret_key = config('SECRET_KEY', default='')
    if secret_key:
        return secret_key

    secret_file = BASE_DIR / '.secret_key'
    if secret_file.exists():
        return secret_file.read_text().strip()

    new_key = secrets.token_urlsafe(50)
    try:
        secret_file.write_text(new_key)
        print(f"[SECURITY] Generated new SECRET_KEY: {secret_file}")
    except PermissionError:
        print(f"[SECURITY] Warning: Could not persist SECRET_KEY to {secret_file}")
    return new_key


SECRET_KEY = get_or_create_secret_key()
ALLOWED_HOSTS = ['127.0.0.1', 'localhost', '*'] if DEBUG else ['127.0.0.1', 'localhost']

# CSRF defaults (relaxed for local Hub — security via PIN codes)
CSRF_COOKIE_SECURE = False
CSRF_COOKIE_HTTPONLY = False
CSRF_USE_SESSIONS = False
CSRF_COOKIE_SAMESITE = 'Lax'
CSRF_TRUSTED_ORIGINS = [
    'http://localhost:8000',
    'http://127.0.0.1:8000',
    'http://localhost:8001',
    'http://127.0.0.1:8001',
]

# =============================================================================
# DATA PATHS — Same structure in local and Docker
# =============================================================================
# Local:  ~/.erplora/hubs/local/
# Docker: /data/hubs/{uuid}/  (bind-mounted from host NVMe)

_DEFAULT_VOLUME_PATH = '/data' if DEPLOYMENT_MODE == 'web' else str(Path.home() / '.erplora')
VOLUME_PATH = config('VOLUME_PATH', default=_DEFAULT_VOLUME_PATH)
DATA_DIR = _ensure_dir(Path(VOLUME_PATH) / 'hubs' / HUB_ID)

# =============================================================================
# DATABASE — PostgreSQL (Hub plan) or SQLite (Starter plan)
# =============================================================================

DATABASE_URL = config('DATABASE_URL', default='')
DATABASE_PATH = config('DATABASE_PATH', default=str(DATA_DIR / 'db' / 'db.sqlite3'))

if DATABASE_URL:
    import dj_database_url
    DATABASES = {
        'default': dj_database_url.parse(DATABASE_URL)
    }
else:
    db_path = Path(DATABASE_PATH)
    _ensure_dir(db_path.parent)
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': db_path,
        }
    }

# =============================================================================
# APPLICATION DEFINITION
# =============================================================================

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    # Third-party
    'rest_framework',
    'drf_spectacular',
    'drf_spectacular_sidecar',
    'djmoney',
    'django_htmx',
    'djicons',
    'django_components',
    # Health Check
    'health_check',
    'health_check.db',
    'health_check.cache',
    'health_check.storage',
    # Hub apps - Core
    'apps.accounts.apps.AccountsConfig',
    'apps.configuration.apps.ConfigurationConfig',
    'apps.sync.apps.SyncConfig',
    'apps.core.apps.CoreConfig',
    'apps.modules_runtime',
    # Hub apps - Auth
    'apps.auth.login.apps.AuthLoginConfig',
    # Hub apps - Main
    'apps.main.index.apps.MainIndexConfig',
    'apps.main.files.apps.FilesConfig',
    'apps.main.settings.apps.MainSettingsConfig',
    'apps.main.employees.apps.MainEmployeesConfig',
    'apps.setup.apps.SetupConfig',
    'apps.main.roles.apps.RolesConfig',
    # Hub apps - System
    'apps.system.modules.apps.SystemModulesConfig',
    # Hub apps - Marketplace
    'apps.marketplace.apps.MarketplaceConfig',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'apps.accounts.middleware.LanguageMiddleware',
    'django.middleware.common.CommonMiddleware',
    # CSRF disabled for local Hub (security via PIN codes)
    # 'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'apps.accounts.middleware.LocalUserAuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'django_htmx.middleware.HtmxMiddleware',
    'apps.accounts.middleware.jwt_middleware.JWTMiddleware',
    'apps.configuration.middleware.StoreConfigCheckMiddleware',
    'apps.core.middleware.module_middleware_manager.ModuleMiddlewareManager',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [
            BASE_DIR / 'templates',
        ],
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.template.context_processors.i18n',
                'django.template.context_processors.static',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'apps.core.context_processors.cloud_url',
                'apps.core.context_processors.module_menu_items',
                'apps.core.context_processors.hub_config_context',
                'apps.core.context_processors.deployment_config',
                'apps.core.context_processors.navigation_context',
                'apps.core.context_processors.module_context',
                'apps.configuration.context_processors.global_config',
            ],
            'loaders': [
                (
                    'django.template.loaders.cached.Loader',
                    [
                        'django.template.loaders.filesystem.Loader',
                        'django.template.loaders.app_directories.Loader',
                        'django_components.template_loader.Loader',
                    ],
                ),
            ],
            'builtins': [
                'django_components.templatetags.component_tags',
                'djicons.templatetags.djicons',
            ],
            'libraries': {
                'djicons': 'djicons.templatetags.djicons',
            },
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

# =============================================================================
# PASSWORD VALIDATION
# =============================================================================

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LOGIN_URL = '/login/'

# =============================================================================
# INTERNATIONALIZATION
# =============================================================================

LANGUAGE_CODE = 'en'
LANGUAGES = [
    ('en', 'English'),
    ('es', 'Español'),
]
LOCALE_PATHS = [BASE_DIR / 'locale']
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

LANGUAGE_COOKIE_NAME = 'django_language'
LANGUAGE_COOKIE_AGE = 31536000  # 1 year
LANGUAGE_COOKIE_SECURE = False
LANGUAGE_COOKIE_SAMESITE = 'Lax'

# =============================================================================
# STATIC FILES
# =============================================================================

STATIC_URL = 'static/'
STATICFILES_DIRS = [BASE_DIR / 'static']

# UX library — served as static/ux/*
_UX_DIST = Path(config('UX_DIST_PATH', default=str(BASE_DIR.parent.parent / 'ux' / 'dist')))
if _UX_DIST.is_dir():
    STATICFILES_DIRS.append(('ux', _UX_DIST))

STATIC_ROOT = BASE_DIR / 'staticfiles'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# =============================================================================
# MEDIA & STORAGE — S3 if credentials present, local filesystem otherwise
# =============================================================================

AWS_ACCESS_KEY_ID = config('AWS_ACCESS_KEY_ID', default='') if DEPLOYMENT_MODE == 'web' else ''
AWS_SECRET_ACCESS_KEY = config('AWS_SECRET_ACCESS_KEY', default='') if DEPLOYMENT_MODE == 'web' else ''

if AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY:
    # Production: S3 storage (Hetzner Object Storage)
    AWS_STORAGE_BUCKET_NAME = config('AWS_STORAGE_BUCKET_NAME', default='erplora')
    AWS_S3_ENDPOINT_URL = config('AWS_S3_ENDPOINT_URL', default='https://fsn1.your-objectstorage.com')
    AWS_S3_REGION_NAME = config('AWS_S3_REGION_NAME', default='eu-central')
    AWS_LOCATION = f'hubs/{HUB_ID}'
    AWS_DEFAULT_ACL = 'public-read'
    AWS_S3_OBJECT_PARAMETERS = {'CacheControl': 'max-age=86400'}
    AWS_S3_SIGNATURE_VERSION = 's3v4'
    AWS_S3_FILE_OVERWRITE = False
    AWS_QUERYSTRING_AUTH = False
    AWS_S3_USE_SSL = True
    AWS_S3_VERIFY = True

    INSTALLED_APPS += ['storages']
    MEDIA_URL = f'{AWS_S3_ENDPOINT_URL}/{AWS_STORAGE_BUCKET_NAME}/{AWS_LOCATION}/'
    MEDIA_ROOT = _ensure_dir(Path('/tmp/hub_media'))

    S3_BACKUPS_PREFIX = 'backups'
    S3_TEMP_PREFIX = 'temp'
    S3_MODULE_DATA_PREFIX = 'module_data'
    S3_REPORTS_PREFIX = 'reports'
else:
    # Local: filesystem storage
    MEDIA_URL = 'media/'
    MEDIA_ROOT = _ensure_dir(DATA_DIR / 'media')

# Data directories
BACKUPS_DIR = _ensure_dir(DATA_DIR / 'backups')
REPORTS_DIR = _ensure_dir(DATA_DIR / 'reports')
MODULE_DATA_ROOT = _ensure_dir(DATA_DIR / 'module_data')
MODULE_MEDIA_ROOT = _ensure_dir(MEDIA_ROOT / 'modules')

# =============================================================================
# MODULE SYSTEM
# =============================================================================

MODULES_DIR = _ensure_dir(Path(config('MODULES_DIR', default=str(DATA_DIR / 'modules'))))
MODULES_ROOT = MODULES_DIR
MODULE_DISCOVERY_PATHS = [MODULES_DIR]

# Module security
REQUIRE_MODULE_SIGNATURE = not DEVELOPMENT_MODE
MODULE_AUTO_RELOAD = DEVELOPMENT_MODE
MODULE_STRICT_VALIDATION = not DEVELOPMENT_MODE

MODULE_ALLOWED_DEPENDENCIES = [
    'Pillow', 'qrcode', 'python-barcode', 'openpyxl', 'reportlab',
    'python-escpos', 'lxml', 'xmltodict', 'signxml', 'cryptography',
    'zeep', 'requests', 'websockets', 'python-dateutil', 'pytz',
    'phonenumbers', 'stripe', 'pandas', 'numpy', 'pyserial', 'pyusb',
    'evdev', 'email-validator', 'python-slugify', 'pydantic',
    'beautifulsoup4', 'PyPDF2'
]

MODULE_MAX_SIZE_MB = 50
MODULE_SIGNATURE_ALGORITHM = 'RSA-SHA256'
MODULE_SIGNATURE_KEY_SIZE = 4096

# Add modules to sys.path
if MODULES_DIR.exists() and str(MODULES_DIR) not in sys.path:
    sys.path.insert(0, str(MODULES_DIR))

# =============================================================================
# CLOUD API
# =============================================================================

CLOUD_API_URL = config('CLOUD_URL', default=config('CLOUD_BASE_URL', default=config('CLOUD_API_URL', default='https://erplora.com')))

# Cloud Sync (only relevant for web deployment)
HUB_JWT = config('HUB_JWT', default='')
CLOUD_SYNC_ENABLED = config('CLOUD_SYNC_ENABLED', default=str(DEPLOYMENT_MODE == 'web'), cast=bool)
CLOUD_SYNC_WEBSOCKET = config('CLOUD_SYNC_WEBSOCKET', default=str(DEPLOYMENT_MODE == 'web'), cast=bool)
HEARTBEAT_INTERVAL = config('HEARTBEAT_INTERVAL', default=60, cast=int)
COMMAND_POLL_INTERVAL = config('COMMAND_POLL_INTERVAL', default=30, cast=int)

# =============================================================================
# WEB DEPLOYMENT — SSO, CORS, WhiteNoise, cookies
# =============================================================================
# Activated when PARENT_DOMAIN is set (e.g., erplora.com)

PARENT_DOMAIN = config('PARENT_DOMAIN', default='') if DEPLOYMENT_MODE == 'web' else ''

if PARENT_DOMAIN:
    # ALLOWED_HOSTS
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

    # Session cookies — Hub uses separate cookie from Cloud
    SESSION_COOKIE_NAME = 'hubsessionid'
    SESSION_COOKIE_DOMAIN = None
    SESSION_COOKIE_SAMESITE = 'Lax'
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True

    # CSRF cookies
    CSRF_COOKIE_DOMAIN = None
    CSRF_COOKIE_SAMESITE = 'Lax'
    CSRF_COOKIE_SECURE = True
    CSRF_TRUSTED_ORIGINS = [
        f'https://{PARENT_DOMAIN}',
        f'https://*.{PARENT_DOMAIN}',
    ]

    # Language cookie
    LANGUAGE_COOKIE_SECURE = True

    # CORS
    CORS_BASE_DOMAINS = [
        d.strip() for d in config('CORS_BASE_DOMAINS', default=PARENT_DOMAIN).split(',') if d.strip()
    ]
    CORS_ALLOWED_ORIGIN_REGEXES = [
        rf'^https://.*\.{d.replace(".", r".")}$'
        for d in CORS_BASE_DOMAINS
    ]
    CORS_ALLOWED_ORIGIN_REGEXES += [
        rf'^https://{d.replace(".", r".")}$'
        for d in CORS_BASE_DOMAINS
    ]
    CORS_ALLOW_CREDENTIALS = True

    INSTALLED_APPS += ['corsheaders']

    # Middleware: CORS → Security → WhiteNoise → Session → ... → SSO
    MIDDLEWARE.insert(0, 'corsheaders.middleware.CorsMiddleware')
    MIDDLEWARE.insert(2, 'whitenoise.middleware.WhiteNoiseMiddleware')
    MIDDLEWARE.insert(4, 'apps.core.middleware.CloudSSOMiddleware')

    # Storage backends for web
    STORAGES = {
        "staticfiles": {
            "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
        },
    }
    if AWS_ACCESS_KEY_ID:
        STORAGES["default"] = {
            "BACKEND": "storages.backends.s3boto3.S3Boto3Storage",
        }

# =============================================================================
# DJANGO REST FRAMEWORK
# =============================================================================

REST_FRAMEWORK = {
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    'DEFAULT_PERMISSION_CLASSES': [
        'apps.core.api_base.IsAuthenticated',
    ],
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
    ],
    'DEFAULT_PARSER_CLASSES': [
        'rest_framework.parsers.JSONParser',
        'rest_framework.parsers.FormParser',
        'rest_framework.parsers.MultiPartParser',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
    'EXCEPTION_HANDLER': 'rest_framework.views.exception_handler',
}

# =============================================================================
# DRF-SPECTACULAR (SWAGGER/OPENAPI)
# =============================================================================

SPECTACULAR_SETTINGS = {
    'TITLE': 'ERPlora Hub API',
    'DESCRIPTION': '''
## ERPlora Hub REST API

API completa para gestionar el Hub de ERPlora:

- **Authentication**: Login con PIN o Cloud, setup de PIN, logout
- **Employees**: CRUD de empleados, reset de PIN
- **Configuration**: Configuración del Hub y tienda
- **Modules**: Gestión de modules, marketplace
- **System**: Health check, actualizaciones

### Autenticación

La API usa autenticación basada en sesión. Primero debes hacer login:

1. `POST /api/v1/auth/pin-login/` - Login con PIN local
2. `POST /api/v1/auth/cloud-login/` - Login con credenciales de Cloud

Después del login, las cookies de sesión se incluyen automáticamente en las peticiones.
    ''',
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
    'SWAGGER_UI_SETTINGS': {
        'deepLinking': True,
        'persistAuthorization': True,
        'displayOperationId': False,
        'filter': True,
    },
    'TAGS': [
        {'name': 'Authentication', 'description': 'Login, logout, PIN setup'},
        {'name': 'Employees', 'description': 'Employee/user management'},
        {'name': 'Configuration', 'description': 'Hub and store settings'},
        {'name': 'Modules', 'description': 'Module management'},
        {'name': 'Marketplace', 'description': 'Module marketplace'},
        {'name': 'System', 'description': 'Health check, updates, language'},
    ],
    'COMPONENT_SPLIT_REQUEST': True,
    'SWAGGER_UI_DIST': 'SIDECAR',
    'SWAGGER_UI_FAVICON_HREF': 'SIDECAR',
    'REDOC_DIST': 'SIDECAR',
}

# =============================================================================
# DJANGO MONEY
# =============================================================================

from config.currencies import CURRENCY_CHOICES, POPULAR_CURRENCY_CHOICES

DEFAULT_CURRENCY = "EUR"
CURRENCIES = tuple([code for code, _ in POPULAR_CURRENCY_CHOICES])

# =============================================================================
# LOGGING
# =============================================================================

LOGS_DIR = _ensure_dir(DATA_DIR / 'logs')

_log_handlers = ['console']
_log_config_handlers = {
    'console': {
        'level': 'DEBUG' if DEVELOPMENT_MODE else 'INFO',
        'class': 'logging.StreamHandler',
        'formatter': 'simple',
    },
}

# File logging only in local mode (Docker uses stdout) and only if dir exists
if DEPLOYMENT_MODE == 'local' and LOGS_DIR.exists():
    _log_handlers.append('file')
    _log_config_handlers['file'] = {
        'level': 'INFO',
        'class': 'logging.handlers.RotatingFileHandler',
        'filename': str(LOGS_DIR / 'hub.log'),
        'maxBytes': 10 * 1024 * 1024,  # 10 MB
        'backupCount': 5,
        'formatter': 'verbose',
    }

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '[{levelname}] {asctime} {module} {message}',
            'style': '{',
            'datefmt': '%Y-%m-%d %H:%M:%S',
        },
        'simple': {
            'format': '[{levelname}] {message}',
            'style': '{',
        },
    },
    'handlers': _log_config_handlers,
    'root': {
        'handlers': _log_handlers,
        'level': 'INFO',
    },
    'loggers': {
        'django': {
            'handlers': _log_handlers,
            'level': 'INFO',
            'propagate': False,
        },
        'apps': {
            'handlers': _log_handlers,
            'level': 'DEBUG' if DEVELOPMENT_MODE else 'INFO',
            'propagate': False,
        },
    },
}

# =============================================================================
# DJANGO COMPONENTS
# =============================================================================

COMPONENTS = {
    "dirs": [
        BASE_DIR / "apps" / "ui" / "components",
    ],
    "autodiscover": True,
    "libraries": [],
    "template_cache_size": 128,
    "context_behavior": "django",
}

# =============================================================================
# DJICONS
# =============================================================================

DJICONS = {
    "DEFAULT_NAMESPACE": "ion",
    "ICON_DIRS": {
        "ion": BASE_DIR / "static" / "icons" / "ionicons",
    },
    "PACKS": [],
    "MISSING_ICON_SILENT": False,
    "CACHE_TIMEOUT": 86400,
    "DEFAULT_CLASS": "icon",
    "DEFAULT_FILL": "currentColor",
}

# =============================================================================
# DEV TOOLS (only when DEBUG=True)
# =============================================================================

if DEBUG and DEPLOYMENT_MODE == 'local':
    DEBUG_TOOLBAR_ENABLED = os.environ.get('DEBUG_TOOLBAR', 'false').lower() == 'true'

    if DEBUG_TOOLBAR_ENABLED:
        INSTALLED_APPS += ['debug_toolbar']
        MIDDLEWARE = ['debug_toolbar.middleware.DebugToolbarMiddleware'] + MIDDLEWARE
        INTERNAL_IPS = ['127.0.0.1', 'localhost']

        def show_toolbar_callback(request):
            if not DEBUG:
                return False
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return False
            if 'application/json' in request.headers.get('Accept', ''):
                return False
            if 'application/json' in request.headers.get('Content-Type', ''):
                return False
            if request.path.startswith('/api/'):
                return False
            if request.path.startswith('/verify-pin/'):
                return False
            return True

        DEBUG_TOOLBAR_CONFIG = {
            'SHOW_TOOLBAR_CALLBACK': show_toolbar_callback,
        }

    # Browser auto-reload
    try:
        import django_browser_reload  # noqa: F401
        INSTALLED_APPS += ['django_browser_reload']
        MIDDLEWARE += ['django_browser_reload.middleware.BrowserReloadMiddleware']
    except ImportError:
        pass

# =============================================================================
# MODULE LOADING — Discover and load modules with dependency resolution
# =============================================================================


def load_modules():
    """Load active modules from MODULES_DIR into INSTALLED_APPS with dependency resolution."""
    import json
    import re

    if not MODULES_DIR.exists():
        return

    # 1. Discover enabled modules
    enabled_ids = set()
    for module_dir in MODULES_DIR.iterdir():
        if not module_dir.is_dir():
            continue
        if module_dir.name.startswith('.') or module_dir.name.startswith('_'):
            continue
        enabled_ids.add(module_dir.name)

    # 2. Read dependencies for each module
    deps = {}
    for mid in enabled_ids:
        raw_deps = []
        module_py_path = MODULES_DIR / mid / 'module.py'
        if module_py_path.exists():
            try:
                import importlib.util
                spec = importlib.util.spec_from_file_location(f"{mid}.module", module_py_path)
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                raw_deps = getattr(mod, 'DEPENDENCIES', [])
            except Exception:
                pass

        if not raw_deps:
            module_json = MODULES_DIR / mid / 'module.json'
            if module_json.exists():
                try:
                    with open(module_json, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    deps_value = data.get('dependencies', data.get('requires', []))
                    if isinstance(deps_value, dict):
                        raw_deps = deps_value.get('modules', [])
                    else:
                        raw_deps = deps_value
                except Exception:
                    pass

        deps[mid] = [re.split(r'[><=!]', d)[0].strip() for d in raw_deps if d]

    # 3. Remove modules with unmet dependencies (cascading)
    to_load = set(enabled_ids)
    changed = True
    while changed:
        changed = False
        for mid in list(to_load):
            missing = [d for d in deps.get(mid, []) if d not in to_load]
            if missing:
                to_load.discard(mid)
                print(f"[SETTINGS] Module '{mid}' skipped: missing dependencies {missing}")
                changed = True

    # 4. Topological sort
    ordered = []
    visited = set()

    def visit(mid):
        if mid in visited or mid not in to_load:
            return
        visited.add(mid)
        for dep in deps.get(mid, []):
            visit(dep)
        ordered.append(mid)
    for mid in sorted(to_load):
        visit(mid)

    # 5. Add to INSTALLED_APPS
    for mid in ordered:
        if mid not in INSTALLED_APPS:
            INSTALLED_APPS.append(mid)
            print(f"[SETTINGS] Loaded module: {mid}")


def load_module_templates():
    """Add module template directories to Django."""
    template_dirs = list(TEMPLATES[0]['DIRS'])

    if MODULES_DIR.exists():
        for module_dir in MODULES_DIR.iterdir():
            if module_dir.is_dir() and (module_dir / 'templates').exists():
                template_dirs.append(module_dir / 'templates')

    TEMPLATES[0]['DIRS'] = template_dirs


# Load modules now
load_modules()
load_module_templates()

# =============================================================================
# STARTUP INFO
# =============================================================================

_db_type = 'PostgreSQL' if DATABASE_URL else 'SQLite'
_db_name = DATABASES['default'].get('NAME', DATABASE_URL.split('/')[-1] if DATABASE_URL else 'unknown')
print(f"[HUB] {HUB_NAME} ({HUB_ID}) — {DEPLOYMENT_MODE}")
print(f"[HUB] Database: {_db_type} — {_db_name}")
print(f"[HUB] Data: {DATA_DIR}")
print(f"[HUB] Modules: {MODULES_DIR}")
