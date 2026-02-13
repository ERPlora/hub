"""
ERPlora Hub - Settings Selector

Selecciona la configuración según HUB_ENV:
- local: Desarrollo local (default si no se especifica)
- web: Docker/Cloud deployment
"""

import os

# Obtener entorno de HUB_ENV
env = os.getenv('HUB_ENV', '').lower()

if env == 'web':
    from .web import *
elif env in ('', 'local', 'dev', 'development'):
    # Default: local development
    from .local import *
else:
    raise ValueError(
        f"Invalid HUB_ENV: '{env}'. "
        f"Valid options: local, web"
    )
