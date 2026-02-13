# Module Activation Flow - WordPress-Style System

## Overview

ERPlora Hub uses a **filesystem-based module system** similar to WordPress. Modules are activated/deactivated by renaming folders, and registration happens automatically on server restart.

## Key Concepts

### 1. Module States (Filesystem-Based)

- **Inactive Module**: Folder starts with underscore `_inventory/`
- **Active Module**: Folder WITHOUT underscore `inventory/`
- **Hidden Module**: Folder starts with dot `.template/` (never loaded)

### 2. Automatic Registration

When Django starts, `apps.modules_runtime` automatically:
1. Scans `modules/` directory
2. Loads active modules (no `_` prefix)
3. Registers in INSTALLED_APPS
4. Runs migrations
5. Registers URLs dynamically
6. Generates menu items from module.json

### 3. No Database Dependency

Module state is determined **only from folder name**, NOT from database. This ensures:
- ✅ Simple and reliable
- ✅ Easy to backup/restore
- ✅ No sync issues
- ✅ Visual inspection of active modules

---

## Complete Activation Flow

### Step 1: Purchase & Download (Marketplace)

```
User → Cloud Marketplace → Purchase Module → Download ZIP
                                                  ↓
                                    Hub receives: inventory.zip
                                                  ↓
                                    Hub extracts to: modules/_inventory/
```

**Folder Structure:**
```
hub/modules/
├── _inventory/           ← Downloaded as INACTIVE (with underscore)
│   ├── module.json
│   ├── models.py
│   ├── views.py
│   ├── urls.py
│   └── templates/
└── products/            ← Example active module (no underscore)
```

**Why `_inventory/`?**
- User hasn't activated it yet
- Won't load on restart
- Gives user control

---

### Step 2: Activate Module (UI Action)

**User Action:**
1. Navigate to `/modules/` page
2. Find inactive module card
3. Click **"Activate"** button

**Backend Action (`module_activate` view):**
```python
# apps/configuration/views_modules.py

@require_http_methods(["POST"])
def module_activate(request, module_id):
    modules_dir = Path(django_settings.MODULES_DIR)
    disabled_folder = modules_dir / f"_{module_id}"  # _inventory/
    active_folder = modules_dir / module_id          # inventory/

    if not disabled_folder.exists():
        return JsonResponse({'success': False, 'error': 'Module not found'}, status=404)

    try:
        # CRITICAL: Just rename the folder (remove underscore)
        disabled_folder.rename(active_folder)
        return JsonResponse({'success': True, 'message': 'Module activated. Restart required.'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)
```

**Result:**
```
modules/_inventory/  →  modules/inventory/
```

**Important Notes:**
- ✅ Operation is instant (just folder rename)
- ✅ Module NOT loaded yet (needs restart)
- ✅ User sees "Restart required" message
- ⚠️ Module won't work until restart

---

### Step 3: Restart Django Server

**User Action:**
```bash
# Kill current process
pkill -f "python manage.py runserver"

# Restart server
cd hub/
python manage.py runserver 8001
```

**Why Manual Restart?**
- Django loads INSTALLED_APPS only at startup
- New modules = new Django apps
- Cannot hot-reload without complexity
- Simple, reliable, clear to user

---

### Step 4: Automatic Module Registration (On Startup)

**Entry Point:** `apps/modules_runtime/apps.py`

```python
class ModulesRuntimeConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.modules_runtime'
    verbose_name = 'Modules Runtime'

    def ready(self):
        """
        Django calls this ONCE during startup.
        This is where ALL module loading happens.
        """
        print("\n" + "="*80)
        print("[MODULES_RUNTIME] Loading active modules from filesystem...")
        print("="*80)

        from .loader import module_loader
        from apps.modules_runtime.router import register_module_urls

        # 1️⃣ Load all active modules from filesystem
        loaded_count = module_loader.load_all_active_modules()
        print(f"[MODULES_RUNTIME] Loaded {loaded_count} active modules")

        # 2️⃣ Register URLs for each loaded module
        for module_id, module_info in module_loader.loaded_modules.items():
            register_module_urls(module_id, module_id, f'/m/{module_id}/')

        print("="*80 + "\n")
```

---

### Step 5: Module Loading Process

**Code:** `apps/modules_runtime/loader.py`

#### 5.1 Scan Filesystem

```python
def load_all_active_modules(self) -> int:
    """
    Scans modules/ directory and loads active modules.
    Active = folder does NOT start with _ or .
    """
    loaded_count = 0

    for module_dir in self.modules_dir.iterdir():
        if not module_dir.is_dir():
            continue

        # Skip disabled modules (_ prefix) and hidden (. prefix)
        if module_dir.name.startswith('.') or module_dir.name.startswith('_'):
            print(f"[SKIP] Module '{module_dir.name}' is disabled")
            continue

        module_id = module_dir.name  # Example: "inventory"

        if self.load_module(module_id):
            loaded_count += 1

    return loaded_count
```

**Example:**
```
modules/
├── .template/        ← SKIP (hidden)
├── _inventory/       ← SKIP (disabled with underscore)
├── products/         ← LOAD ✅ (active)
└── reports/          ← LOAD ✅ (active)

Result: 2 modules loaded (products, reports)
```

---

#### 5.2 Load Individual Module

```python
def load_module(self, module_id: str) -> bool:
    """
    Loads a single module:
    1. Read module.json metadata
    2. Add to Django's INSTALLED_APPS
    3. Import models (triggers migrations)
    4. Store in loaded_modules dict
    """
    module_path = self.modules_dir / module_id

    if not module_path.exists():
        print(f"[ERROR] Module '{module_id}' not found")
        return False

    # Read module.json
    module_json = module_path / 'module.json'
    if not module_json.exists():
        print(f"[ERROR] Module '{module_id}' missing module.json")
        return False

    try:
        with open(module_json, 'r', encoding='utf-8') as f:
            metadata = json.load(f)

        # Add to INSTALLED_APPS (so Django recognizes it as an app)
        app_name = module_id
        if app_name not in django_settings.INSTALLED_APPS:
            django_settings.INSTALLED_APPS.append(app_name)
            print(f"[✓] Added '{app_name}' to INSTALLED_APPS")

        # Import models (Django auto-runs migrations)
        try:
            importlib.import_module(f'{module_id}.models')
            print(f"[✓] Imported models for '{module_id}'")
        except ImportError:
            print(f"[INFO] Module '{module_id}' has no models")

        # Store module info
        self.loaded_modules[module_id] = {
            'path': module_path,
            'metadata': metadata,
            'is_active': True
        }

        print(f"[✓] Module '{module_id}' loaded successfully")
        return True

    except Exception as e:
        print(f"[ERROR] Failed to load module '{module_id}': {e}")
        return False
```

**What Happens:**
1. ✅ Django recognizes module as an app
2. ✅ Models are imported
3. ✅ Migrations run automatically (if models changed)
4. ✅ Module stored in `module_loader.loaded_modules` dict

---

#### 5.3 Register URLs Dynamically

```python
# apps/modules_runtime/router.py

def register_module_urls(module_id: str, app_name: str, prefix: str):
    """
    Registers module URLs dynamically with namespace.

    Example:
        module_id = "inventory"
        app_name = "inventory"
        prefix = "/m/inventory/"

    Result:
        /m/inventory/ → inventory.urls with namespace 'inventory'
    """
    try:
        # Import module's urls.py
        module_urls = importlib.import_module(f'{module_id}.urls')

        # Create URL pattern with namespace
        module_urlpatterns.append(
            path(prefix.lstrip('/'), include((module_urls, app_name), namespace=app_name))
        )

        print(f"[✓] Registered URLs for '{module_id}' at '{prefix}'")

    except ImportError:
        print(f"[INFO] Module '{module_id}' has no urls.py")
    except Exception as e:
        print(f"[ERROR] Failed to register URLs for '{module_id}': {e}")
```

**Example URLs:**
```python
# modules/inventory/urls.py

urlpatterns = [
    path('', views.index, name='index'),           # /m/inventory/
    path('add/', views.add_product, name='add'),   # /m/inventory/add/
]

# After registration, accessible via:
{% url 'inventory:index' %}  # → /m/inventory/
{% url 'inventory:add' %}    # → /m/inventory/add/
```

---

#### 5.4 Generate Menu Items

**Code:** `apps/core/context_processors.py`

```python
def module_menu_items(request):
    """
    Generates menu items from loaded modules' module.json

    Each module can define:
    {
        "menu": {
            "label": "Inventory",
            "icon": "cube-outline",
            "order": 10,
            "items": [
                {"label": "Products", "url": "/modules/inventory/", "icon": "list-outline"},
                {"label": "Categories", "url": "/modules/inventory/categories/", "icon": "folder-outline"}
            ]
        }
    }
    """
    from apps.modules_runtime.loader import module_loader

    menu_items = []

    for module_id, module_info in module_loader.loaded_modules.items():
        metadata = module_info.get('metadata', {})
        menu_config = metadata.get('menu', {})

        if not menu_config:
            continue

        menu_item = {
            'label': menu_config.get('label', module_id.title()),
            'icon': menu_config.get('icon', 'cube-outline'),
            'order': menu_config.get('order', 100),
            'items': menu_config.get('items', []),
            'has_submenu': len(menu_config.get('items', [])) > 1
        }

        menu_items.append(menu_item)

    # Sort by order
    menu_items.sort(key=lambda x: x['order'])

    return {'MODULE_MENU_ITEMS': menu_items}
```

**Template Usage:**
```django
<!-- apps/core/templates/core/app_base.html -->

{% for item in MODULE_MENU_ITEMS %}
    {% if item.has_submenu %}
    <!-- Accordion menu for modules with multiple items -->
    <ion-accordion-group>
        <ion-accordion>
            <ion-item slot="header" class="nav-item">
                <ion-icon name="{{ item.icon }}" slot="start"></ion-icon>
                <ion-label>{{ item.label }}</ion-label>
            </ion-item>
            <div slot="content">
                {% for subitem in item.items %}
                <ion-item href="{{ subitem.url }}" class="nav-item">
                    <ion-icon name="{{ subitem.icon }}" slot="start"></ion-icon>
                    <ion-label>{{ subitem.label }}</ion-label>
                </ion-item>
                {% endfor %}
            </div>
        </ion-accordion>
    </ion-accordion-group>
    {% else %}
    <!-- Single menu item -->
    <ion-item href="{{ item.url }}" class="nav-item">
        <ion-icon name="{{ item.icon }}" slot="start"></ion-icon>
        <ion-label>{{ item.label }}</ion-label>
    </ion-item>
    {% endif %}
{% endfor %}
```

---

### Step 6: Module Fully Active ✅

After restart completes, the module is fully functional:

- ✅ Added to INSTALLED_APPS
- ✅ Models imported
- ✅ Migrations applied
- ✅ URLs registered at `/m/inventory/`
- ✅ Menu items visible in sidebar
- ✅ Ready to use!

---

## Deactivation Flow

### User Action:
1. Navigate to `/modules/`
2. Click **"Deactivate"** on active module
3. Restart server

### Backend Action:
```python
@require_http_methods(["POST"])
def module_deactivate(request, module_id):
    modules_dir = Path(django_settings.MODULES_DIR)
    active_folder = modules_dir / module_id        # inventory/
    disabled_folder = modules_dir / f"_{module_id}" # _inventory/

    try:
        # Rename to add underscore prefix
        active_folder.rename(disabled_folder)
        return JsonResponse({'success': True, 'message': 'Module deactivated. Restart required.'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)
```

**Result:**
```
modules/inventory/  →  modules/_inventory/
```

**After Restart:**
- ❌ NOT loaded (has underscore)
- ❌ NOT in INSTALLED_APPS
- ❌ URLs not registered
- ❌ Menu items removed
- ✅ Files still exist (can re-activate)

---

## Deletion Flow

### User Action:
1. Navigate to `/modules/`
2. Click **"Delete"** button (trash icon)
3. Confirm deletion

### Backend Action:
```python
@require_http_methods(["POST"])
def module_delete(request, module_id):
    modules_dir = Path(django_settings.MODULES_DIR)

    # Try both active and disabled folders
    active_folder = modules_dir / module_id
    disabled_folder = modules_dir / f"_{module_id}"

    folder_to_delete = None
    if active_folder.exists():
        folder_to_delete = active_folder
    elif disabled_folder.exists():
        folder_to_delete = disabled_folder

    if not folder_to_delete:
        return JsonResponse({'success': False, 'error': 'Module not found'}, status=404)

    try:
        # Delete folder completely
        shutil.rmtree(folder_to_delete)
        return JsonResponse({'success': True, 'message': 'Module deleted successfully.'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)
```

**Result:**
```
modules/inventory/  →  DELETED (folder removed)
```

**After Restart:**
- ⚠️ Module completely removed
- ⚠️ Cannot be recovered (unless re-download from marketplace)
- ✅ Clean uninstall

---

## Module Structure Example

### Minimal Module (No Database)

```
modules/inventory/
├── module.json          # Required metadata
├── __init__.py          # Empty (makes it a Python package)
├── views.py             # Django views
├── urls.py              # URL patterns
└── templates/
    └── inventory/
        └── index.html
```

**module.json:**
```json
{
    "module_id": "inventory",
    "name": "Inventory Manager",
    "version": "1.0.0",
    "description": "Manage product inventory",
    "author": "ERPlora Team",
    "menu": {
        "label": "Inventory",
        "icon": "cube-outline",
        "order": 10,
        "items": [
            {
                "label": "Products",
                "url": "/m/inventory/",
                "icon": "list-outline"
            }
        ]
    }
}
```

### Full Module (With Database)

```
modules/inventory/
├── module.json
├── __init__.py
├── models.py            # Django models
├── views.py
├── urls.py
├── migrations/          # Django migrations (auto-generated)
│   └── __init__.py
└── templates/
    └── inventory/
        ├── index.html
        └── add.html
```

**models.py:**
```python
from django.db import models

class Product(models.Model):
    name = models.CharField(max_length=255)
    sku = models.CharField(max_length=50, unique=True)
    stock = models.IntegerField(default=0)

    class Meta:
        db_table = 'inventory_product'  # Recommended: prefix with module_id
```

**Important:**
- ✅ Use `db_table` with module_id prefix to avoid conflicts
- ✅ Migrations run automatically when module loads
- ✅ Database tables persist even if module is deactivated

---

## Troubleshooting

### Module Not Loading After Activation

**Check:**
1. Folder name has NO underscore: `inventory/` ✅ NOT `_inventory/` ❌
2. Server was restarted after activation
3. `module.json` exists and is valid JSON
4. Check console logs for errors during startup

**Console Output:**
```
[MODULES_RUNTIME] Loading active modules from filesystem...
[✓] Added 'inventory' to INSTALLED_APPS
[✓] Imported models for 'inventory'
[✓] Module 'inventory' loaded successfully
[✓] Registered URLs for 'inventory' at '/m/inventory/'
[MODULES_RUNTIME] Loaded 1 active modules
```

### URLs Not Working (404)

**Check:**
1. Module has `urls.py` file
2. URLs registered correctly (check console logs)
3. URL includes module prefix: `/m/inventory/` NOT `/inventory/`

**Common mistake:**
```python
# ❌ WRONG (absolute URL)
{% url 'inventory:index' %}  # → /inventory/ (404)

# ✅ CORRECT (includes prefix)
# URLs are auto-registered with /m/{module_id}/ prefix
/m/inventory/  # Works!
```

### Menu Items Not Showing

**Check:**
1. `module.json` has valid `menu` section
2. Module is loaded (check console logs)
3. Context processor is registered in settings.py:
   ```python
   TEMPLATES = [{
       'OPTIONS': {
           'context_processors': [
               'apps.core.context_processors.module_menu_items',
           ],
       },
   }]
   ```

### Migration Errors

**Issue:** Module models changed but migrations not applied.

**Fix:**
```bash
# Generate migrations for specific module
python manage.py makemigrations inventory

# Apply migrations
python manage.py migrate inventory
```

### Module Won't Deactivate (Folder Rename Fails)

**Check:**
1. No other process has folder open (close IDEs, file explorers)
2. Folder permissions are correct
3. Try manual rename:
   ```bash
   cd modules/
   mv inventory/ _inventory/
   ```

---

## Summary: Why This System Works

### ✅ Advantages

1. **Simple**: Folder name = module state
2. **Visual**: Can see active modules at a glance
3. **Reliable**: No database sync issues
4. **Portable**: Copy folder = backup module
5. **Django-native**: Uses built-in INSTALLED_APPS
6. **Zero downtime**: Activation is instant (just rename)
7. **Safe**: Deactivation preserves files

### ⚠️ Trade-offs

1. **Manual restart**: Required after activate/deactivate
2. **No hot-reload**: Cannot load modules without restart
3. **Naming convention**: Must use `_` prefix correctly

### 🎯 WordPress Comparison

| Feature | WordPress | ERPlora Hub |
|---------|-----------|-------------|
| Activation | Database flag | Folder rename |
| State persistence | wp_options table | Filesystem |
| Hot-reload | Yes (PHP) | No (Django) |
| Restart required | No | Yes |
| Complexity | High | Low |
| Reliability | Moderate | High |

---

## Related Documentation

- [MODULE_DEPENDENCIES.md](./MODULE_DEPENDENCIES.md) - Allowed libraries
- [MODULE_DATABASE_CONFLICTS.md](./MODULE_DATABASE_CONFLICTS.md) - Avoiding table conflicts
- [CLAUDE.md](../../CLAUDE.md) - System architecture overview

---

**Last Updated:** 2025-12-30
