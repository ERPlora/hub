"""
Management command para crear un nuevo plugin desde template.

Uso:
    python manage.py create_plugin <plugin_id> [--name "Plugin Name"] [--author "Author"]

Ejemplos:
    python manage.py create_plugin products --name "Products Manager" --author "CPOS Team"
    python manage.py create_plugin restaurant-pos --name "Restaurant POS" --author "John Doe"
"""

from django.core.management.base import BaseCommand, CommandError
from pathlib import Path
from django.conf import settings
import json
import shutil


class Command(BaseCommand):
    help = 'Crea un nuevo plugin desde template'

    def add_arguments(self, parser):
        parser.add_argument(
            'plugin_id',
            type=str,
            help='ID único del plugin (ej: products, restaurant-pos)'
        )
        parser.add_argument(
            '--name',
            type=str,
            default=None,
            help='Nombre descriptivo del plugin'
        )
        parser.add_argument(
            '--author',
            type=str,
            default='CPOS Plugin Developer',
            help='Nombre del autor del plugin'
        )
        parser.add_argument(
            '--description',
            type=str,
            default='Plugin description',
            help='Descripción corta del plugin'
        )

    def handle(self, *args, **options):
        plugin_id = options['plugin_id']
        plugin_name = options['name'] or plugin_id.replace('-', ' ').replace('_', ' ').title()
        author = options['author']
        description = options['description']

        # Validar plugin_id
        if not plugin_id.replace('-', '').replace('_', '').isalnum():
            raise CommandError('plugin_id debe contener solo letras, números, guiones y guiones bajos')

        # Ruta base para plugins en desarrollo
        base_dir = Path(settings.BASE_DIR)
        plugins_dev_dir = base_dir / 'plugins'
        plugin_dir = plugins_dev_dir / plugin_id

        if plugin_dir.exists():
            raise CommandError(f'El plugin {plugin_id} ya existe en {plugin_dir}')

        self.stdout.write(self.style.SUCCESS(f'\n📦 Creando plugin: {plugin_name}'))
        self.stdout.write(f'   ID: {plugin_id}')
        self.stdout.write(f'   Autor: {author}')
        self.stdout.write(f'   Ubicación: {plugin_dir}\n')

        # Crear estructura de directorios
        plugin_dir.mkdir(parents=True, exist_ok=True)
        (plugin_dir / 'templates' / plugin_id).mkdir(parents=True, exist_ok=True)
        (plugin_dir / 'static' / plugin_id / 'css').mkdir(parents=True, exist_ok=True)
        (plugin_dir / 'static' / plugin_id / 'js').mkdir(parents=True, exist_ok=True)
        (plugin_dir / 'migrations').mkdir(parents=True, exist_ok=True)
        (plugin_dir / 'management' / 'commands').mkdir(parents=True, exist_ok=True)
        (plugin_dir / 'tests').mkdir(parents=True, exist_ok=True)

        # Crear plugin.json
        plugin_json = {
            "plugin_id": plugin_id,
            "name": plugin_name,
            "version": "0.1.0",
            "description": description,
            "author": author,
            "dependencies": {
                "python": [],
                "plugins": []
            },
            "compatibility": {
                "min_cpos_version": settings.HUB_VERSION,
                "max_cpos_version": "99.0.0"
            },
            "permissions": {
                "database": True,
                "filesystem": False,
                "network": False,
                "hardware": False
            },
            "menu": {
                "label": plugin_name,
                "icon": "cube-outline",
                "url": f"/{plugin_id}/"
            }
        }

        with open(plugin_dir / 'plugin.json', 'w') as f:
            json.dump(plugin_json, f, indent=2)

        # Crear __init__.py
        with open(plugin_dir / '__init__.py', 'w') as f:
            f.write(f'"""Plugin {plugin_name}"""\n')
            f.write(f"default_app_config = '{plugin_id}.apps.{plugin_id.replace('-', '_').title().replace('_', '')}Config'\n")

        # Crear apps.py
        app_class_name = plugin_id.replace('-', '_').title().replace('_', '')
        with open(plugin_dir / 'apps.py', 'w') as f:
            f.write(f'''from django.apps import AppConfig


class {app_class_name}Config(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = '{plugin_id}'
    verbose_name = '{plugin_name}'

    def ready(self):
        """Código que se ejecuta cuando el plugin se carga"""
        pass
''')

        # Crear models.py
        with open(plugin_dir / 'models.py', 'w') as f:
            f.write(f'''"""
Modelos del plugin {plugin_name}

IMPORTANTE: Usa prefijos en db_table para evitar conflictos.
Por defecto Django usa: {plugin_id}_modelname
"""

from django.db import models
from django.conf import settings


# Ejemplo de modelo
# class Product(models.Model):
#     name = models.CharField(max_length=255)
#     price = models.DecimalField(max_digits=10, decimal_places=2)
#     created_at = models.DateTimeField(auto_now_add=True)
#     created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
#
#     class Meta:
#         db_table = '{plugin_id}_product'  # Prefijo para evitar conflictos
#         ordering = ['-created_at']
#
#     def __str__(self):
#         return self.name
''')

        # Crear views.py
        with open(plugin_dir / 'views.py', 'w') as f:
            f.write(f'''"""
Vistas del plugin {plugin_name}
"""

from django.shortcuts import render
from django.contrib.auth.decorators import login_required


@login_required
def index(request):
    """Vista principal del plugin"""
    context = {{
        'plugin_name': '{plugin_name}',
    }}
    return render(request, '{plugin_id}/index.html', context)
''')

        # Crear urls.py
        with open(plugin_dir / 'urls.py', 'w') as f:
            f.write(f'''"""
URLs del plugin {plugin_name}
"""

from django.urls import path
from . import views

app_name = '{plugin_id}'

urlpatterns = [
    path('', views.index, name='index'),
]
''')

        # Crear template index.html
        with open(plugin_dir / 'templates' / plugin_id / 'index.html', 'w') as f:
            f.write(f'''{{%extends "core/app_base.html"%}}
{{%load static%}}

{{%block content%}}
<ion-content>
    <div class="ion-padding">
        <ion-card>
            <ion-card-header>
                <ion-card-title>{plugin_name}</ion-card-title>
            </ion-card-header>
            <ion-card-content>
                <p>¡Plugin creado exitosamente!</p>
                <p>Comienza a desarrollar tu plugin aquí.</p>
            </ion-card-content>
        </ion-card>
    </div>
</ion-content>
{{%endblock%}}
''')

        # Crear migrations/__init__.py
        with open(plugin_dir / 'migrations' / '__init__.py', 'w') as f:
            f.write('')

        # Crear management/__init__.py
        with open(plugin_dir / 'management' / '__init__.py', 'w') as f:
            f.write('')
        with open(plugin_dir / 'management' / 'commands' / '__init__.py', 'w') as f:
            f.write('')

        # Crear tests/__init__.py
        with open(plugin_dir / 'tests' / '__init__.py', 'w') as f:
            f.write('')

        # Crear test_basic.py
        with open(plugin_dir / 'tests' / 'test_basic.py', 'w') as f:
            f.write(f'''"""
Tests básicos del plugin {plugin_name}
"""

import pytest
from django.test import TestCase


class BasicTestCase(TestCase):
    """Tests básicos del plugin"""

    def test_plugin_loads(self):
        """Verifica que el plugin se carga correctamente"""
        from django.apps import apps
        app = apps.get_app_config('{plugin_id}')
        self.assertEqual(app.verbose_name, '{plugin_name}')
''')

        # Crear README.md
        with open(plugin_dir / 'README.md', 'w') as f:
            f.write(f'''# {plugin_name}

{description}

## Instalación

Este plugin está en desarrollo. Para probarlo:

1. Asegúrate de que el Hub esté en modo desarrollo (`CPOS_DEV_MODE=true`)
2. El plugin se cargará automáticamente desde `plugins/{plugin_id}/`

## Desarrollo

### Estructura

```
{plugin_id}/
├── plugin.json          # Metadata del plugin
├── apps.py             # Configuración Django
├── models.py           # Modelos de datos
├── views.py            # Vistas
├── urls.py             # URLs
├── templates/          # Templates HTML
├── static/             # CSS, JS, imágenes
├── migrations/         # Migraciones de BD
├── management/         # Management commands
└── tests/              # Tests
```

### Comandos útiles

```bash
# Crear migraciones
python manage.py makemigrations {plugin_id}

# Aplicar migraciones
python manage.py migrate {plugin_id}

# Ejecutar tests
pytest plugins/{plugin_id}/tests/

# Validar plugin
python manage.py validate_plugin {plugin_id}

# Firmar plugin (para distribución)
python manage.py sign_plugin {plugin_id}

# Empaquetar plugin
python manage.py package_plugin {plugin_id}
```

## Autor

{author}

## Licencia

Ver LICENSE
''')

        # Crear .gitignore
        with open(plugin_dir / '.gitignore', 'w') as f:
            f.write('''# Python
__pycache__/
*.py[cod]
*$py.class
*.so

# Django
*.log
db.sqlite3
media/

# Tests
.pytest_cache/
.coverage
htmlcov/

# IDE
.vscode/
.idea/
*.swp
*.swo
*~

# OS
.DS_Store
Thumbs.db

# Plugin build
*.zip
.signature
''')

        self.stdout.write(self.style.SUCCESS('\n✅ Plugin creado exitosamente!\n'))
        self.stdout.write(self.style.WARNING('📋 Próximos pasos:\n'))
        self.stdout.write(f'   1. cd plugins/{plugin_id}')
        self.stdout.write(f'   2. git init && git add . && git commit -m "Initial commit"')
        self.stdout.write(f'   3. Edita {plugin_id}/models.py, views.py, templates/')
        self.stdout.write(f'   4. python manage.py makemigrations {plugin_id}')
        self.stdout.write(f'   5. python manage.py migrate {plugin_id}')
        self.stdout.write(f'   6. python manage.py validate_plugin {plugin_id}')
        self.stdout.write(f'   7. Prueba en http://localhost:8001/{plugin_id}/')
        self.stdout.write('')
