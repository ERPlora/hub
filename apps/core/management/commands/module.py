"""
Django management command for module operations
"""
import os
import json
import shutil
import zipfile
from pathlib import Path
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from apps.modules_runtime.loader import module_loader


class Command(BaseCommand):
    help = 'Manage CPOS Hub modules'

    def add_arguments(self, parser):
        subparsers = parser.add_subparsers(dest='subcommand', help='Module commands')

        # Create new module
        create_parser = subparsers.add_parser('create', help='Create a new module from template')
        create_parser.add_argument('module_id', type=str, help='Module ID (e.g., my-module)')
        create_parser.add_argument('--name', type=str, help='Module display name')
        create_parser.add_argument('--author', type=str, help='Author name')
        create_parser.add_argument('--email', type=str, help='Author email')

        # List modules
        subparsers.add_parser('list', help='List all modules')

        # Sync modules from filesystem to database
        subparsers.add_parser('sync', help='Sync modules from filesystem to database')

        # Package module
        package_parser = subparsers.add_parser('package', help='Package module as ZIP')
        package_parser.add_argument('module_id', type=str, help='Module ID to package')
        package_parser.add_argument('--output', type=str, help='Output directory', default='dist')

        # Validate module
        validate_parser = subparsers.add_parser('validate', help='Validate module structure')
        validate_parser.add_argument('module_id', type=str, help='Module ID to validate')

        # Install module from ZIP
        install_parser = subparsers.add_parser('install', help='Install module from ZIP')
        install_parser.add_argument('zip_file', type=str, help='Path to module ZIP file')

    def handle(self, *args, **options):
        subcommand = options.get('subcommand')

        if not subcommand:
            self.print_help('manage.py', 'module')
            return

        if subcommand == 'create':
            self.create_module(options)
        elif subcommand == 'list':
            self.list_modules()
        elif subcommand == 'sync':
            self.sync_modules()
        elif subcommand == 'package':
            self.package_module(options)
        elif subcommand == 'validate':
            self.validate_module(options)
        elif subcommand == 'install':
            self.install_module(options)

    def create_module(self, options):
        """Create a new module from template"""
        module_id = options['module_id']
        module_name = options.get('name') or module_id.replace('-', ' ').title()
        author = options.get('author') or 'Your Name'
        email = options.get('email') or 'your.email@example.com'

        modules_dir = Path(settings.BASE_DIR) / 'modules'
        module_dir = modules_dir / module_id

        if module_dir.exists():
            raise CommandError(f'Module directory already exists: {module_dir}')

        self.stdout.write(f'Creating module: {module_id}')

        # Create directory structure
        module_dir.mkdir(parents=True)
        (module_dir / 'templates' / module_id).mkdir(parents=True)
        (module_dir / 'static' / module_id / 'css').mkdir(parents=True)
        (module_dir / 'static' / module_id / 'js').mkdir(parents=True)
        (module_dir / 'migrations').mkdir(parents=True)

        # Create module.py
        module_py_content = f"""from django.utils.translation import gettext_lazy as _

MODULE_ID = '{module_id}'
MODULE_NAME = _('{module_name}')
MODULE_VERSION = '1.0.0'
MODULE_ICON = 'cube-outline'

MENU = {{
    'label': _('{module_name}'),
    'icon': 'cube-outline',
    'order': 100,
}}

NAVIGATION = [
    {{'label': _('Dashboard'), 'icon': 'speedometer-outline', 'id': 'dashboard'}},
]

PERMISSIONS = [
    '{module_id}.view',
    '{module_id}.change',
]
"""
        (module_dir / 'module.py').write_text(module_py_content)

        # Create __init__.py
        with open(module_dir / '__init__.py', 'w') as f:
            f.write(f'"""\n{module_name}\n"""\n')

        # Create apps.py
        app_config_class = module_id.replace('-', '').title() + 'Config'
        with open(module_dir / 'apps.py', 'w') as f:
            f.write('from django.apps import AppConfig\n\n\n')
            f.write(f'class {app_config_class}(AppConfig):\n')
            f.write("    default_auto_field = 'django.db.models.BigAutoField'\n")
            f.write(f"    name = '{module_id}'\n")
            f.write(f"    verbose_name = '{module_name}'\n")

        # Create models.py
        with open(module_dir / 'models.py', 'w') as f:
            f.write('from django.db import models\n\n')
            f.write('# Create your models here\n')

        # Create views.py
        with open(module_dir / 'views.py', 'w') as f:
            f.write('from django.shortcuts import render\n\n\n')
            f.write('def index(request):\n')
            f.write('    """Main view for module"""\n')
            f.write(f"    return render(request, '{module_id}/index.html')\n")

        # Create urls.py
        with open(module_dir / 'urls.py', 'w') as f:
            f.write('from django.urls import path\n')
            f.write('from . import views\n\n')
            f.write(f"app_name = '{module_id}'\n\n")
            f.write('urlpatterns = [\n')
            f.write("    path('', views.index, name='index'),\n")
            f.write(']\n')

        # Create template
        with open(module_dir / 'templates' / module_id / 'index.html', 'w') as f:
            f.write('{% extends "core/app_base.html" %}\n\n')
            f.write(f'{{% block page_title %}}{module_name}{{% endblock %}}\n\n')
            f.write('{% block content %}\n')
            f.write('<div style="padding: 24px;">\n')
            f.write(f'    <h1>{module_name}</h1>\n')
            f.write(f'    <p>Welcome to {module_name} module!</p>\n')
            f.write('</div>\n')
            f.write('{% endblock %}\n')

        # Create migrations __init__.py
        (module_dir / 'migrations' / '__init__.py').touch()

        # Create README.md
        with open(module_dir / 'README.md', 'w') as f:
            f.write(f'# {module_name}\n\n')
            f.write(f'{module_name} module for ERPlora Hub.\n\n')
            f.write('## Installation\n\n')
            f.write('This module can be installed via CPOS Cloud marketplace.\n\n')
            f.write('## Development\n\n')
            f.write('```bash\n')
            f.write('python manage.py module sync\n')
            f.write('```\n')

        self.stdout.write(self.style.SUCCESS(f'Module created successfully: {module_dir}'))
        self.stdout.write('Next steps:')
        self.stdout.write(f'  1. cd modules/{module_id}')
        self.stdout.write('  2. Edit your models, views, and templates')
        self.stdout.write('  3. Run: python manage.py module sync')
        self.stdout.write('  4. Run: python manage.py module package ' + module_id)

    def list_modules(self):
        """List all modules from filesystem"""
        modules_dir = Path(settings.MODULES_DIR)

        if not modules_dir.exists():
            self.stdout.write('No modules directory found')
            return

        modules = []

        # Scan filesystem for modules
        for module_dir in modules_dir.iterdir():
            if not module_dir.is_dir():
                continue

            # Skip hidden directories
            if module_dir.name.startswith('.'):
                continue

            module_id = module_dir.name
            is_active = not module_id.startswith('_')
            clean_id = module_id.lstrip('_')

            # Read module.py metadata
            module_py_path = module_dir / 'module.py'
            if module_py_path.exists():
                try:
                    import importlib.util
                    spec = importlib.util.spec_from_file_location(f"{clean_id}.module", module_py_path)
                    mod = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(mod)
                    name = str(getattr(mod, 'MODULE_NAME', clean_id.title()))
                    version = getattr(mod, 'MODULE_VERSION', '1.0.0')
                    modules.append({
                        'id': clean_id,
                        'name': name,
                        'version': version,
                        'is_active': is_active
                    })
                except Exception as e:
                    self.stdout.write(self.style.WARNING(
                        f'Warning: Error reading module.py for {module_id}: {e}'
                    ))

        if not modules:
            self.stdout.write('No modules found')
            return

        # Sort by name
        modules.sort(key=lambda x: x['name'])

        self.stdout.write(self.style.SUCCESS('Installed Modules:'))
        self.stdout.write('-' * 80)

        for module in modules:
            status = '✓' if module['is_active'] else '✗'
            self.stdout.write(
                f"{status} {module['id']:20} {module['name']:30} v{module['version']}"
            )

    def sync_modules(self):
        """Sync modules from filesystem to database"""
        self.stdout.write('Syncing modules...')

        installed, updated = module_loader.sync_modules()

        self.stdout.write(self.style.SUCCESS(
            f'Sync complete: {installed} installed, {updated} updated'
        ))

        # Load active modules
        loaded = module_loader.load_all_active_modules()
        self.stdout.write(self.style.SUCCESS(f'Loaded {loaded} active modules'))

    def package_module(self, options):
        """Package module as ZIP file"""
        module_id = options['module_id']
        output_dir = Path(options['output'])

        modules_dir = Path(settings.BASE_DIR) / 'modules'
        module_dir = modules_dir / module_id

        if not module_dir.exists():
            raise CommandError(f'Module not found: {module_id}')

        # Validate first
        if not self._validate_module_structure(module_dir):
            raise CommandError('Module validation failed')

        # Create output directory
        output_dir.mkdir(parents=True, exist_ok=True)

        # Read version from module.py
        version = '1.0.0'
        module_py_path = module_dir / 'module.py'
        if module_py_path.exists():
            try:
                import importlib.util
                spec = importlib.util.spec_from_file_location(f"{module_id}.module", module_py_path)
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                version = getattr(mod, 'MODULE_VERSION', '1.0.0')
            except Exception:
                pass

        # Create ZIP file
        zip_filename = output_dir / f'{module_id}-{version}.zip'

        self.stdout.write(f'Packaging {module_id}...')

        with zipfile.ZipFile(zip_filename, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, dirs, files in os.walk(module_dir):
                # Skip __pycache__ and .pyc files
                dirs[:] = [d for d in dirs if d != '__pycache__']

                for file in files:
                    if file.endswith('.pyc'):
                        continue

                    file_path = Path(root) / file
                    arcname = file_path.relative_to(modules_dir)
                    zipf.write(file_path, arcname)

        self.stdout.write(self.style.SUCCESS(f'Module packaged: {zip_filename}'))
        self.stdout.write(f'Size: {zip_filename.stat().st_size / 1024:.2f} KB')

    def validate_module(self, options):
        """Validate module structure"""
        module_id = options['module_id']
        modules_dir = Path(settings.BASE_DIR) / 'modules'
        module_dir = modules_dir / module_id

        if not module_dir.exists():
            raise CommandError(f'Module not found: {module_id}')

        self.stdout.write(f'Validating module: {module_id}')

        if self._validate_module_structure(module_dir):
            self.stdout.write(self.style.SUCCESS('✓ Module validation passed'))
        else:
            raise CommandError('Module validation failed')

    def _validate_module_structure(self, module_dir):
        """Validate module structure"""
        required_files = ['module.py', '__init__.py', 'apps.py']

        valid = True
        for file in required_files:
            file_path = module_dir / file
            if not file_path.exists():
                self.stdout.write(self.style.ERROR(f'  Missing required file: {file}'))
                valid = False
            else:
                self.stdout.write(self.style.SUCCESS(f'  Found: {file}'))

        # Validate module.py
        module_py = module_dir / 'module.py'
        if module_py.exists():
            try:
                import importlib.util
                spec = importlib.util.spec_from_file_location(
                    f"{module_dir.name}.module", module_py
                )
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)

                required_attrs = {
                    'MODULE_ID': getattr(mod, 'MODULE_ID', None),
                    'MODULE_NAME': getattr(mod, 'MODULE_NAME', None),
                }
                for attr, value in required_attrs.items():
                    if value is None:
                        self.stdout.write(self.style.ERROR(
                            f'  module.py missing: {attr}'
                        ))
                        valid = False
                    else:
                        self.stdout.write(self.style.SUCCESS(
                            f'  module.py {attr}: {value}'
                        ))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'  Error loading module.py: {e}'))
                valid = False

        return valid

    def install_module(self, options):
        """Install module from ZIP file"""
        zip_file = Path(options['zip_file'])

        if not zip_file.exists():
            raise CommandError(f'ZIP file not found: {zip_file}')

        modules_dir = Path(settings.BASE_DIR) / 'modules'

        self.stdout.write(f'Installing module from: {zip_file}')

        # Extract ZIP
        with zipfile.ZipFile(zip_file, 'r') as zipf:
            # Get module_id from first directory
            first_file = zipf.namelist()[0]
            module_id = first_file.split('/')[0]

            module_dir = modules_dir / module_id

            if module_dir.exists():
                self.stdout.write(self.style.WARNING(
                    f'Module directory exists: {module_id}. Overwriting...'
                ))
                shutil.rmtree(module_dir)

            zipf.extractall(modules_dir)

        self.stdout.write(self.style.SUCCESS(f'Module extracted to: {module_dir}'))

        # Sync to database
        self.sync_modules()

        self.stdout.write(self.style.SUCCESS(f'Module installed: {module_id}'))
