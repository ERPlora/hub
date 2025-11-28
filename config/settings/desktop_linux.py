"""
ERPlora Hub - Linux Desktop Settings

Configuración para Linux desktop (PyInstaller AppImage/binary)
Datos en: /home/<user>/.erplora-hub/
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
# PATHS - Linux specific
# =============================================================================

# ~/.erplora-hub (hidden directory)
DATA_DIR = Path.home() / '.erplora-hub'
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Database
DATABASE_DIR = DATA_DIR / 'db'
DATABASE_DIR.mkdir(parents=True, exist_ok=True)
DATABASES['default']['NAME'] = DATABASE_DIR / 'db.sqlite3'

# Media
MEDIA_ROOT = DATA_DIR / 'media'
MEDIA_ROOT.mkdir(parents=True, exist_ok=True)

# Plugins
PLUGINS_DIR = DATA_DIR / 'plugins'
PLUGINS_DIR.mkdir(parents=True, exist_ok=True)
PLUGINS_ROOT = PLUGINS_DIR

# In development, also check local plugins folder
if DEVELOPMENT_MODE:
    PLUGIN_DISCOVERY_PATHS = [
        BASE_DIR / 'plugins',  # Development plugins
        PLUGINS_DIR,           # Installed plugins
    ]
    # Use local plugins in dev
    PLUGINS_DIR = BASE_DIR / 'plugins'
    PLUGINS_ROOT = PLUGINS_DIR
else:
    PLUGIN_DISCOVERY_PATHS = [PLUGINS_DIR]

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

# Plugin data
PLUGIN_DATA_ROOT = PLUGINS_DIR / 'data'
PLUGIN_DATA_ROOT.mkdir(parents=True, exist_ok=True)
PLUGIN_MEDIA_ROOT = MEDIA_ROOT / 'plugins'
PLUGIN_MEDIA_ROOT.mkdir(parents=True, exist_ok=True)

# =============================================================================
# SECURITY - Relaxed for local desktop
# =============================================================================

ALLOWED_HOSTS = ['127.0.0.1', 'localhost']
CSRF_COOKIE_SECURE = False

print(f"[LINUX] Data directory: {DATA_DIR}")
