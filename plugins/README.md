# CPOS Hub - Plugin Development Guide

Este directorio es para **desarrollo de plugins**. Cada plugin es un Django app independiente con su propio repositorio git.

## 📋 Tabla de Contenidos

- [Arquitectura del Sistema de Plugins](#arquitectura-del-sistema-de-plugins)
- [Desarrollo Local](#desarrollo-local)
- [Estructura de un Plugin](#estructura-de-un-plugin)
- [Management Commands](#management-commands)
- [Dependencias Permitidas](#dependencias-permitidas)
- [Persistencia de Datos](#persistencia-de-datos)
- [Firma Digital y Distribución](#firma-digital-y-distribución)
- [Buenas Prácticas](#buenas-prácticas)

---

## Arquitectura del Sistema de Plugins

### Dos Modos de Operación

#### 🔧 Modo Desarrollo (`CPOS_DEV_MODE=true`)
- Plugins se cargan desde **dos ubicaciones**:
  1. `./plugins/` - Repositorios locales (desarrollo)
  2. `~/.cpos-hub/plugins/` - Plugins instalados
- Sin firma digital requerida
- Hot reload automático (detecta cambios)
- Validación relajada

#### 🚀 Modo Producción (PyInstaller Build)
- Plugins se cargan solo desde `~/.cpos-hub/plugins/`
- Firma digital **obligatoria** (RSA-SHA256)
- Sin hot reload
- Validación estricta

### Ubicaciones de Datos

Los plugins **NO deben** guardar datos dentro de su propio directorio. Usar estas ubicaciones:

```python
from django.conf import settings

# Datos persistentes del plugin
data_dir = settings.PLUGIN_DATA_ROOT / 'mi-plugin'
data_dir.mkdir(parents=True, exist_ok=True)

# Archivos media (imágenes, uploads)
media_dir = settings.PLUGIN_MEDIA_ROOT / 'mi-plugin'
media_dir.mkdir(parents=True, exist_ok=True)
```

**Ubicaciones por plataforma:**
- Windows: `C:\Users\<user>\AppData\Local\CPOSHub\plugins\`
- macOS: `~/Library/Application Support/CPOSHub/plugins/`
- Linux: `~/.cpos-hub/plugins/`

---

## Desarrollo Local

### 1. Crear un Nuevo Plugin

```bash
# Ubicarte en la carpeta hub
cd hub

# Activar entorno virtual
source .venv/bin/activate

# Crear plugin desde template
python manage.py create_plugin products --name "Products Manager" --author "Tu Nombre"

# Resultado:
# plugins/
# └── products/
#     ├── plugin.json
#     ├── apps.py
#     ├── models.py
#     ├── views.py
#     ├── urls.py
#     ├── templates/
#     ├── static/
#     ├── migrations/
#     ├── tests/
#     └── README.md
```

### 2. Inicializar Git para el Plugin

```bash
cd plugins/products
git init
git add .
git commit -m "Initial commit"

# Opcional: crear repositorio remoto
git remote add origin https://github.com/tu-usuario/cpos-plugin-products.git
git push -u origin main
```

### 3. Desarrollar el Plugin

```bash
# Editar modelos, vistas, templates
nano models.py
nano views.py
nano templates/products/index.html

# Crear migraciones
python manage.py makemigrations products

# Aplicar migraciones
python manage.py migrate products

# Ejecutar tests
pytest plugins/products/tests/
```

### 4. Probar en el Hub

```bash
# Iniciar Hub en desarrollo
python manage.py runserver 8001

# Acceder al plugin
# http://localhost:8001/products/
```

---

## Estructura de un Plugin

### Estructura Completa

```
products/
├── plugin.json              # ⚠️ REQUERIDO - Metadata del plugin
├── __init__.py              # ⚠️ REQUERIDO - Package init
├── apps.py                  # ⚠️ REQUERIDO - Django app config
├── models.py                # Modelos de datos
├── views.py                 # Vistas
├── urls.py                  # URLs
├── admin.py                 # Django admin (opcional)
├── forms.py                 # Formularios (opcional)
├── signals.py               # Signals (opcional)
├── utils.py                 # Utilidades (opcional)
│
├── templates/
│   └── products/            # ⚠️ Debe coincidir con plugin_id
│       ├── index.html
│       ├── list.html
│       └── detail.html
│
├── static/
│   └── products/            # ⚠️ Debe coincidir con plugin_id
│       ├── css/
│       │   └── products.css
│       ├── js/
│       │   └── products.js
│       └── img/
│           └── icon.png
│
├── migrations/
│   └── __init__.py
│
├── management/
│   └── commands/
│       └── __init__.py
│
├── tests/
│   ├── __init__.py
│   ├── test_models.py
│   ├── test_views.py
│   └── test_basic.py
│
├── README.md                # Documentación del plugin
├── LICENSE                  # Licencia
└── .gitignore              # Git ignore
```

### plugin.json - Formato Completo

```json
{
  "plugin_id": "products",
  "name": "Products Manager",
  "version": "1.0.0",
  "description": "Gestión de productos e inventario para CPOS Hub",
  "author": "CPOS Team",
  "author_email": "plugins@erplora.com",
  "license": "BUSL-1.1",
  "homepage": "https://github.com/cpos/cpos-plugin-products",

  "dependencies": {
    "python": [
      "Pillow>=10.0.0",
      "openpyxl>=3.1.0",
      "qrcode>=7.4.0"
    ],
    "plugins": [
      "cpos-plugin-shared>=1.0.0"
    ]
  },

  "compatibility": {
    "min_cpos_version": "1.0.0",
    "max_cpos_version": "2.0.0"
  },

  "permissions": {
    "database": true,
    "filesystem": false,
    "network": false,
    "hardware": false
  },

  "menu": {
    "label": "Products",
    "icon": "cube-outline",
    "url": "/products/",
    "order": 100,
    "show": true
  }
}
```

### models.py - Ejemplo con Prefijos

```python
"""
Modelos del plugin Products Manager

⚠️ IMPORTANTE: Usa prefijos en db_table para evitar conflictos
"""

from django.db import models
from django.conf import settings


class Product(models.Model):
    """Modelo de producto"""
    name = models.CharField(max_length=255)
    sku = models.CharField(max_length=100, unique=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    stock = models.IntegerField(default=0)

    # Media: usar PLUGIN_MEDIA_ROOT
    image = models.ImageField(upload_to='plugins/products/images/', blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True
    )

    class Meta:
        db_table = 'products_product'  # ⚠️ Prefijo para evitar conflictos
        ordering = ['-created_at']
        verbose_name = 'Product'
        verbose_name_plural = 'Products'

    def __str__(self):
        return f"{self.sku} - {self.name}"

    def save_barcode(self):
        """Ejemplo: guardar datos en PLUGIN_DATA_ROOT"""
        from pathlib import Path
        from django.conf import settings

        data_dir = Path(settings.PLUGIN_DATA_ROOT) / 'products' / 'barcodes'
        data_dir.mkdir(parents=True, exist_ok=True)

        barcode_file = data_dir / f"{self.sku}.txt"
        barcode_file.write_text(self.sku)
```

### views.py - Ejemplo con Ionic + Alpine.js

```python
"""
Vistas del plugin Products Manager
"""

from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from .models import Product


@login_required
def index(request):
    """Vista principal del plugin"""
    products = Product.objects.all()[:10]

    context = {
        'plugin_name': 'Products Manager',
        'products': products,
    }
    return render(request, 'products/index.html', context)


@login_required
def product_list_api(request):
    """API para listado de productos (HTMX/Alpine.js)"""
    products = Product.objects.all()

    data = {
        'products': [
            {
                'id': p.id,
                'name': p.name,
                'sku': p.sku,
                'price': str(p.price),
                'stock': p.stock,
            }
            for p in products
        ]
    }
    return JsonResponse(data)
```

### templates/products/index.html - Ejemplo

```html
{% extends "core/app_base.html" %}
{% load static %}

{% block content %}
<ion-content>
    <div class="ion-padding" x-data="productsData()">

        <!-- Header Card -->
        <ion-card>
            <ion-card-header>
                <ion-card-title>Products Manager</ion-card-title>
                <ion-card-subtitle>Gestión de productos e inventario</ion-card-subtitle>
            </ion-card-header>
        </ion-card>

        <!-- Product List -->
        <ion-card>
            <ion-card-header>
                <ion-card-title>Products</ion-card-title>
            </ion-card-header>
            <ion-card-content>

                <!-- Search -->
                <ion-searchbar
                    x-model="search"
                    placeholder="Buscar producto..."
                    @input="filterProducts()">
                </ion-searchbar>

                <!-- List -->
                <ion-list>
                    <template x-for="product in filteredProducts" :key="product.id">
                        <ion-item>
                            <ion-label>
                                <h2 x-text="product.name"></h2>
                                <p x-text="'SKU: ' + product.sku"></p>
                            </ion-label>
                            <ion-note slot="end" x-text="'$' + product.price"></ion-note>
                        </ion-item>
                    </template>
                </ion-list>

            </ion-card-content>
        </ion-card>

    </div>
</ion-content>
{% endblock %}

{% block scripts %}
<script>
function productsData() {
    return {
        products: {{ products|safe }},
        filteredProducts: [],
        search: '',

        filterProducts() {
            if (!this.search) {
                this.filteredProducts = this.products;
                return;
            }

            const term = this.search.toLowerCase();
            this.filteredProducts = this.products.filter(p =>
                p.name.toLowerCase().includes(term) ||
                p.sku.toLowerCase().includes(term)
            );
        },

        init() {
            this.filteredProducts = this.products;
        }
    }
}
</script>
{% endblock %}
```

---

## Management Commands

### create_plugin - Crear Plugin

```bash
python manage.py create_plugin <plugin_id> [options]

# Opciones:
#   --name "Plugin Name"      # Nombre descriptivo
#   --author "Author Name"    # Nombre del autor
#   --description "Desc"      # Descripción corta

# Ejemplos:
python manage.py create_plugin products --name "Products Manager"
python manage.py create_plugin restaurant-pos --name "Restaurant POS" --author "John Doe"
```

**Resultado:**
- Crea estructura completa del plugin
- Genera archivos base (models, views, urls, templates)
- Crea tests básicos
- Genera README.md y .gitignore

### validate_plugin - Validar Plugin

```bash
python manage.py validate_plugin <plugin_id> [options]

# Opciones:
#   --strict    # Modo estricto (falla en warnings)

# Ejemplos:
python manage.py validate_plugin products
python manage.py validate_plugin products --strict
```

**Validaciones:**
- ✓ Estructura de archivos requerida
- ✓ plugin.json válido y completo
- ✓ Dependencias en whitelist
- ✓ Sin conflictos de base de datos
- ✓ Sintaxis Python correcta
- ✓ Tests ejecutables
- ✓ Templates válidos

### sign_plugin - Firmar Plugin

```bash
python manage.py sign_plugin <plugin_id> [options]

# Opciones:
#   --key-file path/to/key.pem    # Clave privada RSA (genera una si no existe)
#   --force                        # Re-firmar aunque ya tenga firma

# Ejemplos:
python manage.py sign_plugin products
python manage.py sign_plugin products --key-file ~/.cpos-dev/signing-key.pem
```

**Proceso:**
1. Carga o genera clave RSA-4096
2. Calcula hash SHA256 del plugin
3. Firma con RSA-SHA256
4. Guarda `.signature` con clave pública

**⚠️ IMPORTANTE:**
- Clave privada: `~/.cpos-dev/signing-key.pem` (NO incluir en repo)
- Clave pública: incluida en `.signature` (SÍ incluir)

### package_plugin - Empaquetar Plugin

```bash
python manage.py package_plugin <plugin_id> [options]

# Opciones:
#   --output-dir path/      # Directorio de salida (default: ~/Downloads/)
#   --skip-validation       # Omitir validación

# Ejemplos:
python manage.py package_plugin products
python manage.py package_plugin products --output-dir ~/Desktop/
```

**Resultado:**
- Valida plugin automáticamente
- Crea ZIP: `<plugin_id>-<version>.zip`
- Incluye `.signature` si existe
- Excluye archivos de desarrollo

---

## Dependencias Permitidas

Los plugins pueden usar **25 librerías Python pre-empaquetadas** en la app:

### Críticas (13)
- `Pillow` - Imágenes (productos, categorías)
- `qrcode` - QR codes (mesas, productos, pagos)
- `python-barcode` - Códigos de barras (EAN, UPC)
- `openpyxl` - Excel (import/export)
- `reportlab` - PDFs (tickets, facturas)
- `python-escpos` - Impresoras térmicas
- `lxml` - XML (facturación electrónica)
- `xmltodict` - XML parsing
- `signxml` - Firmas digitales XML
- `cryptography` - Cifrado, certificados
- `zeep` - SOAP (APIs Hacienda/SAT/AFIP)
- `requests` - HTTP requests
- `websockets` - WebSocket

### Importantes (10)
- `python-dateutil`, `pytz`, `phonenumbers` - Fechas & localización
- `stripe` - Pagos
- `pandas`, `numpy` - Análisis de datos
- `pyserial` - Hardware (básculas, cajones)
- `email-validator`, `python-slugify`, `pydantic` - Utils

### Útiles (2)
- `beautifulsoup4` - HTML parsing
- `PyPDF2` - PDF manipulación

**Uso en plugin.json:**

```json
{
  "dependencies": {
    "python": [
      "Pillow>=10.0.0",
      "qrcode>=7.4.0",
      "openpyxl>=3.1.0"
    ]
  }
}
```

---

## Persistencia de Datos

### ⚠️ REGLA IMPORTANTE

**NO guardar datos dentro del directorio del plugin** porque:
- Los plugins se actualizan reemplazando el directorio completo
- Los datos se perderían en cada actualización
- El directorio del plugin es solo para código

### ✅ Ubicaciones Correctas

```python
from django.conf import settings
from pathlib import Path

# 1. Base de datos SQLite (mejor opción)
# Django ORM maneja migraciones automáticamente
class Product(models.Model):
    name = models.CharField(max_length=255)
    # Los datos se guardan en ~/.cpos-hub/db/db.sqlite3

# 2. Archivos de datos (config, cache, exports)
data_dir = Path(settings.PLUGIN_DATA_ROOT) / 'mi-plugin'
data_dir.mkdir(parents=True, exist_ok=True)

config_file = data_dir / 'config.json'
config_file.write_text(json.dumps({'setting': 'value'}))

# 3. Media files (imágenes, uploads)
media_dir = Path(settings.PLUGIN_MEDIA_ROOT) / 'mi-plugin'
media_dir.mkdir(parents=True, exist_ok=True)

# O usar Django ImageField/FileField
class Product(models.Model):
    image = models.ImageField(upload_to='plugins/mi-plugin/images/')
    # Se guarda en ~/.cpos-hub/media/plugins/mi-plugin/images/
```

### Ubicaciones por Plataforma

| Plataforma | Base Dir |
|------------|----------|
| Windows | `C:\Users\<user>\AppData\Local\CPOSHub\` |
| macOS | `~/Library/Application Support/CPOSHub/` |
| Linux | `~/.cpos-hub/` |

**Estructura completa:**

```
~/.cpos-hub/  (o equivalente)
├── db/
│   └── db.sqlite3                    # Base de datos SQLite
├── plugins/
│   ├── data/
│   │   └── mi-plugin/               # Datos del plugin
│   │       ├── config.json
│   │       ├── cache/
│   │       └── exports/
│   └── installed/
│       └── mi-plugin/               # Código del plugin instalado
├── media/
│   └── plugins/
│       └── mi-plugin/               # Media del plugin
│           └── images/
├── reports/
├── logs/
└── backups/
```

---

## Firma Digital y Distribución

### 1. Desarrollo Local (Sin Firma)

```bash
# Crear y probar plugin
python manage.py create_plugin products
python manage.py validate_plugin products

# Probar localmente
python manage.py runserver 8001
```

### 2. Preparar para Distribución

```bash
# Validar en modo estricto
python manage.py validate_plugin products --strict

# Firmar (genera clave si no existe)
python manage.py sign_plugin products

# Empaquetar
python manage.py package_plugin products
```

**Resultado:**
- `~/Downloads/products-1.0.0.zip` - Listo para distribución
- Incluye `.signature` con clave pública

### 3. Distribución

**Opción 1: Cloud (Privado/Pago)**

```bash
# 1. Subir a https://erplora.com
# 2. Dashboard → Plugins → Mis Plugins → Subir
# 3. Configurar precio y visibilidad
```

**Opción 2: GitHub Release (Público)**

```bash
cd plugins/products
git tag v1.0.0
git push origin v1.0.0

# Crear GitHub Release
# Adjuntar products-1.0.0.zip
```

**Opción 3: Distribución Directa**

```bash
# Compartir ZIP directamente
# Usuarios instalan desde Hub con URL del ZIP
```

### 4. Actualización

```bash
# Incrementar versión en plugin.json
# "version": "1.0.0" → "1.1.0"

# Crear migraciones si hay cambios en modelos
python manage.py makemigrations products

# Re-validar, firmar y empaquetar
python manage.py validate_plugin products --strict
python manage.py sign_plugin products --force
python manage.py package_plugin products
```

---

## Buenas Prácticas

### 1. Nombres de Tabla

```python
# ❌ MAL - Sin prefijo
class Product(models.Model):
    class Meta:
        db_table = 'product'  # Conflicto con otros plugins

# ✅ BIEN - Con prefijo del plugin
class Product(models.Model):
    class Meta:
        db_table = 'products_product'  # Único
```

### 2. Dependencias

```python
# ❌ MAL - Dependencia no permitida
{
  "dependencies": {
    "python": ["tensorflow>=2.0.0"]  # NO está en whitelist
  }
}

# ✅ BIEN - Solo dependencias permitidas
{
  "dependencies": {
    "python": [
      "Pillow>=10.0.0",
      "qrcode>=7.4.0"
    ]
  }
}
```

### 3. Persistencia

```python
# ❌ MAL - Guardar en directorio del plugin
plugin_dir = Path(__file__).parent
config_file = plugin_dir / 'config.json'  # Se pierde en update

# ✅ BIEN - Usar PLUGIN_DATA_ROOT
from django.conf import settings
data_dir = settings.PLUGIN_DATA_ROOT / 'mi-plugin'
config_file = data_dir / 'config.json'  # Persiste en updates
```

### 4. Media Files

```python
# ❌ MAL - Guardar en static/
image_path = 'static/mi-plugin/uploads/image.jpg'

# ✅ BIEN - Usar ImageField con upload_to
class Product(models.Model):
    image = models.ImageField(upload_to='plugins/mi-plugin/images/')
```

### 5. Testing

```python
# tests/test_models.py
import pytest
from django.test import TestCase
from ..models import Product


class ProductTestCase(TestCase):
    """Tests del modelo Product"""

    def test_create_product(self):
        """Verifica que se puede crear un producto"""
        product = Product.objects.create(
            name='Test Product',
            sku='TEST-001',
            price=10.00
        )
        self.assertEqual(product.name, 'Test Product')
        self.assertEqual(str(product), 'TEST-001 - Test Product')
```

### 6. Versioning

```json
{
  "version": "1.2.3"
}
```

**Semantic Versioning:**
- `MAJOR.MINOR.PATCH`
- `1.0.0` → Primera versión estable
- `1.0.1` → Bug fix
- `1.1.0` → Nueva funcionalidad (compatible)
- `2.0.0` → Breaking change

---

## Ejemplos de Plugins

### Plugin Mínimo (Hello World)

```bash
python manage.py create_plugin hello --name "Hello World"
```

**Estructura creada:**
- `plugin.json` - Metadata
- `views.py` - Vista básica
- `templates/hello/index.html` - Template
- Tests básicos

### Plugin con Modelos (Products)

```bash
python manage.py create_plugin products --name "Products Manager"

# Editar models.py
# Crear migraciones
python manage.py makemigrations products
python manage.py migrate products
```

### Plugin con API (Restaurant POS)

```bash
python manage.py create_plugin restaurant --name "Restaurant POS"

# Agregar views API
# Agregar templates con HTMX/Alpine.js
# Agregar static files (CSS/JS)
```

---

## Troubleshooting

### Error: "Dependencia no permitida"

```bash
# Verifica que la dependencia esté en whitelist
python manage.py validate_plugin mi-plugin

# Ver lista completa de dependencias permitidas
grep -A 30 "PLUGIN_ALLOWED_DEPENDENCIES" config/settings.py
```

### Error: "Conflicto de tabla"

```python
# Asegúrate de usar prefijo en db_table
class Meta:
    db_table = 'mi_plugin_tabla'  # Con prefijo
```

### Error: "Plugin sin firma"

```bash
# Firmar plugin antes de empaquetar
python manage.py sign_plugin mi-plugin
python manage.py package_plugin mi-plugin
```

---

## Recursos Adicionales

- **Documentación Django**: https://docs.djangoproject.com/
- **Ionic Framework**: https://ionicframework.com/docs/components
- **Alpine.js**: https://alpinejs.dev/
- **HTMX**: https://htmx.org/docs/

---

## Soporte

¿Problemas o dudas?

- GitHub Issues: https://github.com/cpos/cpos-hub/issues
- Email: plugins@erplora.com
- Docs: https://docs.erplora.com/plugins/

---

**Última actualización:** 2025-01-10
