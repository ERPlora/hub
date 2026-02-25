"""
ERPlora Hub - Sandbox Settings

Isolated environment for testing the setup wizard, module installation, etc.
Inherits from local.py but uses separate paths (ERPloraHub-sandbox/).

Usage:
    HUB_ENV=sandbox python manage.py sandbox           # wipe + migrate + runserver
    HUB_ENV=sandbox python manage.py sandbox 8080      # custom port
    HUB_ENV=sandbox python manage.py sandbox --no-run  # wipe + migrate only
"""

from .local import *
from pathlib import Path
import sys

# =============================================================================
# DEV MODULES FALLBACK — path to copy modules from when Cloud has no ZIPs
# =============================================================================

if sys.platform == "darwin":
    DEV_MODULES_DIR = Path.home() / "Library" / "Application Support" / "ERPloraHub" / "modules"
else:
    DEV_MODULES_DIR = Path.home() / ".erplora-hub" / "modules"

# Remember dev modules path so we can clean sys.path
_dev_modules_path = str(MODULES_DIR)

# =============================================================================
# SANDBOX PATHS — isolated from development data
# =============================================================================

if sys.platform == "darwin":
    _SANDBOX_BASE = Path.home() / "Library" / "Application Support" / "ERPloraHub-sandbox"
else:
    _SANDBOX_BASE = Path.home() / ".erplora-hub-sandbox"

SANDBOX_MODE = True

# Database
DATABASE_DIR = _SANDBOX_BASE / "db"
DATABASES['default']['NAME'] = DATABASE_DIR / "db.sqlite3"

# Modules
MODULES_DIR = _SANDBOX_BASE / "modules"
MODULES_ROOT = MODULES_DIR
MODULE_DISCOVERY_PATHS = [MODULES_DIR]

# Media, Logs
MEDIA_ROOT = _SANDBOX_BASE / "media"
LOGS_DIR = _SANDBOX_BASE / "logs"
LOGGING['handlers']['file']['filename'] = str(LOGS_DIR / 'hub.log')

# Module data
MODULE_DATA_ROOT = _SANDBOX_BASE / "module_data"
MODULE_MEDIA_ROOT = MEDIA_ROOT / "modules"

# Ensure directories
for _d in [DATABASE_DIR, MODULES_DIR, MEDIA_ROOT, LOGS_DIR, MODULE_DATA_ROOT, MODULE_MEDIA_ROOT]:
    _d.mkdir(parents=True, exist_ok=True)

# Fix sys.path: remove dev modules path added by local.py, add sandbox path
if _dev_modules_path in sys.path:
    sys.path.remove(_dev_modules_path)
if str(MODULES_DIR) not in sys.path:
    sys.path.insert(0, str(MODULES_DIR))

# Disable symlink creation (sandbox is not the main dev env)
def _create_dev_symlinks():
    pass

# =============================================================================
# RELOAD MODULES from sandbox directory (not dev)
# =============================================================================
# 1. Strip ALL modules loaded by local.py (they point to dev folder)
# 2. Discover modules in sandbox/modules/ (empty on first launch, populated after setup)
# 3. On reloader restart after module install, they get picked up here

_CORE_PREFIXES = ('django', 'apps.', 'health_check')
_THIRD_PARTY = {
    'djmoney', 'django_htmx', 'djicons', 'django_components',
    'rest_framework', 'drf_spectacular', 'drf_spectacular_sidecar',
    'debug_toolbar', 'django_browser_reload',
}
INSTALLED_APPS = [
    app for app in INSTALLED_APPS
    if any(app.startswith(p) for p in _CORE_PREFIXES) or app in _THIRD_PARTY
]

# Discover sandbox modules (same logic as reload_local_modules but simpler)
if MODULES_DIR.exists():
    for module_dir in sorted(MODULES_DIR.iterdir()):
        if not module_dir.is_dir():
            continue
        if module_dir.name.startswith('.') or module_dir.name.startswith('_'):
            continue
        mid = module_dir.name
        if mid not in INSTALLED_APPS:
            INSTALLED_APPS.append(mid)
            print(f"[SANDBOX] Loaded module: {mid}")

# Reset and reload module template dirs from sandbox
TEMPLATES[0]['DIRS'] = [
    d for d in TEMPLATES[0]['DIRS']
    if 'ERPloraHub/' not in str(d)
]
if MODULES_DIR.exists():
    for module_dir in MODULES_DIR.iterdir():
        if module_dir.is_dir() and (module_dir / 'templates').exists():
            tpl = str(module_dir / 'templates')
            if tpl not in TEMPLATES[0]['DIRS']:
                TEMPLATES[0]['DIRS'].append(tpl)

print(f"[SANDBOX] Base: {_SANDBOX_BASE}")
print(f"[SANDBOX] DB: {DATABASES['default']['NAME']}")
print(f"[SANDBOX] Modules: {MODULES_DIR}")
print(f"[SANDBOX] Dev fallback: {DEV_MODULES_DIR}")
