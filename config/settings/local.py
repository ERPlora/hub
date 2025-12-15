"""
ERPlora Hub - Local Development Settings

Configuración para desarrollo local.
Usa DataPaths para rutas consistentes con producción.
Plugins desde ./plugins/ del proyecto (para desarrollo).
"""

from .base import *
from pathlib import Path
import sys
from config.paths import get_data_paths

# =============================================================================
# DEPLOYMENT
# =============================================================================

DEPLOYMENT_MODE = 'local'
DEBUG = True
OFFLINE_ENABLED = True
CLOUD_SYNC_REQUIRED = False
DEVELOPMENT_MODE = True

# =============================================================================
# PATHS - Using DataPaths (same as production)
# =============================================================================

# Get all paths from DataPaths (auto-detects OS)
_paths = get_data_paths()
DATA_DIR = _paths.base_dir

# Database - same location as production
DATABASE_DIR = _paths.database_dir
DATABASES['default']['NAME'] = _paths.database_path

# Media
MEDIA_ROOT = _paths.media_dir

# Logs
LOGS_DIR = _paths.logs_dir
LOGGING['handlers']['file']['filename'] = str(LOGS_DIR / 'hub.log')

# Backups & Reports
BACKUPS_DIR = _paths.backups_dir
REPORTS_DIR = _paths.reports_dir

# Plugin data
PLUGIN_DATA_ROOT = DATA_DIR / 'plugin_data'
PLUGIN_DATA_ROOT.mkdir(parents=True, exist_ok=True)
PLUGIN_MEDIA_ROOT = MEDIA_ROOT / 'plugins'
PLUGIN_MEDIA_ROOT.mkdir(parents=True, exist_ok=True)

# =============================================================================
# PLUGINS - Override: use project ./plugins/ for development
# =============================================================================
# En desarrollo queremos editar plugins directamente en el repo
# En producción (desktop_*) usarían _paths.plugins_dir

PLUGINS_DIR = BASE_DIR / 'plugins'
PLUGINS_ROOT = PLUGINS_DIR
PLUGIN_DISCOVERY_PATHS = [PLUGINS_DIR]

# Add plugins to sys.path
if PLUGINS_DIR.exists() and str(PLUGINS_DIR) not in sys.path:
    sys.path.insert(0, str(PLUGINS_DIR))

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

# Add plugin templates (keeping global templates directory)
if PLUGINS_DIR.exists():
    # Start with existing global templates directory
    template_dirs = [str(d) for d in TEMPLATES[0]['DIRS']]

    for plugin_dir in PLUGINS_DIR.iterdir():
        if plugin_dir.is_dir() and (plugin_dir / 'templates').exists():
            template_dirs.append(str(plugin_dir / 'templates'))

    TEMPLATES[0]['DIRS'] = template_dirs

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
