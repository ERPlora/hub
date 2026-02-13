"""
Management command para crear un nuevo module desde template.

Uso:
    python manage.py create_module <module_id> [--name "Module Name"] [--author "Author"]

Ejemplos:
    python manage.py create_module products --name "Products Manager" --author "CPOS Team"
    python manage.py create_module restaurant-pos --name "Restaurant POS" --author "John Doe"
"""

from django.core.management.base import BaseCommand, CommandError
from pathlib import Path
from django.conf import settings
import json
import shutil


class Command(BaseCommand):
    help = 'Crea un nuevo module desde template'

    def add_arguments(self, parser):
        parser.add_argument(
            'module_id',
            type=str,
            help='ID único del module (ej: products, restaurant-pos)'
        )
        parser.add_argument(
            '--name',
            type=str,
            default=None,
            help='Nombre descriptivo del module'
        )
        parser.add_argument(
            '--author',
            type=str,
            default='CPOS Module Developer',
            help='Nombre del autor del module'
        )
        parser.add_argument(
            '--description',
            type=str,
            default='Module description',
            help='Descripción corta del module'
        )

    def handle(self, *args, **options):
        module_id = options['module_id']
        module_name = options['name'] or module_id.replace('-', ' ').replace('_', ' ').title()
        author = options['author']
        description = options['description']

        # Validar module_id
        if not module_id.replace('-', '').replace('_', '').isalnum():
            raise CommandError('module_id debe contener solo letras, números, guiones y guiones bajos')

        # Ruta base para modules en desarrollo
        base_dir = Path(settings.BASE_DIR)
        modules_dev_dir = base_dir / 'modules'
        module_dir = modules_dev_dir / module_id

        if module_dir.exists():
            raise CommandError(f'El module {module_id} ya existe en {module_dir}')

        self.stdout.write(self.style.SUCCESS(f'\n📦 Creando module: {module_name}'))
        self.stdout.write(f'   ID: {module_id}')
        self.stdout.write(f'   Autor: {author}')
        self.stdout.write(f'   Ubicación: {module_dir}\n')

        # Crear estructura de directorios
        module_dir.mkdir(parents=True, exist_ok=True)
        (module_dir / 'templates' / module_id).mkdir(parents=True, exist_ok=True)
        (module_dir / 'static' / module_id / 'css').mkdir(parents=True, exist_ok=True)
        (module_dir / 'static' / module_id / 'js').mkdir(parents=True, exist_ok=True)
        (module_dir / 'migrations').mkdir(parents=True, exist_ok=True)
        (module_dir / 'management' / 'commands').mkdir(parents=True, exist_ok=True)
        (module_dir / 'tests').mkdir(parents=True, exist_ok=True)

        # Crear module.json
        module_json = {
            "module_id": module_id,
            "name": module_name,
            "version": "0.1.0",
            "description": description,
            "author": author,
            "dependencies": {
                "python": [],
                "modules": []
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
                "label": module_name,
                "icon": "cube-outline",
                "url": f"/{module_id}/"
            }
        }

        with open(module_dir / 'module.json', 'w') as f:
            json.dump(module_json, f, indent=2)

        # Crear __init__.py
        with open(module_dir / '__init__.py', 'w') as f:
            f.write(f'"""Module {module_name}"""\n')
            f.write(f"default_app_config = '{module_id}.apps.{module_id.replace('-', '_').title().replace('_', '')}Config'\n")

        # Crear apps.py
        app_class_name = module_id.replace('-', '_').title().replace('_', '')
        with open(module_dir / 'apps.py', 'w') as f:
            f.write(f'''from django.apps import AppConfig


class {app_class_name}Config(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = '{module_id}'
    verbose_name = '{module_name}'

    def ready(self):
        """Código que se ejecuta cuando el module se carga"""
        pass
''')

        # Crear models.py
        with open(module_dir / 'models.py', 'w') as f:
            f.write(f'''"""
Modelos del module {module_name}

IMPORTANTE: Usa prefijos en db_table para evitar conflictos.
Por defecto Django usa: {module_id}_modelname
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
#         db_table = '{module_id}_product'  # Prefijo para evitar conflictos
#         ordering = ['-created_at']
#
#     def __str__(self):
#         return self.name
''')

        # Crear views.py
        with open(module_dir / 'views.py', 'w') as f:
            f.write(f'''"""
Vistas del module {module_name}
"""

from django.shortcuts import render
from django.contrib.auth.decorators import login_required


@login_required
def index(request):
    """Vista principal del module"""
    context = {{
        'module_name': '{module_name}',
    }}
    return render(request, '{module_id}/index.html', context)
''')

        # Crear urls.py
        with open(module_dir / 'urls.py', 'w') as f:
            f.write(f'''"""
URLs del module {module_name}
"""

from django.urls import path
from . import views

app_name = '{module_id}'

urlpatterns = [
    path('', views.index, name='index'),
]
''')

        # Crear template index.html
        with open(module_dir / 'templates' / module_id / 'index.html', 'w') as f:
            f.write(f'''{{%extends "core/app_base.html"%}}
{{%load static%}}

{{%block content%}}
<div class="content">
    <div class="card">
        <div class="card-header">
            <h3 class="card-title">{module_name}</h3>
        </div>
        <div class="card-body">
            <p>¡Module creado exitosamente!</p>
            <p>Comienza a desarrollar tu module aquí.</p>
        </div>
    </div>
</div>
{{%endblock%}}
''')

        # Crear migrations/__init__.py
        with open(module_dir / 'migrations' / '__init__.py', 'w') as f:
            f.write('')

        # Crear management/__init__.py
        with open(module_dir / 'management' / '__init__.py', 'w') as f:
            f.write('')
        with open(module_dir / 'management' / 'commands' / '__init__.py', 'w') as f:
            f.write('')

        # Crear tests/__init__.py
        with open(module_dir / 'tests' / '__init__.py', 'w') as f:
            f.write('')

        # Crear test_basic.py
        with open(module_dir / 'tests' / 'test_basic.py', 'w') as f:
            f.write(f'''"""
Tests básicos del module {module_name}
"""

import pytest
from django.test import TestCase


class BasicTestCase(TestCase):
    """Tests básicos del module"""

    def test_module_loads(self):
        """Verifica que el module se carga correctamente"""
        from django.apps import apps
        app = apps.get_app_config('{module_id}')
        self.assertEqual(app.verbose_name, '{module_name}')
''')

        # Crear README.md
        with open(module_dir / 'README.md', 'w') as f:
            f.write(f'''# {module_name}

{description}

## Instalación

Este module está en desarrollo. Para probarlo:

1. Asegúrate de que el Hub esté en modo desarrollo (`CPOS_DEV_MODE=true`)
2. El module se cargará automáticamente desde `modules/{module_id}/`

## Desarrollo

### Estructura

```
{module_id}/
├── module.json          # Metadata del module
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
python manage.py makemigrations {module_id}

# Aplicar migraciones
python manage.py migrate {module_id}

# Ejecutar tests
pytest modules/{module_id}/tests/

# Validar module
python manage.py validate_module {module_id}

# Firmar module (para distribución)
python manage.py sign_module {module_id}

# Empaquetar module
python manage.py package_module {module_id}
```

## Autor

{author}

## Licencia

Ver LICENSE
''')

        # Crear .gitignore
        with open(module_dir / '.gitignore', 'w') as f:
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

# Module build
*.zip
.signature
''')

        self.stdout.write(self.style.SUCCESS('\n✅ Module creado exitosamente!\n'))
        self.stdout.write(self.style.WARNING('📋 Próximos pasos:\n'))
        self.stdout.write(f'   1. cd modules/{module_id}')
        self.stdout.write('   2. git init && git add . && git commit -m "Initial commit"')
        self.stdout.write(f'   3. Edita {module_id}/models.py, views.py, templates/')
        self.stdout.write(f'   4. python manage.py makemigrations {module_id}')
        self.stdout.write(f'   5. python manage.py migrate {module_id}')
        self.stdout.write(f'   6. python manage.py validate_module {module_id}')
        self.stdout.write(f'   7. Prueba en http://localhost:8001/{module_id}/')
        self.stdout.write('')
