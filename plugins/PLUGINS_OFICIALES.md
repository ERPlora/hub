# Plugins Oficiales CPOS

Este documento describe los **plugins oficiales** que extienden la funcionalidad del Hub CPOS.

## 🎯 Arquitectura del Sistema

CPOS Hub sigue una arquitectura **core + plugins**:

```
┌─────────────────────────────────────┐
│         CPOS Hub Core (85%)         │
│  ─────────────────────────────────  │
│  ✅ Login (PIN + Cloud)             │
│  ✅ Dashboard                       │
│  ✅ Settings (Hub + Store)          │
│  ✅ Employee Management             │
│  ✅ Plugin Management UI            │
│  ✅ Session Management              │
│  ✅ i18n (en/es)                    │
│  ✅ Theme toggle                    │
│  ✅ JWT Offline Mode                │
└─────────────────────────────────────┘
              ↓ Plugins
┌─────────────────────────────────────┐
│      🔌 Plugins Oficiales (0%)      │
│  ─────────────────────────────────  │
│  ❌ cpos-plugin-pos                 │
│  ❌ cpos-plugin-products            │
│  ❌ cpos-plugin-hardware            │
│  ❌ cpos-plugin-backups             │
│  ❌ cpos-plugin-facturacion-mx      │
└─────────────────────────────────────┘
```

### Principio de Diseño

**Hub Core provee la infraestructura, plugins proveen la funcionalidad de negocio.**

- ✅ **Hub Core (85% completo)**: Layout, autenticación, configuración, gestión de plugins
- ❌ **Plugins Oficiales (0% completo)**: POS, inventario, hardware, backups, facturación

## 📦 Plugins Oficiales Pendientes

### 1. `cpos-plugin-pos` - Point of Sale (CRÍTICO)

**Prioridad:** CRÍTICA ⚠️ (Bloqueante para MVP)
**Estado:** 0%
**Estimación:** 5-7 días

**Funcionalidad:**
- Interfaz de punto de venta (product grid + cart)
- Procesamiento de ventas (efectivo, tarjeta)
- Generación de tickets (PDF/print)
- Lista de ventas del día
- Integración con productos y hardware

**Modelos:**
```python
class Sale(models.Model):
    date = models.DateTimeField(auto_now_add=True)
    user = models.ForeignKey(LocalUser, on_delete=CASCADE)
    subtotal = models.DecimalField(max_digits=10, decimal_places=2)
    tax = models.DecimalField(max_digits=10, decimal_places=2)
    total = models.DecimalField(max_digits=10, decimal_places=2)
    payment_method = models.CharField(max_length=50)  # cash, card

class SaleItem(models.Model):
    sale = models.ForeignKey(Sale, on_delete=CASCADE, related_name='items')
    product = models.ForeignKey('products.Product', on_delete=CASCADE)
    quantity = models.IntegerField()
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    total = models.DecimalField(max_digits=10, decimal_places=2)
```

**Dependencies:**
```json
{
  "plugin_id": "cpos-plugin-pos",
  "dependencies": {
    "python": ["reportlab>=4.0.0"],
    "plugins": ["cpos-plugin-products>=1.0.0"]
  }
}
```

**Archivos:**
- `plugins/cpos-plugin-pos/models.py` - Sale, SaleItem, Payment
- `plugins/cpos-plugin-pos/views.py` - POS views y APIs
- `plugins/cpos-plugin-pos/templates/pos/index.html` - UI POS con Alpine.js
- `plugins/cpos-plugin-pos/static/pos/css/pos.css` - Estilos

---

### 2. `cpos-plugin-products` - Gestión de Productos

**Prioridad:** CRÍTICA ⚠️ (Requerido por POS)
**Estado:** 0%
**Estimación:** 3-4 días

**Funcionalidad:**
- CRUD de productos
- Categorías
- Precios e inventario
- Búsqueda y filtros
- Import/export Excel

**Modelos:**
```python
class Category(models.Model):
    name = models.CharField(max_length=255)
    icon = models.CharField(max_length=50, default='pricetag-outline')

class Product(models.Model):
    name = models.CharField(max_length=255)
    category = models.ForeignKey(Category, on_delete=SET_NULL, null=True)
    sku = models.CharField(max_length=100, unique=True)
    barcode = models.CharField(max_length=100, blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    cost = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    stock = models.IntegerField(default=0)
    image = models.ImageField(upload_to='products/', blank=True)
```

**Dependencies:**
```json
{
  "plugin_id": "cpos-plugin-products",
  "dependencies": {
    "python": [
      "Pillow>=10.0.0",
      "openpyxl>=3.1.0",
      "python-barcode>=0.15.0"
    ]
  }
}
```

---

### 3. `cpos-plugin-hardware` - Hardware POS

**Prioridad:** ALTA
**Estado:** 0%
**Estimación:** 4-5 días

**Funcionalidad:**
- Impresoras térmicas ESC/POS (USB, LAN, Serial)
- Scanners de códigos de barras
- Cajón de dinero
- Display de cliente (pole display)
- Báscula electrónica

**Servicios:**
```python
# services/printer.py
class ThermalPrinterService:
    def detect_printers(self) -> list[Printer]:
        # Auto-detect via USB, LAN, Serial
        pass

    def print_receipt(self, sale_data: dict):
        # Usar python-escpos
        pass

    def open_cash_drawer(self):
        # Comando ESC/POS
        pass

# services/scanner.py
class BarcodeScannerService:
    def detect_scanners(self) -> list[Scanner]:
        pass

    def start_listening(self, callback):
        # Escuchar eventos del scanner
        pass
```

**Dependencies (ya pre-empaquetadas):**
```json
{
  "plugin_id": "cpos-plugin-hardware",
  "dependencies": {
    "python": [
      "python-escpos>=3.0",
      "pyserial>=3.5",
      "pyusb>=1.2.1",
      "evdev>=1.6.0",
      "pywinusb>=0.4.2"
    ]
  }
}
```

**Documentación:** Ver [HARDWARE_POS.md](../docs/HARDWARE_POS.md) para ejemplos completos.

---

### 4. `cpos-plugin-backups` - Sistema de Backups

**Prioridad:** ALTA
**Estado:** 0%
**Estimación:** 5-7 días

**Funcionalidad:**
- Backup completo de SQLite
- Backup de media files (logos, avatars)
- Compresión con gzip
- Encriptación AES-256
- Upload a Cloud (S3/MinIO)
- Scheduling automático (diario/semanal/mensual)

**Servicios:**
```python
# services/backup_manager.py
class BackupManager:
    def create_backup(self) -> BackupFile:
        # Backup SQLite + media → .tar.gz.enc
        pass

    def upload_to_cloud(self, backup_file: BackupFile):
        # POST /api/backups/upload/
        pass

    def schedule_backup(self, frequency: str):
        # Usar APScheduler
        pass
```

**Dependencies:**
```json
{
  "plugin_id": "cpos-plugin-backups",
  "dependencies": {
    "python": [
      "boto3>=1.34.0",
      "cryptography>=42.0.0",
      "APScheduler>=3.10.0"
    ]
  }
}
```

**Cloud API:**
- `POST /api/backups/upload/` - Recibir backup del Hub
- `GET /api/backups/` - Listar backups disponibles
- `POST /api/backups/{id}/restore/` - Generar presigned URL para restaurar

---

### 5. `cpos-plugin-facturacion-mx` - Facturación Electrónica México

**Prioridad:** MEDIA
**Estado:** 0%
**Estimación:** 7-10 días

**Funcionalidad:**
- Generación de CFDi 4.0
- Timbrado con PAC (Proveedor Autorizado de Certificación)
- Validación de RFC
- Generación de PDF
- Envío por email
- Cancelación de facturas

**Servicios:**
```python
# services/cfdi_generator.py
class CFDIGenerator:
    def generate_cfdi(self, sale: Sale) -> CFDI:
        # Generar XML CFDi 4.0
        pass

    def sign_cfdi(self, cfdi: CFDI, certificate) -> str:
        # Firmar con certificado .cer + .key
        pass

    def stamp_cfdi(self, cfdi_xml: str) -> str:
        # Timbrar con PAC
        pass
```

**Dependencies:**
```json
{
  "plugin_id": "cpos-plugin-facturacion-mx",
  "dependencies": {
    "python": [
      "lxml>=5.0.0",
      "xmltodict>=0.13.0",
      "signxml>=3.2.0",
      "cryptography>=42.0.0",
      "zeep>=4.2.0",
      "reportlab>=4.0.0"
    ]
  }
}
```

---

## 🚀 Cómo Desarrollar un Plugin Oficial

### 1. Estructura del Plugin

```
plugins/cpos-plugin-{name}/
├── plugin.json          # Metadata del plugin
├── __init__.py          # Punto de entrada
├── models.py            # Modelos Django
├── views.py             # Views y APIs
├── urls.py              # URL routing
├── admin.py             # Django admin (opcional)
├── management/          # Management commands (opcional)
│   └── commands/
├── migrations/          # Migraciones Django
├── templates/{name}/    # Templates Django
│   └── index.html
├── static/{name}/       # CSS, JS, imágenes
│   ├── css/
│   ├── js/
│   └── img/
├── services/            # Lógica de negocio (opcional)
│   └── service.py
└── tests/               # Tests pytest
    ├── test_models.py
    ├── test_views.py
    └── test_services.py
```

### 2. plugin.json

```json
{
  "plugin_id": "cpos-plugin-nombre",
  "name": "Nombre del Plugin",
  "version": "1.0.0",
  "description": "Descripción del plugin",
  "author": "CPOS Team",
  "category": "pos",

  "dependencies": {
    "python": [
      "reportlab>=4.0.0",
      "pillow>=10.0.0"
    ],
    "plugins": [
      "cpos-plugin-products>=1.0.0"
    ]
  },

  "compatibility": {
    "min_cpos_version": "1.0.0",
    "max_cpos_version": "2.0.0"
  },

  "menu": {
    "label": "Nombre en menú",
    "icon": "cart-outline",
    "order": 10
  },

  "urls": {
    "main": "/plugins/nombre/"
  }
}
```

### 3. Instalación y Activación

```bash
# Desarrollo local
cd /Users/ioan/Desktop/code/cpos/hub
python manage.py plugin install plugins/cpos-plugin-nombre/

# Desde ZIP (producción)
python manage.py plugin install /path/to/plugin.zip
```

### 4. Guidelines de Desarrollo

#### ✅ DO:
- Usar prefijo del plugin en nombres de tabla (`pos_sale`, `products_product`)
- Declarar todas las dependencias Python en `plugin.json`
- Usar solo librerías de la whitelist ([plugin_allowed_deps.py](../config/plugin_allowed_deps.py))
- Escribir tests completos (models, views, servicios)
- Usar Ionic 8 + Alpine.js + HTMX para UI
- Seguir estructura de carpetas estándar

#### ❌ DON'T:
- NO usar nombres genéricos sin prefijo (`class Product` → `products_product`)
- NO instalar librerías con pip (usar solo whitelist)
- NO modificar código del Hub Core
- NO usar JavaScript frameworks pesados (React, Vue, Angular)
- NO crear conflictos de tabla con otros plugins

### 5. Testing

```bash
# Run tests del plugin
pytest plugins/cpos-plugin-nombre/tests/ -v

# Con coverage
pytest plugins/cpos-plugin-nombre/tests/ --cov=plugins/cpos-plugin-nombre --cov-report=html
```

### 6. Empaquetado

```bash
# Crear ZIP para distribución
python manage.py plugin package cpos-plugin-nombre

# Output: dist/cpos-plugin-nombre-1.0.0.zip
```

---

## 📚 Recursos

- **Guía Completa:** [README.md](./README.md) - Guía detallada de desarrollo de plugins (877 líneas)
- **Hardware POS:** [HARDWARE_POS.md](../docs/HARDWARE_POS.md) - Ejemplos de integración hardware
- **Dependencies Whitelist:** [plugin_allowed_deps.py](../config/plugin_allowed_deps.py) - 28 librerías permitidas
- **Validación:** [plugin_validator.py](../apps/core/plugin_validator.py) - Validador de seguridad
- **Runtime Manager:** [runtime_manager.py](../apps/core/runtime_manager.py) - Instalador de plugins

---

## 🎯 Prioridades de Desarrollo

### MVP (Crítico - Semana 1-2)
1. **cpos-plugin-pos** (5-7 días) - BLOQUEANTE
2. **cpos-plugin-products** (3-4 días) - BLOQUEANTE

### Post-MVP (Alta - Semana 3-4)
3. **cpos-plugin-backups** (5-7 días)

### Futuro (Media - Semana 5+)
4. **cpos-plugin-hardware** (4-5 días)
5. **cpos-plugin-facturacion-mx** (7-10 días)

---

**Última actualización:** 2025-01-10
