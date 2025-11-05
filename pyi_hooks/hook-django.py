#-----------------------------------------------------------------------------
# Copyright (c) 2005-2023, PyInstaller Development Team.
#
# Distributed under the terms of the GNU General Public License (version 2
# or later) with exception for distributing the bootloader.
#
# The full license is in the file COPYING.txt, distributed with this software.
#
# SPDX-License-Identifier: (GPL-2.0-or-later WITH Bootloader-exception)
#-----------------------------------------------------------------------------
"""
Django hook for PyInstaller - Custom version that safely handles missing modules

IMPORTANTE: Este hook personalizado ES NECESARIO porque el hook estándar de PyInstaller
tiene un bug que causa TypeError cuando intenta procesar módulos de Django que no existen.

Error sin este hook:
  TypeError: expected str, bytes or os.PathLike object, not NoneType
  at /PyInstaller/hooks/hook-django.py line 71

Este hook corrige el problema usando try/except para manejar módulos faltantes de forma segura.

NOTA: Con collect_submodules('django') en main.spec, este hook solo necesita manejar
      data files (templates, static, locale) y migrations, pero es crítico para evitar
      errores durante el build.
"""

import os
import sys
from PyInstaller.utils import hooks as hookutil
from PyInstaller import log as logging

logger = logging.getLogger(__name__)

# Collect all Django submodules
hiddenimports = [
    'django.core.management',
    'django.core.management.commands',
    'django.core.management.commands.runserver',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.template.loaders.filesystem',
    'django.template.loaders.app_directories',
]

# Collect Django data files (templates, static files, etc)
datas = []

# Try to collect Django templates and static files
try:
    import django
    django_pkg = os.path.dirname(django.__file__)

    # Collect contrib app templates and static files
    for contrib_app in ['admin', 'auth', 'contenttypes', 'sessions', 'messages', 'staticfiles']:
        contrib_pkg = os.path.join(django_pkg, 'contrib', contrib_app)
        if os.path.exists(contrib_pkg):
            # Templates
            templates_dir = os.path.join(contrib_pkg, 'templates')
            if os.path.exists(templates_dir):
                datas.append((templates_dir, f'django/contrib/{contrib_app}/templates'))

            # Static files
            static_dir = os.path.join(contrib_pkg, 'static')
            if os.path.exists(static_dir):
                datas.append((static_dir, f'django/contrib/{contrib_app}/static'))

            # Locale files
            locale_dir = os.path.join(contrib_pkg, 'locale')
            if os.path.exists(locale_dir):
                datas.append((locale_dir, f'django/contrib/{contrib_app}/locale'))

    # Collect Django conf files
    conf_dir = os.path.join(django_pkg, 'conf')
    if os.path.exists(conf_dir):
        datas.append((conf_dir, 'django/conf'))

except Exception as e:
    logger.warning(f'Could not collect Django data files: {e}')

# Collect migrations - safely handle missing modules
try:
    # Get INSTALLED_APPS from settings
    settings_module = os.environ.get('DJANGO_SETTINGS_MODULE', 'config.settings')

    # Import settings
    if settings_module:
        try:
            # Import the settings module
            settings_parts = settings_module.split('.')
            settings_mod = __import__(settings_module, fromlist=[settings_parts[-1]])

            # Get INSTALLED_APPS
            installed_apps = getattr(settings_mod, 'INSTALLED_APPS', [])

            # Collect migrations for each app
            for app in installed_apps:
                try:
                    # Try to import the app
                    app_mod = __import__(app, fromlist=['migrations'])

                    # Check if migrations module exists
                    if hasattr(app_mod, 'migrations'):
                        migrations_path = os.path.join(os.path.dirname(app_mod.__file__), 'migrations')
                        if os.path.exists(migrations_path):
                            logger.debug(f'Collecting migrations for {app}')
                            datas.append((migrations_path, f'{app.replace(".", "/")}/migrations'))

                            # Add migrations module to hiddenimports
                            hiddenimports.append(f'{app}.migrations')

                except (ImportError, AttributeError) as e:
                    logger.debug(f'Skipping migrations for {app}: {e}')
                    continue

        except Exception as e:
            logger.warning(f'Could not import settings module {settings_module}: {e}')

except Exception as e:
    logger.warning(f'Could not collect Django migrations: {e}')

# Collect installed apps
try:
    if 'settings_mod' in locals() and hasattr(settings_mod, 'INSTALLED_APPS'):
        for app in settings_mod.INSTALLED_APPS:
            if not app.startswith('django.'):
                # Add custom apps to hiddenimports
                hiddenimports.append(app)

                # Try to collect app data (templates, static, locale)
                try:
                    app_mod = __import__(app, fromlist=[''])
                    app_path = os.path.dirname(app_mod.__file__)

                    # Templates
                    templates_dir = os.path.join(app_path, 'templates')
                    if os.path.exists(templates_dir):
                        datas.append((templates_dir, f'{app.replace(".", "/")}/templates'))

                    # Static files
                    static_dir = os.path.join(app_path, 'static')
                    if os.path.exists(static_dir):
                        datas.append((static_dir, f'{app.replace(".", "/")}/static'))

                    # Locale files
                    locale_dir = os.path.join(app_path, 'locale')
                    if os.path.exists(locale_dir):
                        datas.append((locale_dir, f'{app.replace(".", "/")}/locale'))

                except Exception as e:
                    logger.debug(f'Could not collect data for app {app}: {e}')

except Exception as e:
    logger.warning(f'Could not collect installed apps: {e}')

logger.info(f'Django hook collected {len(hiddenimports)} hidden imports and {len(datas)} data files')
