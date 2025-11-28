"""
ERPlora Hub - Settings Selector

Selecciona la configuración según HUB_ENV:
- local: Desarrollo local (default si no se especifica)
- web: Docker/Cloud deployment
- desktop_windows: Windows desktop (PyInstaller)
- desktop_macos: macOS desktop (PyInstaller)
- desktop_linux: Linux desktop (PyInstaller)
"""

import os
import sys

# Obtener entorno de HUB_ENV
env = os.getenv('HUB_ENV', '').lower()

if env == 'web':
    from .web import *
elif env == 'desktop_windows':
    from .desktop_windows import *
elif env == 'desktop_macos':
    from .desktop_macos import *
elif env == 'desktop_linux':
    from .desktop_linux import *
elif env in ('', 'local', 'dev', 'development'):
    # Default: local development
    from .local import *
else:
    raise ValueError(
        f"Invalid HUB_ENV: '{env}'. "
        f"Valid options: local, web, desktop_windows, desktop_macos, desktop_linux"
    )
