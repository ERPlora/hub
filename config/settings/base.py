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
    'djmoney',
    'django_htmx',
    # Hub apps
    'apps.accounts.apps.AccountsConfig',
    'apps.configuration.apps.ConfigurationConfig',
    'apps.sync.apps.SyncConfig',
    'apps.core.apps.CoreConfig',
    'apps.plugins_runtime',
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
    'apps.core.middleware.plugin_middleware_manager.PluginMiddlewareManager',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.template.context_processors.i18n',
                'django.template.context_processors.static',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'apps.core.context_processors.cloud_url',
                'apps.core.context_processors.plugin_menu_items',
                'apps.core.context_processors.hub_config_context',
                'apps.core.context_processors.deployment_config',
                'apps.configuration.context_processors.global_config',
            ],
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

CLOUD_API_URL = config('CLOUD_API_URL', default='https://int.erplora.com')

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
# PLUGIN SYSTEM
# =============================================================================

# Detect frozen (PyInstaller) vs development
DEVELOPMENT_MODE = not getattr(sys, 'frozen', False) and config('ERPLORA_DEV_MODE', default='true', cast=bool)

# Plugin paths (set per environment)
PLUGINS_DIR = BASE_DIR / 'plugins'
PLUGINS_ROOT = PLUGINS_DIR

# Plugin discovery paths (extended per environment)
PLUGIN_DISCOVERY_PATHS = [PLUGINS_DIR]

# Plugin security
REQUIRE_PLUGIN_SIGNATURE = not DEVELOPMENT_MODE
PLUGIN_AUTO_RELOAD = DEVELOPMENT_MODE
PLUGIN_STRICT_VALIDATION = not DEVELOPMENT_MODE

# Plugin data directories
PLUGIN_DATA_ROOT = BASE_DIR / 'plugin_data'
PLUGIN_MEDIA_ROOT = BASE_DIR / 'media' / 'plugins'

# Plugin allowed dependencies
PLUGIN_ALLOWED_DEPENDENCIES = [
    'Pillow', 'qrcode', 'python-barcode', 'openpyxl', 'reportlab',
    'python-escpos', 'lxml', 'xmltodict', 'signxml', 'cryptography',
    'zeep', 'requests', 'websockets', 'python-dateutil', 'pytz',
    'phonenumbers', 'stripe', 'pandas', 'numpy', 'pyserial', 'pyusb',
    'evdev', 'pywinusb', 'email-validator', 'python-slugify', 'pydantic',
    'beautifulsoup4', 'PyPDF2'
]

PLUGIN_MAX_SIZE_MB = 50
PLUGIN_SIGNATURE_ALGORITHM = 'RSA-SHA256'
PLUGIN_SIGNATURE_KEY_SIZE = 4096

# =============================================================================
# DJANGO MONEY
# =============================================================================

CURRENCIES = ('USD', 'EUR', 'GBP', 'JPY', 'CNY', 'MXN', 'CAD', 'AUD', 'BRL', 'ARS', 'COP', 'CLP', 'PEN', 'CRC')
CURRENCY_CHOICES = [
    ('USD', 'US Dollar ($)'),
    ('EUR', 'Euro (€)'),
    ('GBP', 'British Pound (£)'),
    ('JPY', 'Japanese Yen (¥)'),
    ('CNY', 'Chinese Yuan (¥)'),
    ('MXN', 'Mexican Peso ($)'),
    ('CAD', 'Canadian Dollar ($)'),
    ('AUD', 'Australian Dollar ($)'),
    ('BRL', 'Brazilian Real (R$)'),
    ('ARS', 'Argentine Peso ($)'),
    ('COP', 'Colombian Peso ($)'),
    ('CLP', 'Chilean Peso ($)'),
    ('PEN', 'Peruvian Sol (S/)'),
    ('CRC', 'Costa Rican Colón (₡)'),
]

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
# AUTO-LOAD PLUGINS (common logic)
# =============================================================================

def load_plugins():
    """Load active plugins from PLUGINS_DIR into INSTALLED_APPS"""
    import json

    if not PLUGINS_DIR.exists():
        return

    for plugin_dir in PLUGINS_DIR.iterdir():
        if not plugin_dir.is_dir():
            continue
        # Skip disabled plugins (start with _ or .)
        if plugin_dir.name.startswith('.') or plugin_dir.name.startswith('_'):
            continue

        INSTALLED_APPS.append(plugin_dir.name)
        print(f"[SETTINGS] Auto-loaded plugin: {plugin_dir.name}")


def load_plugin_templates():
    """Add plugin template directories to Django"""
    template_dirs = []

    if PLUGINS_DIR.exists():
        for plugin_dir in PLUGINS_DIR.iterdir():
            if plugin_dir.is_dir() and (plugin_dir / 'templates').exists():
                template_dirs.append(plugin_dir / 'templates')

    if template_dirs:
        TEMPLATES[0]['DIRS'] = template_dirs


# Load plugins on import
load_plugins()
load_plugin_templates()

# Add plugins to sys.path
if PLUGINS_DIR.exists():
    sys.path.insert(0, str(PLUGINS_DIR))
