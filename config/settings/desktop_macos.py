"""
ERPlora Hub - macOS Desktop Settings

Configuración para macOS desktop (PyInstaller .app)
Datos en: /Users/<user>/Library/Application Support/ERPloraHub/
"""

from .base import *
from pathlib import Path

# =============================================================================
# DEPLOYMENT
# =============================================================================

DEPLOYMENT_MODE = 'desktop'
DEBUG = config('DEBUG', default=True, cast=bool)
OFFLINE_ENABLED = True
CLOUD_SYNC_REQUIRED = False

# =============================================================================
# PATHS - macOS specific
# =============================================================================

# ~/Library/Application Support/ERPloraHub
DATA_DIR = Path.home() / 'Library' / 'Application Support' / 'ERPloraHub'
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Database
DATABASE_DIR = DATA_DIR / 'db'
DATABASE_DIR.mkdir(parents=True, exist_ok=True)
DATABASES['default']['NAME'] = DATABASE_DIR / 'db.sqlite3'

# Media
MEDIA_ROOT = DATA_DIR / 'media'
MEDIA_ROOT.mkdir(parents=True, exist_ok=True)

# Plugins - uses base.py config (PLUGINS_DIR from DataPaths)
# In desktop: ~/Library/Application Support/ERPloraHub/plugins/

# Logs
LOGS_DIR = DATA_DIR / 'logs'
LOGS_DIR.mkdir(parents=True, exist_ok=True)
LOGGING['handlers']['file']['filename'] = str(LOGS_DIR / 'hub.log')

# Backups
BACKUPS_DIR = DATA_DIR / 'backups'
BACKUPS_DIR.mkdir(parents=True, exist_ok=True)

# Reports
REPORTS_DIR = DATA_DIR / 'reports'
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

# Temp
TEMP_DIR = DATA_DIR / 'temp'
TEMP_DIR.mkdir(parents=True, exist_ok=True)

# Plugin data (outside PLUGINS_DIR to avoid being detected as a plugin)
PLUGIN_DATA_ROOT = DATA_DIR / 'plugin_data'
PLUGIN_DATA_ROOT.mkdir(parents=True, exist_ok=True)
PLUGIN_MEDIA_ROOT = MEDIA_ROOT / 'plugins'
PLUGIN_MEDIA_ROOT.mkdir(parents=True, exist_ok=True)

# =============================================================================
# SECURITY - Relaxed for local desktop
# =============================================================================

ALLOWED_HOSTS = ['127.0.0.1', 'localhost']
CSRF_COOKIE_SECURE = False

print(f"[MACOS] Data directory: {DATA_DIR}")
