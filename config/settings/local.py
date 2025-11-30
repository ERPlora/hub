"""
ERPlora Hub - Local Development Settings

Configuración para desarrollo local.
Plugins se cargan desde el proyecto (./plugins/)
Base de datos en ubicación específica del OS.
"""

from .base import *
from pathlib import Path
import sys

# =============================================================================
# DEPLOYMENT
# =============================================================================

DEPLOYMENT_MODE = 'local'
DEBUG = True
OFFLINE_ENABLED = True
CLOUD_SYNC_REQUIRED = False
DEVELOPMENT_MODE = True

# =============================================================================
# PATHS - Local development
# =============================================================================

# Plugins SIEMPRE desde el proyecto en local
PLUGINS_DIR = BASE_DIR / 'plugins'
PLUGINS_ROOT = PLUGINS_DIR
PLUGIN_DISCOVERY_PATHS = [PLUGINS_DIR]

# Add plugins to sys.path
if PLUGINS_DIR.exists() and str(PLUGINS_DIR) not in sys.path:
    sys.path.insert(0, str(PLUGINS_DIR))

# Data directory based on OS
import platform
if platform.system() == 'Darwin':
    DATA_DIR = Path.home() / 'Library' / 'Application Support' / 'ERPloraHub'
elif platform.system() == 'Windows':
    DATA_DIR = Path.home() / 'AppData' / 'Local' / 'ERPloraHub'
else:
    DATA_DIR = Path.home() / '.local' / 'share' / 'erplora-hub'

DATA_DIR.mkdir(parents=True, exist_ok=True)

# Database
DATABASE_DIR = DATA_DIR / 'db'
DATABASE_DIR.mkdir(parents=True, exist_ok=True)
DATABASES['default']['NAME'] = DATABASE_DIR / 'db.sqlite3'

# Media
MEDIA_ROOT = DATA_DIR / 'media'
MEDIA_ROOT.mkdir(parents=True, exist_ok=True)

# Logs
LOGS_DIR = DATA_DIR / 'logs'
LOGS_DIR.mkdir(parents=True, exist_ok=True)
LOGGING['handlers']['file']['filename'] = str(LOGS_DIR / 'hub.log')

# Plugin data (still in DATA_DIR for persistence)
PLUGIN_DATA_ROOT = DATA_DIR / 'plugin_data'
PLUGIN_DATA_ROOT.mkdir(parents=True, exist_ok=True)
PLUGIN_MEDIA_ROOT = MEDIA_ROOT / 'plugins'
PLUGIN_MEDIA_ROOT.mkdir(parents=True, exist_ok=True)

# =============================================================================
# SECURITY - Relaxed for local development
# =============================================================================

ALLOWED_HOSTS = ['127.0.0.1', 'localhost', '*']
CSRF_COOKIE_SECURE = False

# =============================================================================
# PLUGIN SECURITY - Relaxed for development
# =============================================================================

REQUIRE_PLUGIN_SIGNATURE = False
PLUGIN_AUTO_RELOAD = True
PLUGIN_STRICT_VALIDATION = False

# =============================================================================
# RE-LOAD PLUGINS (override base.py loading)
# =============================================================================

# Clear plugins loaded by base.py and reload from local plugins dir
def reload_local_plugins():
    """Reload plugins from local ./plugins/ directory"""
    global INSTALLED_APPS

    # Remove any plugins that were loaded from wrong directory
    INSTALLED_APPS = [app for app in INSTALLED_APPS if not (
        isinstance(app, str) and
        not app.startswith('django') and
        not app.startswith('apps.') and
        app not in ['djmoney', 'django_htmx']
    )]

    if not PLUGINS_DIR.exists():
        return

    for plugin_dir in PLUGINS_DIR.iterdir():
        if not plugin_dir.is_dir():
            continue
        # Skip disabled plugins (start with _ or .)
        if plugin_dir.name.startswith('.') or plugin_dir.name.startswith('_'):
            continue

        if plugin_dir.name not in INSTALLED_APPS:
            INSTALLED_APPS.append(plugin_dir.name)
            print(f"[LOCAL] Loaded plugin: {plugin_dir.name}")


reload_local_plugins()

# Add plugin templates
if PLUGINS_DIR.exists():
    plugin_template_dirs = []
    for plugin_dir in PLUGINS_DIR.iterdir():
        if plugin_dir.is_dir() and (plugin_dir / 'templates').exists():
            plugin_template_dirs.append(str(plugin_dir / 'templates'))

    if plugin_template_dirs:
        TEMPLATES[0]['DIRS'] = plugin_template_dirs

print(f"[LOCAL] Development mode")
print(f"[LOCAL] Plugins: {PLUGINS_DIR}")
print(f"[LOCAL] Data: {DATA_DIR}")

# =============================================================================
# DJANGO DEBUG TOOLBAR
# =============================================================================

INSTALLED_APPS += ['debug_toolbar']

MIDDLEWARE = [
    'debug_toolbar.middleware.DebugToolbarMiddleware',
] + MIDDLEWARE

INTERNAL_IPS = [
    '127.0.0.1',
    'localhost',
]

DEBUG_TOOLBAR_CONFIG = {
    'SHOW_TOOLBAR_CALLBACK': lambda request: DEBUG,
}
