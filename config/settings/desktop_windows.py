"""
ERPlora Hub - Windows Desktop Settings

Configuración para Windows desktop (PyInstaller .exe)
Datos en: C:\\Users\\<user>\\AppData\\Local\\ERPloraHub\\
"""

from .base import *
from pathlib import Path
import os

# =============================================================================
# DEPLOYMENT
# =============================================================================

DEPLOYMENT_MODE = 'desktop'
DEBUG = config('DEBUG', default=True, cast=bool)
OFFLINE_ENABLED = True
CLOUD_SYNC_REQUIRED = False

# =============================================================================
# PATHS - Windows specific
# =============================================================================

# AppData\Local\ERPloraHub
_LOCAL_APPDATA = os.getenv('LOCALAPPDATA', Path.home() / 'AppData' / 'Local')
DATA_DIR = Path(_LOCAL_APPDATA) / 'ERPloraHub'
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Database
DATABASE_DIR = DATA_DIR / 'db'
DATABASE_DIR.mkdir(parents=True, exist_ok=True)
DATABASES['default']['NAME'] = DATABASE_DIR / 'db.sqlite3'

# Media
MEDIA_ROOT = DATA_DIR / 'media'
MEDIA_ROOT.mkdir(parents=True, exist_ok=True)

# Modules - uses base.py config (MODULES_DIR from DataPaths)
# In desktop: %LOCALAPPDATA%\ERPloraHub\modules\

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

# Module data (outside MODULES_DIR to avoid being detected as a module)
MODULE_DATA_ROOT = DATA_DIR / 'module_data'
MODULE_DATA_ROOT.mkdir(parents=True, exist_ok=True)
MODULE_MEDIA_ROOT = MEDIA_ROOT / 'modules'
MODULE_MEDIA_ROOT.mkdir(parents=True, exist_ok=True)

# =============================================================================
# SECURITY - Relaxed for local desktop
# =============================================================================

ALLOWED_HOSTS = ['127.0.0.1', 'localhost']
CSRF_COOKIE_SECURE = False

print(f"[WINDOWS] Data directory: {DATA_DIR}")
