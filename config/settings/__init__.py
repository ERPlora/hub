"""
ERPlora Hub - Settings Selector

Selecciona la configuración según HUB_ENV:
- web: Docker/Cloud deployment (default en Dockerfile)
- desktop_windows: Windows desktop (PyInstaller)
- desktop_macos: macOS desktop (PyInstaller)
- desktop_linux: Linux desktop (PyInstaller)

Default: Detecta OS automáticamente para desktop
Docker siempre usa HUB_ENV=web
"""

import os
import sys

# Obtener entorno de HUB_ENV o detectar automáticamente
env = os.getenv('HUB_ENV', '').lower()

if env == 'web':
    from .web import *
elif env == 'desktop_windows':
    from .desktop_windows import *
elif env == 'desktop_macos':
    from .desktop_macos import *
elif env == 'desktop_linux':
    from .desktop_linux import *
elif env in ('', 'desktop', 'local'):
    # Auto-detect OS for desktop
    if sys.platform == 'win32':
        from .desktop_windows import *
    elif sys.platform == 'darwin':
        from .desktop_macos import *
    else:
        from .desktop_linux import *
else:
    raise ValueError(
        f"Invalid HUB_ENV: '{env}'. "
        f"Valid options: web, desktop_windows, desktop_macos, desktop_linux"
    )
