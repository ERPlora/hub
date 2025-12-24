"""
ERPlora Hub - Local Development Settings

Configuración para desarrollo local.
Usa DataPaths para rutas consistentes con producción.
Modules desde ./modules/ del proyecto (para desarrollo).
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

# Use production Cloud API for local development
CLOUD_API_URL = 'https://erplora.com'

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

# Module data
MODULE_DATA_ROOT = DATA_DIR / 'module_data'
MODULE_DATA_ROOT.mkdir(parents=True, exist_ok=True)
MODULE_MEDIA_ROOT = MEDIA_ROOT / 'modules'
MODULE_MEDIA_ROOT.mkdir(parents=True, exist_ok=True)

# =============================================================================
# MODULES - Same as production (from DataPaths)
# =============================================================================
# Uses ~/Library/.../ERPloraHub/modules/ (same as desktop builds)
# A symlink at ./modules -> real location makes development easier

MODULES_DIR = _paths.modules_dir
MODULES_ROOT = MODULES_DIR
MODULE_DISCOVERY_PATHS = [MODULES_DIR]

# Add modules to sys.path
if MODULES_DIR.exists() and str(MODULES_DIR) not in sys.path:
    sys.path.insert(0, str(MODULES_DIR))

# =============================================================================
# SYMLINKS - Create convenience symlinks in ERPlora root (parent of hub/)
# =============================================================================
# Creates symlinks for easy access during development:
#   ERPlora/hub_data -> ~/Library/Application Support/ERPloraHub/
#   ERPlora/hub_modules -> ~/Library/Application Support/ERPloraHub/modules/

def _create_dev_symlinks():
    """Create symlinks in ERPlora root for development convenience."""
    import os

    # ERPlora root is parent of hub/
    erplora_root = BASE_DIR.parent

    # Symlink: ERPlora/hub_data -> DATA_DIR
    data_link = erplora_root / 'hub_data'
    if not data_link.exists():
        try:
            os.symlink(DATA_DIR, data_link)
            print(f"[LOCAL] Created symlink: hub_data -> {DATA_DIR}")
        except (OSError, FileExistsError):
            pass  # Symlink already exists or can't create

    # Symlink: ERPlora/hub_modules -> MODULES_DIR
    modules_link = erplora_root / 'hub_modules'
    if not modules_link.exists():
        try:
            os.symlink(MODULES_DIR, modules_link)
            print(f"[LOCAL] Created symlink: hub_modules -> {MODULES_DIR}")
        except (OSError, FileExistsError):
            pass

_create_dev_symlinks()

# =============================================================================
# CLOUD SYNC - Disabled for local development
# =============================================================================

CLOUD_SYNC_ENABLED = False
CLOUD_SYNC_WEBSOCKET = False

# =============================================================================
# SECURITY - Relaxed for local development
# =============================================================================

ALLOWED_HOSTS = ['127.0.0.1', 'localhost', '*']
CSRF_COOKIE_SECURE = False

# =============================================================================
# MODULE SECURITY - Relaxed for development
# =============================================================================

REQUIRE_MODULE_SIGNATURE = False
MODULE_AUTO_RELOAD = True
MODULE_STRICT_VALIDATION = False

# =============================================================================
# RE-LOAD MODULES (override base.py loading)
# =============================================================================

# Clear modules loaded by base.py and reload from local modules dir
def reload_local_modules():
    """Reload modules from local ./modules/ directory"""
    global INSTALLED_APPS

    # Remove any modules that were loaded from wrong directory
    INSTALLED_APPS = [app for app in INSTALLED_APPS if not (
        isinstance(app, str) and
        not app.startswith('django') and
        not app.startswith('apps.') and
        app not in ['djmoney', 'django_htmx']
    )]

    if not MODULES_DIR.exists():
        return

    for module_dir in MODULES_DIR.iterdir():
        if not module_dir.is_dir():
            continue
        # Skip disabled modules (start with _ or .)
        if module_dir.name.startswith('.') or module_dir.name.startswith('_'):
            continue

        if module_dir.name not in INSTALLED_APPS:
            INSTALLED_APPS.append(module_dir.name)
            print(f"[LOCAL] Loaded module: {module_dir.name}")


reload_local_modules()

# Add module templates (keeping global templates directory)
if MODULES_DIR.exists():
    # Start with existing global templates directory
    template_dirs = [str(d) for d in TEMPLATES[0]['DIRS']]

    for module_dir in MODULES_DIR.iterdir():
        if module_dir.is_dir() and (module_dir / 'templates').exists():
            template_dirs.append(str(module_dir / 'templates'))

    TEMPLATES[0]['DIRS'] = template_dirs

print(f"[LOCAL] Development mode")
print(f"[LOCAL] Modules: {MODULES_DIR}")
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
