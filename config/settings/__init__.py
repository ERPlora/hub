"""
ERPlora Hub - Settings Selector

When DJANGO_SETTINGS_MODULE=config.settings (the package), this __init__.py
selects the right sub-module based on HUB_ENV:
- local: Desarrollo local (default si no se especifica)
- web: Docker/Cloud deployment

When DJANGO_SETTINGS_MODULE=config.settings.web (or .local), Python still
executes this __init__.py as part of package loading, so we must skip the
import to avoid loading the wrong settings.
"""

import os

# Only run the selector when Django is loading THIS package as the settings
# module. When it's loading config.settings.web directly, skip.
_settings_module = os.environ.get('DJANGO_SETTINGS_MODULE', '')
if _settings_module == 'config.settings':
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
