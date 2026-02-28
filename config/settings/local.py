"""
ERPlora Hub - Local Development Settings

Local development configuration.
Uses DataPaths for consistent paths with production.
Modules loaded from external directory (for development).
"""

from .base import *
from pathlib import Path
import os
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

# CLOUD_API_URL defaults to https://erplora.com (in base.py), overridable via .env

# =============================================================================
# PATHS - configurable via .env, fallback to DataPaths auto-detection
# =============================================================================

_paths = get_data_paths()
DATA_DIR = _paths.base_dir

# Database
_db_path_env = config('DATABASE_PATH', default='')
if _db_path_env:
    DATABASES['default']['NAME'] = Path(_db_path_env)
    DATABASE_DIR = Path(_db_path_env).parent
else:
    DATABASE_DIR = _paths.database_dir
    DATABASES['default']['NAME'] = _paths.database_path

# Modules
_modules_dir_env = config('MODULES_DIR', default='')
if _modules_dir_env:
    MODULES_DIR = Path(_modules_dir_env)
else:
    MODULES_DIR = _paths.modules_dir
MODULES_ROOT = MODULES_DIR
MODULE_DISCOVERY_PATHS = [MODULES_DIR]

# Ensure all directories exist
DATABASE_DIR.mkdir(parents=True, exist_ok=True)
MODULES_DIR.mkdir(parents=True, exist_ok=True)

# Media, Logs, Backups, Reports
MEDIA_ROOT = _paths.media_dir
LOGS_DIR = _paths.logs_dir
LOGGING['handlers']['file']['filename'] = str(LOGS_DIR / 'hub.log')
BACKUPS_DIR = _paths.backups_dir
REPORTS_DIR = _paths.reports_dir

# Module data
MODULE_DATA_ROOT = DATA_DIR / 'module_data'
MODULE_DATA_ROOT.mkdir(parents=True, exist_ok=True)
MODULE_MEDIA_ROOT = MEDIA_ROOT / 'modules'
MODULE_MEDIA_ROOT.mkdir(parents=True, exist_ok=True)

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
# LOAD MODULES (delegates to base.py load_modules with full dependency resolution)
# =============================================================================

load_modules(MODULES_DIR)
load_module_templates(MODULES_DIR)

print(f"[LOCAL] Development mode")
print(f"[LOCAL] Modules: {MODULES_DIR}")
print(f"[LOCAL] Data: {DATA_DIR}")

# =============================================================================
# DJANGO DEBUG TOOLBAR
# =============================================================================
# Disabled by default. Set DEBUG_TOOLBAR=true in .env to enable.

DEBUG_TOOLBAR_ENABLED = os.environ.get('DEBUG_TOOLBAR', 'false').lower() == 'true'

if DEBUG_TOOLBAR_ENABLED:
    INSTALLED_APPS += ['debug_toolbar']

    MIDDLEWARE = [
        'debug_toolbar.middleware.DebugToolbarMiddleware',
    ] + MIDDLEWARE

    INTERNAL_IPS = [
        '127.0.0.1',
        'localhost',
    ]

    def show_toolbar_callback(request):
        """Show debug toolbar only for HTML requests, not AJAX/JSON."""
        if not DEBUG:
            return False
        # Skip for AJAX requests
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return False
        # Skip for JSON requests
        if 'application/json' in request.headers.get('Accept', ''):
            return False
        if 'application/json' in request.headers.get('Content-Type', ''):
            return False
        # Skip for API endpoints
        if request.path.startswith('/api/'):
            return False
        # Skip for verify-pin endpoint
        if request.path.startswith('/verify-pin/'):
            return False
        return True

    DEBUG_TOOLBAR_CONFIG = {
        'SHOW_TOOLBAR_CALLBACK': show_toolbar_callback,
    }

    print(f"[LOCAL] Debug Toolbar: ENABLED")

# =============================================================================
# DJANGO BROWSER RELOAD (auto-refresh on file changes)
# =============================================================================

INSTALLED_APPS += ['django_browser_reload']

MIDDLEWARE += ['django_browser_reload.middleware.BrowserReloadMiddleware']
