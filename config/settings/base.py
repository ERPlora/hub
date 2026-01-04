"""
ERPlora Hub - Base Settings

Configuración común para todos los entornos.
Los archivos específicos (desktop_*.py, web.py) importan este y añaden overrides.
"""

import sys
import secrets
from pathlib import Path
from decouple import config

# =============================================================================
# PATHS
# =============================================================================

BASE_DIR = Path(__file__).resolve().parent.parent.parent

# =============================================================================
# SECURITY
# =============================================================================


def get_or_create_secret_key():
    """
    Get SECRET_KEY from environment or generate one automatically.
    For Docker deployments, generates and persists to .secret_key file.
    """
    # First, try environment variable
    secret_key = config('SECRET_KEY', default='')
    if secret_key:
        return secret_key

    # For Docker: generate and persist to file
    secret_file = Path('/app/.secret_key')
    if not secret_file.parent.exists():
        # Desktop: use local file
        secret_file = BASE_DIR / '.secret_key'

    if secret_file.exists():
        return secret_file.read_text().strip()

    # Generate new key
    new_key = secrets.token_urlsafe(50)
    try:
        secret_file.write_text(new_key)
        print(f"[SECURITY] Generated new SECRET_KEY: {secret_file}")
    except PermissionError:
        print(f"[SECURITY] Warning: Could not persist SECRET_KEY to {secret_file}")

    return new_key


SECRET_KEY = get_or_create_secret_key()

# Defaults - overridden per environment
DEBUG = False
ALLOWED_HOSTS = ['127.0.0.1', 'localhost']

# CSRF defaults (relaxed for desktop, strict for web)
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
    'djicons',  # SVG icons for Django templates (must be before django_components)
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
    # Hub apps - UI Components
    'apps.ui.apps.UiConfig',
    # Hub apps - Auth
    'apps.auth.login.apps.AuthLoginConfig',
    # Hub apps - Main
    'apps.main.index.apps.MainIndexConfig',
    'apps.main.files.apps.FilesConfig',
    'apps.main.settings.apps.MainSettingsConfig',
    'apps.main.employees.apps.MainEmployeesConfig',
    'apps.main.setup.apps.SetupConfig',
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
            BASE_DIR / 'templates',  # Global templates (base.html)
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
                'djicons.templatetags.djicons',  # SVG icons
            ],
            'libraries': {
                'djicons': 'djicons.templatetags.djicons',
            },
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

# =============================================================================
# DATABASE (default SQLite - overridden per environment)
# =============================================================================

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

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

# Language cookie settings (for auto-detection and persistence)
# Middleware priority: 1. LocaleMiddleware checks URL (not used)
# 2. Session, 3. Cookie, 4. Browser Accept-Language, 5. LANGUAGE_CODE
LANGUAGE_COOKIE_NAME = 'django_language'
LANGUAGE_COOKIE_AGE = 31536000  # 1 year
LANGUAGE_COOKIE_SECURE = False  # Hub runs locally
LANGUAGE_COOKIE_SAMESITE = 'Lax'

# =============================================================================
# STATIC & MEDIA FILES
# =============================================================================

STATIC_URL = 'static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

MEDIA_URL = 'media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# =============================================================================
# CLOUD API
# =============================================================================

# Cloud base URL (API endpoints are at /api/...)
# Priority: CLOUD_URL > CLOUD_BASE_URL > CLOUD_API_URL (legacy)
CLOUD_API_URL = config('CLOUD_URL', default=config('CLOUD_BASE_URL', default=config('CLOUD_API_URL', default='https://int.erplora.com')))

# =============================================================================
# DEPLOYMENT MODE (overridden per environment)
# =============================================================================

DEPLOYMENT_MODE = 'desktop'  # desktop, web, demo
OFFLINE_ENABLED = True
CLOUD_SYNC_REQUIRED = False
DEMO_MODE = False

# =============================================================================
# HUB CONFIGURATION
# =============================================================================

HUB_LOCAL_PORT = config('HUB_LOCAL_PORT', default=8001, cast=int)
HUB_VERSION = "1.0.0"

# =============================================================================
# MODULE SYSTEM
# =============================================================================

# Detect frozen (PyInstaller) vs development
DEVELOPMENT_MODE = not getattr(sys, 'frozen', False) and config('ERPLORA_DEV_MODE', default='true', cast=bool)

# Module paths - auto-detected via DataPaths (Docker vs Desktop)
# Can be overridden via MODULES_DIR env var
from config.paths import get_modules_dir
_modules_dir_env = config('MODULES_DIR', default='')
if _modules_dir_env:
    MODULES_DIR = Path(_modules_dir_env)
    MODULES_DIR.mkdir(parents=True, exist_ok=True)
else:
    MODULES_DIR = get_modules_dir()

MODULES_ROOT = MODULES_DIR

# Module discovery paths
MODULE_DISCOVERY_PATHS = [MODULES_DIR]

# Module security
REQUIRE_MODULE_SIGNATURE = not DEVELOPMENT_MODE
MODULE_AUTO_RELOAD = DEVELOPMENT_MODE
MODULE_STRICT_VALIDATION = not DEVELOPMENT_MODE

# Module data directories
MODULE_DATA_ROOT = BASE_DIR / 'module_data'
MODULE_MEDIA_ROOT = BASE_DIR / 'media' / 'modules'

# Module allowed dependencies
MODULE_ALLOWED_DEPENDENCIES = [
    'Pillow', 'qrcode', 'python-barcode', 'openpyxl', 'reportlab',
    'python-escpos', 'lxml', 'xmltodict', 'signxml', 'cryptography',
    'zeep', 'requests', 'websockets', 'python-dateutil', 'pytz',
    'phonenumbers', 'stripe', 'pandas', 'numpy', 'pyserial', 'pyusb',
    'evdev', 'pywinusb', 'email-validator', 'python-slugify', 'pydantic',
    'beautifulsoup4', 'PyPDF2'
]

MODULE_MAX_SIZE_MB = 50
MODULE_SIGNATURE_ALGORITHM = 'RSA-SHA256'
MODULE_SIGNATURE_KEY_SIZE = 4096

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
    # Use sidecar for static files (Swagger UI CSS/JS)
    'SWAGGER_UI_DIST': 'SIDECAR',
    'SWAGGER_UI_FAVICON_HREF': 'SIDECAR',
    'REDOC_DIST': 'SIDECAR',
}

# =============================================================================
# DJANGO MONEY
# =============================================================================

# Import all currencies from django-money (308 ISO 4217 currencies)
from config.currencies import CURRENCY_CHOICES, POPULAR_CURRENCY_CHOICES

# Default currency for Hub
DEFAULT_CURRENCY = "EUR"

# Allowed currencies (use popular for UI selects)
CURRENCIES = tuple([code for code, _ in POPULAR_CURRENCY_CHOICES])

# =============================================================================
# LOGGING (base config - paths set per environment)
# =============================================================================

LOGS_DIR = BASE_DIR / 'logs'
LOGS_DIR.mkdir(parents=True, exist_ok=True)

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
    'handlers': {
        'file': {
            'level': 'INFO',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': str(LOGS_DIR / 'hub.log'),
            'maxBytes': 10 * 1024 * 1024,  # 10 MB
            'backupCount': 5,
            'formatter': 'verbose',
        },
        'console': {
            'level': 'DEBUG' if DEVELOPMENT_MODE else 'INFO',
            'class': 'logging.StreamHandler',
            'formatter': 'simple',
        },
    },
    'root': {
        'handlers': ['console', 'file'],
        'level': 'INFO',
    },
    'loggers': {
        'django': {
            'handlers': ['console', 'file'],
            'level': 'INFO',
            'propagate': False,
        },
        'apps': {
            'handlers': ['console', 'file'],
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
    "context_behavior": "django",  # or "isolated"
}

# =============================================================================
# DJICONS - SVG Icons for Django Templates
# =============================================================================

DJICONS = {
    "DEFAULT_NAMESPACE": "ion",  # Ionicons as default (compatible with existing <ion-icon>)
    "ICON_DIRS": {
        "ion": BASE_DIR / "static" / "ionicons" / "dist" / "svg",
    },
    "PACKS": [],  # Disable bundled packs, use ICON_DIRS instead
    "MISSING_ICON_SILENT": False,  # Show error in development
    "CACHE_TIMEOUT": 86400,  # 24 hours
    "DEFAULT_SIZE": 20,  # Default icon size in pixels (matches ion-icon default)
    "DEFAULT_CLASS": "icon",  # Base CSS class for all icons
}

# =============================================================================
# AUTO-LOAD MODULES (common logic)
# =============================================================================

def load_modules():
    """Load active modules from MODULES_DIR into INSTALLED_APPS"""
    import json

    if not MODULES_DIR.exists():
        return

    for module_dir in MODULES_DIR.iterdir():
        if not module_dir.is_dir():
            continue
        # Skip disabled modules (start with _ or .)
        if module_dir.name.startswith('.') or module_dir.name.startswith('_'):
            continue

        INSTALLED_APPS.append(module_dir.name)
        print(f"[SETTINGS] Auto-loaded module: {module_dir.name}")


def load_module_templates():
    """Add module template directories to Django"""
    # Start with the existing global templates directory
    template_dirs = list(TEMPLATES[0]['DIRS'])

    if MODULES_DIR.exists():
        for module_dir in MODULES_DIR.iterdir():
            if module_dir.is_dir() and (module_dir / 'templates').exists():
                template_dirs.append(module_dir / 'templates')

    # Update DIRS with all template directories
    TEMPLATES[0]['DIRS'] = template_dirs


# NOTE: load_modules() and load_module_templates() are called by each
# environment-specific settings file AFTER MODULES_DIR is properly set.
# Do NOT call them here in base.py.
