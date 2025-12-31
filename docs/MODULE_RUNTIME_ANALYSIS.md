# Análisis del Sistema de Modules - Estado Actual

**Fecha:** 2025-12-30
**Estado:** 100% Completo ✅

---

## 📊 Resumen Ejecutivo

El sistema de modules está **100% implementado** con una arquitectura completamente basada en filesystem.

### Arquitectura Actual: Filesystem-Based (NO Database)

**IMPORTANTE:** Los modules **NO se almacenan en base de datos**. Toda la información viene del filesystem:

| Fuente | Información |
|--------|-------------|
| **Carpeta** | Estado activo/inactivo (`module/` vs `_module/` vs `.module/`) |
| **module.json** | Metadata (nombre, versión, autor, menú, etc.) |
| **Código Python** | Funcionalidad, modelos, vistas, URLs |

### Estados de Módulos por Convención de Nombres

```
modules/
├── inventory/          ← ACTIVO (sin prefijo)
├── sales/              ← ACTIVO (sin prefijo)
├── _cash_register/     ← INACTIVO (prefijo _)
├── _returns/           ← INACTIVO (prefijo _)
└── .experimental/      ← OCULTO (prefijo .)
```

### Componentes Implementados

| Componente | Estado | Archivo | Descripción |
|------------|--------|---------|-------------|
| **Module Loader** | ✅ 100% | `apps/core/module_loader.py` | Descubrimiento y carga desde filesystem |
| **Modules Runtime** | ✅ 100% | `apps/modules_runtime/loader.py` | Carga dinámica en INSTALLED_APPS |
| **URL Router** | ✅ 100% | `apps/modules_runtime/router.py` | Registro dinámico de URLs en `/m/{module_id}/` |
| **API** | ✅ 100% | `apps/system/modules/api.py` | API REST para gestión de modules |
| **Context Processor** | ✅ 100% | `apps/core/context_processors.py` | Menú dinámico en templates |

---

## ✅ Componentes Principales

### 1. Module Loader (`apps/core/module_loader.py`)

**Funcionalidades:**

```python
class ModuleLoader:
    ✅ discover_modules(include_inactive=True)  # Lee filesystem
    ✅ get_active_modules()                      # Solo activos (sin _)
    ✅ load_module(module_id)                    # Carga en INSTALLED_APPS
    ✅ load_all_active_modules()                 # Carga masiva
    ✅ activate_module(module_id)                # Renombra _module → module
    ✅ deactivate_module(module_id)              # Renombra module → _module
    ✅ delete_module(module_id)                  # Elimina carpeta
    ✅ get_menu_items()                          # Lee menu de module.json
```

**Flujo de descubrimiento:**

1. Lee directorio `MODULES_DIR`
2. Filtra carpetas (ignora `.` prefix = ocultas)
3. Determina estado por prefijo `_`
4. Lee `module.json` para metadata
5. Genera menu items para sidebar

### 2. Modules Runtime (`apps/modules_runtime/`)

**Carga al inicio de Django:**

```python
# apps/modules_runtime/apps.py
class ModulesRuntimeConfig(AppConfig):
    def ready(self):
        # 1. Descubre modules activos
        active_modules = module_loader.get_active_modules()

        # 2. Los agrega a INSTALLED_APPS
        for module in active_modules:
            settings.INSTALLED_APPS.append(module['module_id'])

        # 3. Registra URLs en /m/{module_id}/
        for module in active_modules:
            register_module_urls(module['module_id'])
```

**Router de URLs:**

```python
# apps/modules_runtime/router.py
def register_module_urls(module_id, app_name, prefix):
    """Registra URLs dinámicamente en /m/{module_id}/"""
    urlpatterns.append(
        path(f'm/{module_id}/', include(f'{module_id}.urls'))
    )
```

### 3. API de Gestión (`apps/system/modules/api.py`)

**Endpoints disponibles:**

| Método | Endpoint | Descripción |
|--------|----------|-------------|
| GET | `/api/modules/` | Lista todos los modules (filesystem) |
| POST | `/api/modules/{id}/activate/` | Activa (renombra carpeta) |
| POST | `/api/modules/{id}/deactivate/` | Desactiva (renombra carpeta) |
| DELETE | `/api/modules/{id}/delete/` | Elimina carpeta |
| POST | `/api/modules/restart/` | Reinicia servidor |
| GET | `/api/modules/marketplace/` | Fetch de Cloud marketplace |
| POST | `/api/modules/marketplace/install/` | Descarga e instala ZIP |
| POST | `/api/modules/marketplace/purchase/` | Inicia compra en Cloud |

### 4. Context Processor (`apps/core/context_processors.py`)

```python
def module_menu_items(request):
    """Agrega items de menú al contexto de templates"""
    if 'local_user_id' in request.session:
        menu_items = module_loader.get_menu_items()
    else:
        menu_items = []
    return {'MODULE_MENU_ITEMS': menu_items}
```

---

## 📁 Estructura de un Module

```
{module_id}/
├── module.json          # Metadata (REQUERIDO)
├── __init__.py          # Module init
├── apps.py              # AppConfig
├── models.py            # Modelos Django
├── views.py             # Vistas
├── urls.py              # URLconf con app_name
├── templates/
│   └── {module_id}/
│       └── *.html
├── static/
│   └── {module_id}/
│       ├── css/
│       └── js/
├── migrations/
│   └── __init__.py
└── README.md
```

### module.json (Ejemplo)

```json
{
    "module_id": "inventory",
    "name": "Inventory",
    "description": "Product and stock management",
    "version": "1.0.0",
    "author": "ERPlora",
    "icon": "cube-outline",
    "category": "operations",
    "menu": {
        "label": "Inventory",
        "label_es": "Inventario",
        "icon": "cube-outline",
        "order": 20,
        "show": true
    }
}
```

---

## 🔄 Flujo de Activación/Desactivación

### Activar Module

```bash
# Estado inicial
modules/_sales/

# API: POST /api/modules/sales/activate/

# Estado final
modules/sales/  # Renombrado, sin _

# Requiere reinicio del servidor para cargar URLs
```

### Desactivar Module

```bash
# Estado inicial
modules/sales/

# API: POST /api/modules/sales/deactivate/

# Estado final
modules/_sales/  # Renombrado, con _

# Requiere reinicio del servidor
```

---

## 🚀 URLs de Modules

Todos los modules activos se registran bajo el prefijo `/m/`:

```
/m/inventory/          → inventory.urls
/m/sales/              → sales.urls
/m/customers/          → customers.urls
/m/cash_register/      → cash_register.urls
```

Esto evita conflictos con las URLs del sistema:
- `/modules/` → "Mis Módulos" (página del sistema)
- `/m/{module_id}/` → URLs del module dinámico

---

## 🎯 Decisiones de Arquitectura

### ¿Por qué NO base de datos?

1. **Simplicidad**: Sin migraciones ni sincronización
2. **Portabilidad**: Copiar carpeta = instalar module
3. **Debugging**: Ver estado con `ls modules/`
4. **Backups**: rsync/tar de la carpeta modules/
5. **Desarrollo**: Crear carpeta = module funcional

### ¿Por qué prefijos en nombres de carpetas?

| Prefijo | Estado | Ejemplo |
|---------|--------|---------|
| (ninguno) | Activo, cargado | `inventory/` |
| `_` | Inactivo, visible en UI | `_cash_register/` |
| `.` | Oculto, no visible | `.experimental/` |

**Ventajas:**
- Estado visible en el filesystem
- No requiere base de datos
- Activar/desactivar = renombrar carpeta
- Funciona offline

---

## 📋 Comandos Útiles

### Listar modules

```bash
# Ver todos los modules
ls -la /path/to/modules/

# Solo activos (sin prefijo)
ls -d /path/to/modules/[^_.]*/

# Solo inactivos
ls -d /path/to/modules/_*/
```

### Activar/Desactivar manualmente

```bash
# Activar
mv modules/_sales modules/sales

# Desactivar
mv modules/sales modules/_sales

# Ocultar
mv modules/sales modules/.sales
```

### Reiniciar después de cambios

```bash
# Desarrollo
python manage.py runserver

# Producción (touch wsgi.py triggers reload)
touch config/wsgi.py
```

---

**Última actualización:** 2025-12-30
**Arquitectura:** Filesystem-based (NO database)
**Estado:** 100% completo ✅
