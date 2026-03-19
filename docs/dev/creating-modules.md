# Creating ERPlora Hub Modules

Guide for creating new Hub modules and publishing them to the Cloud marketplace.

---

## Module Structure

Every module is a Django app inside `hub/modules/`:

```
hub/modules/{module_id}/
├── __init__.py
├── module.py               # Module metadata (required)
├── models.py               # Django models (HubBaseModel)
├── views.py                # Views with @htmx_view, @with_module_nav
├── urls.py                 # URL patterns
├── forms.py                # Django forms
├── admin.py                # Django admin (Unfold)
├── apps.py                 # AppConfig
├── ai_tools.py             # AI assistant tools (@register_tool)
├── ai_context.py           # AI context provider
├── templates/{module_id}/
│   ├── pages/              # Full page templates
│   └── partials/           # HTMX partial templates
├── migrations/
└── tests/
```

---

## module.py — Module Metadata

This is the most important file. Cloud parses it via AST to extract metadata.

```python
from django.utils.translation import gettext_lazy as _

MODULE_ID = 'my_module'
MODULE_NAME = _('My Module')
MODULE_VERSION = '1.0.0'
MODULE_ICON = 'material:icon_name'      # djicons format: {set}:{name}
MODULE_DESCRIPTION = _('Short description of the module')
MODULE_AUTHOR = 'ERPlora'
MODULE_CATEGORY = 'category'            # e.g. integrations, finance, operations

MENU = {
    'label': _('My Module'),
    'icon': 'material:icon_name',
    'order': 50,                         # Sidebar order (lower = higher)
}

NAVIGATION = [
    {'label': _('Dashboard'), 'icon': 'speedometer-outline', 'id': 'dashboard'},
    {'label': _('Settings'), 'icon': 'settings-outline', 'id': 'settings'},
]

# --- Pricing (required for paid modules) ---

PRICING = {
    'type': 'subscription',              # free | one_time | subscription
    'subscription_price_monthly': 14.99, # EUR/month (IVA included)
}

# For one-time purchase:
# PRICING = {
#     'type': 'one_time',
#     'price': 49.99,                    # EUR (IVA included)
# }

# For free modules, omit PRICING or:
# PRICING = {
#     'type': 'free',
# }

DEPENDENCIES = ['inventory', 'customers']  # Required module IDs

PERMISSIONS = [
    'my_module.view_mymodel',
    'my_module.add_mymodel',
    'my_module.change_mymodel',
    'my_module.delete_mymodel',
]

ROLE_PERMISSIONS = {
    "admin": ["*"],
    "manager": [
        "view_mymodel",
        "add_mymodel",
        "change_mymodel",
    ],
    "employee": [
        "view_mymodel",
    ],
}

# Optional
COMPATIBILITY = {
    'min_erplora_version': '1.0.0',
}
```

### Fields Extracted by Cloud

Cloud's `parse_module_py()` uses Python AST to safely extract these constants:

| Constant | Cloud Field | Notes |
|----------|-------------|-------|
| `MODULE_ID` | `module_id` | Required, unique identifier |
| `MODULE_NAME` | `name` | Required, supports `_()` |
| `MODULE_VERSION` | `version` | Required, semver |
| `MODULE_DESCRIPTION` | `description` | Supports `_()` |
| `MODULE_AUTHOR` | `author` | |
| `MODULE_ICON` | `ionic_icon` | |
| `FUNCTIONAL_UNIT` | `functional_unit` | UFO code |
| `PRICING` | `module_type`, `price`, `subscription_price_monthly` | Dict |
| `COMPATIBILITY` | `min_erplora_version` | Dict |
| `DEPENDENCIES` | `dependencies` | List |

**Important**: `PRICING` is only read during initial import (`create_module_from_git`). Subsequent syncs update name, version, description, etc., but NOT pricing.

---

## Publishing to Cloud Marketplace

### 1. Create the module code

Develop locally in `hub/modules/{module_id}/`.

### 2. Create a private GitHub repo

```bash
cd hub/modules/{module_id}
git init
git add .
git commit -m "feat: initial module"
gh repo create ERPlora/module-{name} --private --source=. --push
```

Convention: repo name = `module-{module_id}` with underscores replaced by hyphens.

### 3. Import to Cloud

Use the Developer API:

```bash
# Single import
curl -X POST https://erplora.com/api/developer/repos/import/ \
  -H "Authorization: Bearer {jwt_token}" \
  -H "Content-Type: application/json" \
  -d '{"repo_url": "https://github.com/ERPlora/module-{name}", "branch": "main"}'

# Bulk import
curl -X POST https://erplora.com/api/developer/repos/import/bulk/ \
  -H "Authorization: Bearer {jwt_token}" \
  -H "Content-Type: application/json" \
  -d '{
    "repositories": [
      {"repo_url": "https://github.com/ERPlora/module-foo", "branch": "main"},
      {"repo_url": "https://github.com/ERPlora/module-bar", "branch": "main"}
    ]
  }'
```

Or via the web UI: `https://erplora.com/dashboard/vendor/developer/repos/add/`

### 4. Private repo access

For the import to work, Cloud needs to read `module.py` from the repo. Two options:

**Option A — GitHub App (recommended)**:
1. Go to GitHub > Settings > Applications > ERPlora App
2. Add the new repos to "Repository access"
3. Import works immediately with private repos

**Option B — Temporary public**:
1. Make repos public: `gh repo edit ERPlora/module-{name} --visibility public`
2. Run the import
3. Make repos private again: `gh repo edit ERPlora/module-{name} --visibility private --accept-visibility-change-consequences`

### 5. Auto-sync on push

Once imported, pushing to the repo triggers automatic sync:
- GitHub webhook → Cloud → re-downloads ZIP → uploads to S3 → updates module metadata
- Hub marketplace sees updated module on next check

---

## View Patterns

### Standard module view

```python
from apps.accounts.decorators import login_required, permission_required
from apps.modules_runtime.navigation import with_module_nav
from apps.core.htmx import htmx_view

@login_required
@permission_required('my_module.view_mymodel')
@with_module_nav('my_module', 'dashboard')   # BEFORE @htmx_view
@htmx_view('my_module/pages/dashboard.html', 'my_module/partials/dashboard_content.html')
def dashboard(request):
    return {'items': MyModel.objects.all()}
```

### Template hierarchy

```
base.html → app_base.html → page_base.html → module_base.html → your template
```

Pages extend `module_base.html` and use `{% block module_content %}`.

---

## Models

All module models must extend `HubBaseModel`:

```python
from apps.core.models import HubBaseModel

class MyModel(HubBaseModel):
    name = models.CharField(max_length=200)
    # ...

    class Meta:
        verbose_name = _('My Model')
```

---

## AI Tools

```python
from modules.assistant.tool_registry import register_tool, AssistantTool

@register_tool
class MyTool(AssistantTool):
    name = "my_module_action"
    description = "Does something in my module"
    module_id = "my_module"
    parameters = {
        "param1": {"type": "string", "description": "..."},
    }
    required = ["param1"]

    def execute(self, arguments, context):
        # Implementation
        return {"status": "success", "message": "Done"}
```

---

## Pricing Reference (Current Modules)

| Module | Type | Price/month |
|--------|------|-------------|
| Shopify Connect | subscription | 14.99 EUR |
| WooCommerce Connect | subscription | 12.99 EUR |
| PrestaShop Connect | subscription | 12.99 EUR |
| Magento Connect | subscription | 19.99 EUR |
| All other modules | free | — |
