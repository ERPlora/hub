# Plugin Activation Flow - WordPress-Style System

## Overview

ERPlora Hub uses a **filesystem-based plugin system** similar to WordPress. Plugins are activated/deactivated by renaming folders, and registration happens automatically on server restart.

## Key Concepts

### 1. Plugin States (Filesystem-Based)

- **Inactive Plugin**: Folder starts with underscore `_inventory/`
- **Active Plugin**: Folder WITHOUT underscore `inventory/`
- **Hidden Plugin**: Folder starts with dot `.template/` (never loaded)

### 2. Automatic Registration

When Django starts, `apps.plugins_runtime` automatically:
1. Scans `plugins/` directory
2. Loads active plugins (no `_` prefix)
3. Registers in INSTALLED_APPS
4. Runs migrations
5. Registers URLs dynamically
6. Generates menu items from plugin.json

### 3. No Database Dependency

Plugin state is determined **only from folder name**, NOT from database. This ensures:
- ✅ Simple and reliable
- ✅ Easy to backup/restore
- ✅ No sync issues
- ✅ Visual inspection of active plugins

---

## Complete Activation Flow

### Step 1: Purchase & Download (Marketplace)

```
User → Cloud Marketplace → Purchase Plugin → Download ZIP
                                                  ↓
                                    Hub receives: inventory.zip
                                                  ↓
                                    Hub extracts to: plugins/_inventory/
```

**Folder Structure:**
```
hub/plugins/
├── _inventory/           ← Downloaded as INACTIVE (with underscore)
│   ├── plugin.json
│   ├── models.py
│   ├── views.py
│   ├── urls.py
│   └── templates/
└── products/            ← Example active plugin (no underscore)
```

**Why `_inventory/`?**
- User hasn't activated it yet
- Won't load on restart
- Gives user control

---

### Step 2: Activate Plugin (UI Action)

**User Action:**
1. Navigate to `/plugins/` page
2. Find inactive plugin card
3. Click **"Activate"** button

**Backend Action (`plugin_activate` view):**
```python
# apps/configuration/views_plugins.py

@require_http_methods(["POST"])
def plugin_activate(request, plugin_id):
    plugins_dir = Path(django_settings.PLUGINS_DIR)
    disabled_folder = plugins_dir / f"_{plugin_id}"  # _inventory/
    active_folder = plugins_dir / plugin_id          # inventory/

    if not disabled_folder.exists():
        return JsonResponse({'success': False, 'error': 'Plugin not found'}, status=404)

    try:
        # CRITICAL: Just rename the folder (remove underscore)
        disabled_folder.rename(active_folder)
        return JsonResponse({'success': True, 'message': 'Plugin activated. Restart required.'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)
```

**Result:**
```
plugins/_inventory/  →  plugins/inventory/
```

**Important Notes:**
- ✅ Operation is instant (just folder rename)
- ✅ Plugin NOT loaded yet (needs restart)
- ✅ User sees "Restart required" message
- ⚠️ Plugin won't work until restart

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
- New plugins = new Django apps
- Cannot hot-reload without complexity
- Simple, reliable, clear to user

---

### Step 4: Automatic Plugin Registration (On Startup)

**Entry Point:** `apps/plugins_runtime/apps.py`

```python
class PluginsRuntimeConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.plugins_runtime'
    verbose_name = 'Plugins Runtime'

    def ready(self):
        """
        Django calls this ONCE during startup.
        This is where ALL plugin loading happens.
        """
        print("\n" + "="*80)
        print("[PLUGINS_RUNTIME] Loading active plugins from filesystem...")
        print("="*80)

        from .loader import plugin_loader
        from apps.core.runtime_manager import register_plugin_urls

        # 1️⃣ Load all active plugins from filesystem
        loaded_count = plugin_loader.load_all_active_plugins()
        print(f"[PLUGINS_RUNTIME] Loaded {loaded_count} active plugins")

        # 2️⃣ Register URLs for each loaded plugin
        for plugin_id, plugin_info in plugin_loader.loaded_plugins.items():
            register_plugin_urls(plugin_id, plugin_id, f'/plugins/{plugin_id}/')

        print("="*80 + "\n")
```

---

### Step 5: Plugin Loading Process

**Code:** `apps/plugins_runtime/loader.py`

#### 5.1 Scan Filesystem

```python
def load_all_active_plugins(self) -> int:
    """
    Scans plugins/ directory and loads active plugins.
    Active = folder does NOT start with _ or .
    """
    loaded_count = 0

    for plugin_dir in self.plugins_dir.iterdir():
        if not plugin_dir.is_dir():
            continue

        # Skip disabled plugins (_ prefix) and hidden (. prefix)
        if plugin_dir.name.startswith('.') or plugin_dir.name.startswith('_'):
            print(f"[SKIP] Plugin '{plugin_dir.name}' is disabled")
            continue

        plugin_id = plugin_dir.name  # Example: "inventory"

        if self.load_plugin(plugin_id):
            loaded_count += 1

    return loaded_count
```

**Example:**
```
plugins/
├── .template/        ← SKIP (hidden)
├── _inventory/       ← SKIP (disabled with underscore)
├── products/         ← LOAD ✅ (active)
└── multi_store/      ← LOAD ✅ (active)

Result: 2 plugins loaded (products, multi_store)
```

---

#### 5.2 Load Individual Plugin

```python
def load_plugin(self, plugin_id: str) -> bool:
    """
    Loads a single plugin:
    1. Read plugin.json metadata
    2. Add to Django's INSTALLED_APPS
    3. Import models (triggers migrations)
    4. Store in loaded_plugins dict
    """
    plugin_path = self.plugins_dir / plugin_id

    if not plugin_path.exists():
        print(f"[ERROR] Plugin '{plugin_id}' not found")
        return False

    # Read plugin.json
    plugin_json = plugin_path / 'plugin.json'
    if not plugin_json.exists():
        print(f"[ERROR] Plugin '{plugin_id}' missing plugin.json")
        return False

    try:
        with open(plugin_json, 'r', encoding='utf-8') as f:
            metadata = json.load(f)

        # Add to INSTALLED_APPS (so Django recognizes it as an app)
        app_name = plugin_id
        if app_name not in django_settings.INSTALLED_APPS:
            django_settings.INSTALLED_APPS.append(app_name)
            print(f"[✓] Added '{app_name}' to INSTALLED_APPS")

        # Import models (Django auto-runs migrations)
        try:
            importlib.import_module(f'{plugin_id}.models')
            print(f"[✓] Imported models for '{plugin_id}'")
        except ImportError:
            print(f"[INFO] Plugin '{plugin_id}' has no models")

        # Store plugin info
        self.loaded_plugins[plugin_id] = {
            'path': plugin_path,
            'metadata': metadata,
            'is_active': True
        }

        print(f"[✓] Plugin '{plugin_id}' loaded successfully")
        return True

    except Exception as e:
        print(f"[ERROR] Failed to load plugin '{plugin_id}': {e}")
        return False
```

**What Happens:**
1. ✅ Django recognizes plugin as an app
2. ✅ Models are imported
3. ✅ Migrations run automatically (if models changed)
4. ✅ Plugin stored in `plugin_loader.loaded_plugins` dict

---

#### 5.3 Register URLs Dynamically

```python
# apps/core/runtime_manager.py

def register_plugin_urls(plugin_id: str, app_name: str, prefix: str):
    """
    Registers plugin URLs dynamically with namespace.

    Example:
        plugin_id = "inventory"
        app_name = "inventory"
        prefix = "/plugins/inventory/"

    Result:
        /plugins/inventory/ → inventory.urls with namespace 'inventory'
    """
    try:
        # Import plugin's urls.py
        plugin_urls = importlib.import_module(f'{plugin_id}.urls')

        # Create URL pattern with namespace
        plugin_urlpatterns.append(
            path(prefix.lstrip('/'), include((plugin_urls, app_name), namespace=app_name))
        )

        print(f"[✓] Registered URLs for '{plugin_id}' at '{prefix}'")

    except ImportError:
        print(f"[INFO] Plugin '{plugin_id}' has no urls.py")
    except Exception as e:
        print(f"[ERROR] Failed to register URLs for '{plugin_id}': {e}")
```

**Example URLs:**
```python
# plugins/inventory/urls.py

urlpatterns = [
    path('', views.index, name='index'),           # /plugins/inventory/
    path('add/', views.add_product, name='add'),   # /plugins/inventory/add/
]

# After registration, accessible via:
{% url 'inventory:index' %}  # → /plugins/inventory/
{% url 'inventory:add' %}    # → /plugins/inventory/add/
```

---

#### 5.4 Generate Menu Items

**Code:** `apps/core/context_processors.py`

```python
def plugin_menu_items(request):
    """
    Generates menu items from loaded plugins' plugin.json

    Each plugin can define:
    {
        "menu": {
            "label": "Inventory",
            "icon": "cube-outline",
            "order": 10,
            "items": [
                {"label": "Products", "url": "/plugins/inventory/", "icon": "list-outline"},
                {"label": "Categories", "url": "/plugins/inventory/categories/", "icon": "folder-outline"}
            ]
        }
    }
    """
    from apps.plugins_runtime.loader import plugin_loader

    menu_items = []

    for plugin_id, plugin_info in plugin_loader.loaded_plugins.items():
        metadata = plugin_info.get('metadata', {})
        menu_config = metadata.get('menu', {})

        if not menu_config:
            continue

        menu_item = {
            'label': menu_config.get('label', plugin_id.title()),
            'icon': menu_config.get('icon', 'cube-outline'),
            'order': menu_config.get('order', 100),
            'items': menu_config.get('items', []),
            'has_submenu': len(menu_config.get('items', [])) > 1
        }

        menu_items.append(menu_item)

    # Sort by order
    menu_items.sort(key=lambda x: x['order'])

    return {'PLUGIN_MENU_ITEMS': menu_items}
```

**Template Usage:**
```django
<!-- apps/core/templates/core/app_base.html -->

{% for item in PLUGIN_MENU_ITEMS %}
    {% if item.has_submenu %}
    <!-- Accordion menu for plugins with multiple items -->
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

### Step 6: Plugin Fully Active ✅

After restart completes, the plugin is fully functional:

- ✅ Added to INSTALLED_APPS
- ✅ Models imported
- ✅ Migrations applied
- ✅ URLs registered at `/plugins/inventory/`
- ✅ Menu items visible in sidebar
- ✅ Ready to use!

---

## Deactivation Flow

### User Action:
1. Navigate to `/plugins/`
2. Click **"Deactivate"** on active plugin
3. Restart server

### Backend Action:
```python
@require_http_methods(["POST"])
def plugin_deactivate(request, plugin_id):
    plugins_dir = Path(django_settings.PLUGINS_DIR)
    active_folder = plugins_dir / plugin_id        # inventory/
    disabled_folder = plugins_dir / f"_{plugin_id}" # _inventory/

    try:
        # Rename to add underscore prefix
        active_folder.rename(disabled_folder)
        return JsonResponse({'success': True, 'message': 'Plugin deactivated. Restart required.'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)
```

**Result:**
```
plugins/inventory/  →  plugins/_inventory/
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
1. Navigate to `/plugins/`
2. Click **"Delete"** button (trash icon)
3. Confirm deletion

### Backend Action:
```python
@require_http_methods(["POST"])
def plugin_delete(request, plugin_id):
    plugins_dir = Path(django_settings.PLUGINS_DIR)

    # Try both active and disabled folders
    active_folder = plugins_dir / plugin_id
    disabled_folder = plugins_dir / f"_{plugin_id}"

    folder_to_delete = None
    if active_folder.exists():
        folder_to_delete = active_folder
    elif disabled_folder.exists():
        folder_to_delete = disabled_folder

    if not folder_to_delete:
        return JsonResponse({'success': False, 'error': 'Plugin not found'}, status=404)

    try:
        # Delete folder completely
        shutil.rmtree(folder_to_delete)
        return JsonResponse({'success': True, 'message': 'Plugin deleted successfully.'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)
```

**Result:**
```
plugins/inventory/  →  DELETED (folder removed)
```

**After Restart:**
- ⚠️ Plugin completely removed
- ⚠️ Cannot be recovered (unless re-download from marketplace)
- ✅ Clean uninstall

---

## Plugin Structure Example

### Minimal Plugin (No Database)

```
plugins/inventory/
├── plugin.json          # Required metadata
├── __init__.py          # Empty (makes it a Python package)
├── views.py             # Django views
├── urls.py              # URL patterns
└── templates/
    └── inventory/
        └── index.html
```

**plugin.json:**
```json
{
    "plugin_id": "inventory",
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
                "url": "/plugins/inventory/",
                "icon": "list-outline"
            }
        ]
    }
}
```

### Full Plugin (With Database)

```
plugins/inventory/
├── plugin.json
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
        db_table = 'inventory_product'  # Recommended: prefix with plugin_id
```

**Important:**
- ✅ Use `db_table` with plugin_id prefix to avoid conflicts
- ✅ Migrations run automatically when plugin loads
- ✅ Database tables persist even if plugin is deactivated

---

## Troubleshooting

### Plugin Not Loading After Activation

**Check:**
1. Folder name has NO underscore: `inventory/` ✅ NOT `_inventory/` ❌
2. Server was restarted after activation
3. `plugin.json` exists and is valid JSON
4. Check console logs for errors during startup

**Console Output:**
```
[PLUGINS_RUNTIME] Loading active plugins from filesystem...
[✓] Added 'inventory' to INSTALLED_APPS
[✓] Imported models for 'inventory'
[✓] Plugin 'inventory' loaded successfully
[✓] Registered URLs for 'inventory' at '/plugins/inventory/'
[PLUGINS_RUNTIME] Loaded 1 active plugins
```

### URLs Not Working (404)

**Check:**
1. Plugin has `urls.py` file
2. URLs registered correctly (check console logs)
3. URL includes plugin prefix: `/plugins/inventory/` NOT `/inventory/`

**Common mistake:**
```python
# ❌ WRONG (absolute URL)
{% url 'inventory:index' %}  # → /inventory/ (404)

# ✅ CORRECT (includes prefix)
# URLs are auto-registered with /plugins/{plugin_id}/ prefix
/plugins/inventory/  # Works!
```

### Menu Items Not Showing

**Check:**
1. `plugin.json` has valid `menu` section
2. Plugin is loaded (check console logs)
3. Context processor is registered in settings.py:
   ```python
   TEMPLATES = [{
       'OPTIONS': {
           'context_processors': [
               'apps.core.context_processors.plugin_menu_items',
           ],
       },
   }]
   ```

### Migration Errors

**Issue:** Plugin models changed but migrations not applied.

**Fix:**
```bash
# Generate migrations for specific plugin
python manage.py makemigrations inventory

# Apply migrations
python manage.py migrate inventory
```

### Plugin Won't Deactivate (Folder Rename Fails)

**Check:**
1. No other process has folder open (close IDEs, file explorers)
2. Folder permissions are correct
3. Try manual rename:
   ```bash
   cd plugins/
   mv inventory/ _inventory/
   ```

---

## Summary: Why This System Works

### ✅ Advantages

1. **Simple**: Folder name = plugin state
2. **Visual**: Can see active plugins at a glance
3. **Reliable**: No database sync issues
4. **Portable**: Copy folder = backup plugin
5. **Django-native**: Uses built-in INSTALLED_APPS
6. **Zero downtime**: Activation is instant (just rename)
7. **Safe**: Deactivation preserves files

### ⚠️ Trade-offs

1. **Manual restart**: Required after activate/deactivate
2. **No hot-reload**: Cannot load plugins without restart
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

- [PLUGIN_DEPENDENCIES.md](./PLUGIN_DEPENDENCIES.md) - Allowed libraries
- [PLUGIN_DATABASE_CONFLICTS.md](./PLUGIN_DATABASE_CONFLICTS.md) - Avoiding table conflicts
- [CLAUDE.md](../../CLAUDE.md) - System architecture overview

---

**Last Updated:** 2025-01-22
