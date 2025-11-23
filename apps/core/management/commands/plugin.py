"""
Django management command for plugin operations
"""
import os
import json
import shutil
import zipfile
from pathlib import Path
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from apps.plugins_runtime.loader import plugin_loader


class Command(BaseCommand):
    help = 'Manage CPOS Hub plugins'

    def add_arguments(self, parser):
        subparsers = parser.add_subparsers(dest='subcommand', help='Plugin commands')

        # Create new plugin
        create_parser = subparsers.add_parser('create', help='Create a new plugin from template')
        create_parser.add_argument('plugin_id', type=str, help='Plugin ID (e.g., my-plugin)')
        create_parser.add_argument('--name', type=str, help='Plugin display name')
        create_parser.add_argument('--author', type=str, help='Author name')
        create_parser.add_argument('--email', type=str, help='Author email')

        # List plugins
        subparsers.add_parser('list', help='List all plugins')

        # Sync plugins from filesystem to database
        subparsers.add_parser('sync', help='Sync plugins from filesystem to database')

        # Package plugin
        package_parser = subparsers.add_parser('package', help='Package plugin as ZIP')
        package_parser.add_argument('plugin_id', type=str, help='Plugin ID to package')
        package_parser.add_argument('--output', type=str, help='Output directory', default='dist')

        # Validate plugin
        validate_parser = subparsers.add_parser('validate', help='Validate plugin structure')
        validate_parser.add_argument('plugin_id', type=str, help='Plugin ID to validate')

        # Install plugin from ZIP
        install_parser = subparsers.add_parser('install', help='Install plugin from ZIP')
        install_parser.add_argument('zip_file', type=str, help='Path to plugin ZIP file')

    def handle(self, *args, **options):
        subcommand = options.get('subcommand')

        if not subcommand:
            self.print_help('manage.py', 'plugin')
            return

        if subcommand == 'create':
            self.create_plugin(options)
        elif subcommand == 'list':
            self.list_plugins()
        elif subcommand == 'sync':
            self.sync_plugins()
        elif subcommand == 'package':
            self.package_plugin(options)
        elif subcommand == 'validate':
            self.validate_plugin(options)
        elif subcommand == 'install':
            self.install_plugin(options)

    def create_plugin(self, options):
        """Create a new plugin from template"""
        plugin_id = options['plugin_id']
        plugin_name = options.get('name') or plugin_id.replace('-', ' ').title()
        author = options.get('author') or 'Your Name'
        email = options.get('email') or 'your.email@example.com'

        plugins_dir = Path(settings.BASE_DIR) / 'plugins'
        plugin_dir = plugins_dir / plugin_id

        if plugin_dir.exists():
            raise CommandError(f'Plugin directory already exists: {plugin_dir}')

        self.stdout.write(f'Creating plugin: {plugin_id}')

        # Create directory structure
        plugin_dir.mkdir(parents=True)
        (plugin_dir / 'templates' / plugin_id).mkdir(parents=True)
        (plugin_dir / 'static' / plugin_id / 'css').mkdir(parents=True)
        (plugin_dir / 'static' / plugin_id / 'js').mkdir(parents=True)
        (plugin_dir / 'migrations').mkdir(parents=True)

        # Create plugin.json
        plugin_json = {
            'plugin_id': plugin_id,
            'name': plugin_name,
            'version': '1.0.0',
            'description': f'{plugin_name} plugin for CPOS Hub',
            'author': author,
            'author_email': email,
            'license': 'MIT',
            'icon': 'cube-outline',
            'category': 'general',
            'menu': {
                'label': plugin_name,
                'icon': 'cube-outline',
                'order': 100,
                'show': True
            },
            'main_url': f'{plugin_id}:index',
            'dependencies': [],
            'min_hub_version': '1.0.0'
        }

        with open(plugin_dir / 'plugin.json', 'w') as f:
            json.dump(plugin_json, f, indent=4)

        # Create __init__.py
        with open(plugin_dir / '__init__.py', 'w') as f:
            f.write(f'"""\n{plugin_name}\n"""\n')
            f.write(f"default_app_config = '{plugin_id}.apps.{plugin_id.replace('-', '').title()}Config'\n")

        # Create apps.py
        app_config_class = plugin_id.replace('-', '').title() + 'Config'
        with open(plugin_dir / 'apps.py', 'w') as f:
            f.write('from django.apps import AppConfig\n\n\n')
            f.write(f'class {app_config_class}(AppConfig):\n')
            f.write("    default_auto_field = 'django.db.models.BigAutoField'\n")
            f.write(f"    name = '{plugin_id}'\n")
            f.write(f"    verbose_name = '{plugin_name}'\n")

        # Create models.py
        with open(plugin_dir / 'models.py', 'w') as f:
            f.write('from django.db import models\n\n')
            f.write('# Create your models here\n')

        # Create views.py
        with open(plugin_dir / 'views.py', 'w') as f:
            f.write('from django.shortcuts import render\n\n\n')
            f.write('def index(request):\n')
            f.write('    """Main view for plugin"""\n')
            f.write(f"    return render(request, '{plugin_id}/index.html')\n")

        # Create urls.py
        with open(plugin_dir / 'urls.py', 'w') as f:
            f.write('from django.urls import path\n')
            f.write('from . import views\n\n')
            f.write(f"app_name = '{plugin_id}'\n\n")
            f.write('urlpatterns = [\n')
            f.write("    path('', views.index, name='index'),\n")
            f.write(']\n')

        # Create template
        with open(plugin_dir / 'templates' / plugin_id / 'index.html', 'w') as f:
            f.write('{% extends "core/app_base.html" %}\n\n')
            f.write(f'{{% block page_title %}}{plugin_name}{{% endblock %}}\n\n')
            f.write('{% block content %}\n')
            f.write('<div style="padding: 24px;">\n')
            f.write(f'    <h1>{plugin_name}</h1>\n')
            f.write(f'    <p>Welcome to {plugin_name} plugin!</p>\n')
            f.write('</div>\n')
            f.write('{% endblock %}\n')

        # Create migrations __init__.py
        (plugin_dir / 'migrations' / '__init__.py').touch()

        # Create README.md
        with open(plugin_dir / 'README.md', 'w') as f:
            f.write(f'# {plugin_name}\n\n')
            f.write(f'{plugin_json["description"]}\n\n')
            f.write('## Installation\n\n')
            f.write('This plugin can be installed via CPOS Cloud marketplace.\n\n')
            f.write('## Development\n\n')
            f.write('```bash\n')
            f.write('python manage.py plugin sync\n')
            f.write('```\n')

        self.stdout.write(self.style.SUCCESS(f'Plugin created successfully: {plugin_dir}'))
        self.stdout.write('Next steps:')
        self.stdout.write(f'  1. cd plugins/{plugin_id}')
        self.stdout.write('  2. Edit your models, views, and templates')
        self.stdout.write('  3. Run: python manage.py plugin sync')
        self.stdout.write('  4. Run: python manage.py plugin package ' + plugin_id)

    def list_plugins(self):
        """List all plugins from filesystem"""
        plugins_dir = Path(settings.PLUGINS_DIR)

        if not plugins_dir.exists():
            self.stdout.write('No plugins directory found')
            return

        plugins = []

        # Scan filesystem for plugins
        for plugin_dir in plugins_dir.iterdir():
            if not plugin_dir.is_dir():
                continue

            # Skip hidden directories
            if plugin_dir.name.startswith('.'):
                continue

            plugin_id = plugin_dir.name
            is_active = not plugin_id.startswith('_')
            clean_id = plugin_id.lstrip('_')

            # Read plugin.json
            plugin_json_path = plugin_dir / 'plugin.json'
            if plugin_json_path.exists():
                try:
                    with open(plugin_json_path, 'r', encoding='utf-8') as f:
                        metadata = json.load(f)
                        name = metadata.get('name', clean_id.title())
                        version = metadata.get('version', '1.0.0')
                        plugins.append({
                            'id': clean_id,
                            'name': name,
                            'version': version,
                            'is_active': is_active
                        })
                except Exception as e:
                    self.stdout.write(self.style.WARNING(
                        f'Warning: Error reading plugin.json for {plugin_id}: {e}'
                    ))

        if not plugins:
            self.stdout.write('No plugins found')
            return

        # Sort by name
        plugins.sort(key=lambda x: x['name'])

        self.stdout.write(self.style.SUCCESS('Installed Plugins:'))
        self.stdout.write('-' * 80)

        for plugin in plugins:
            status = '✓' if plugin['is_active'] else '✗'
            self.stdout.write(
                f"{status} {plugin['id']:20} {plugin['name']:30} v{plugin['version']}"
            )

    def sync_plugins(self):
        """Sync plugins from filesystem to database"""
        self.stdout.write('Syncing plugins...')

        installed, updated = plugin_loader.sync_plugins()

        self.stdout.write(self.style.SUCCESS(
            f'Sync complete: {installed} installed, {updated} updated'
        ))

        # Load active plugins
        loaded = plugin_loader.load_all_active_plugins()
        self.stdout.write(self.style.SUCCESS(f'Loaded {loaded} active plugins'))

    def package_plugin(self, options):
        """Package plugin as ZIP file"""
        plugin_id = options['plugin_id']
        output_dir = Path(options['output'])

        plugins_dir = Path(settings.BASE_DIR) / 'plugins'
        plugin_dir = plugins_dir / plugin_id

        if not plugin_dir.exists():
            raise CommandError(f'Plugin not found: {plugin_id}')

        # Validate first
        if not self._validate_plugin_structure(plugin_dir):
            raise CommandError('Plugin validation failed')

        # Create output directory
        output_dir.mkdir(parents=True, exist_ok=True)

        # Read version from plugin.json
        with open(plugin_dir / 'plugin.json', 'r') as f:
            metadata = json.load(f)
            version = metadata.get('version', '1.0.0')

        # Create ZIP file
        zip_filename = output_dir / f'{plugin_id}-{version}.zip'

        self.stdout.write(f'Packaging {plugin_id}...')

        with zipfile.ZipFile(zip_filename, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, dirs, files in os.walk(plugin_dir):
                # Skip __pycache__ and .pyc files
                dirs[:] = [d for d in dirs if d != '__pycache__']

                for file in files:
                    if file.endswith('.pyc'):
                        continue

                    file_path = Path(root) / file
                    arcname = file_path.relative_to(plugins_dir)
                    zipf.write(file_path, arcname)

        self.stdout.write(self.style.SUCCESS(f'Plugin packaged: {zip_filename}'))
        self.stdout.write(f'Size: {zip_filename.stat().st_size / 1024:.2f} KB')

    def validate_plugin(self, options):
        """Validate plugin structure"""
        plugin_id = options['plugin_id']
        plugins_dir = Path(settings.BASE_DIR) / 'plugins'
        plugin_dir = plugins_dir / plugin_id

        if not plugin_dir.exists():
            raise CommandError(f'Plugin not found: {plugin_id}')

        self.stdout.write(f'Validating plugin: {plugin_id}')

        if self._validate_plugin_structure(plugin_dir):
            self.stdout.write(self.style.SUCCESS('✓ Plugin validation passed'))
        else:
            raise CommandError('Plugin validation failed')

    def _validate_plugin_structure(self, plugin_dir):
        """Validate plugin structure"""
        required_files = ['plugin.json', '__init__.py', 'apps.py']

        valid = True
        for file in required_files:
            file_path = plugin_dir / file
            if not file_path.exists():
                self.stdout.write(self.style.ERROR(f'✗ Missing required file: {file}'))
                valid = False
            else:
                self.stdout.write(self.style.SUCCESS(f'✓ Found: {file}'))

        # Validate plugin.json
        plugin_json = plugin_dir / 'plugin.json'
        if plugin_json.exists():
            try:
                with open(plugin_json, 'r') as f:
                    metadata = json.load(f)

                required_fields = ['plugin_id', 'name', 'version']
                for field in required_fields:
                    if field not in metadata:
                        self.stdout.write(self.style.ERROR(
                            f'✗ plugin.json missing required field: {field}'
                        ))
                        valid = False
                    else:
                        self.stdout.write(self.style.SUCCESS(
                            f'✓ plugin.json has {field}: {metadata[field]}'
                        ))
            except json.JSONDecodeError:
                self.stdout.write(self.style.ERROR('✗ Invalid JSON in plugin.json'))
                valid = False

        return valid

    def install_plugin(self, options):
        """Install plugin from ZIP file"""
        zip_file = Path(options['zip_file'])

        if not zip_file.exists():
            raise CommandError(f'ZIP file not found: {zip_file}')

        plugins_dir = Path(settings.BASE_DIR) / 'plugins'

        self.stdout.write(f'Installing plugin from: {zip_file}')

        # Extract ZIP
        with zipfile.ZipFile(zip_file, 'r') as zipf:
            # Get plugin_id from first directory
            first_file = zipf.namelist()[0]
            plugin_id = first_file.split('/')[0]

            plugin_dir = plugins_dir / plugin_id

            if plugin_dir.exists():
                self.stdout.write(self.style.WARNING(
                    f'Plugin directory exists: {plugin_id}. Overwriting...'
                ))
                shutil.rmtree(plugin_dir)

            zipf.extractall(plugins_dir)

        self.stdout.write(self.style.SUCCESS(f'Plugin extracted to: {plugin_dir}'))

        # Sync to database
        self.sync_plugins()

        self.stdout.write(self.style.SUCCESS(f'Plugin installed: {plugin_id}'))
