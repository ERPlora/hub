# ERPlora Hub

Modular POS (Point of Sale) system built with Django 5.2 + HTMX + Alpine.js.

---

## Architecture

| Component | Technology |
|-----------|------------|
| Backend | Django 5.2 |
| Frontend | UX CSS + Alpine.js + HTMX |
| Database | PostgreSQL 17 |
| Icons | djicons (template tags) |
| Auth | LocalUser with PIN + JWT (Cloud API) |
| API | Django REST Framework + drf-spectacular |
| Scheduler | APScheduler (backups) |
| Deployment | Docker (Dokploy) for Cloud Hubs |

### Deployment Modes

1. **Local (Development)**: Django runserver + PostgreSQL, modules in `~/Library/Application Support/ERPloraHub/`
2. **Sandbox**: Isolated environment for testing setup wizard (`HUB_ENV=sandbox python manage.py sandbox`)
3. **Cloud Hub (SaaS)**: Docker container, PostgreSQL on dedicated server, access via `{subdomain}.a.erplora.com`

### Data Paths (auto-detected)

| Platform | Base Directory |
|----------|---------------|
| macOS | `~/Library/Application Support/ERPloraHub/` |
| Linux | `~/.erplora-hub/` |
| Docker | `/app/data/` |

Subdirectories: `modules/`, `media/`, `logs/`, `backups/`, `reports/`

---

## Installation (Development)

### Requirements

- Python 3.11+
- PostgreSQL 17+
- uv (Python package manager)

```bash
cd hub

# Create virtual environment with uv
uv venv
source .venv/bin/activate  # Linux/macOS

# Install dependencies
uv pip install -e ".[dev]"

# Apply migrations
python manage.py migrate

# Development server (port 8000)
python manage.py runserver
```

The Hub runs on port **8000** by default (Cloud Portal uses 8001).

### Configuration

The Hub works **without any `.env` file** — all settings have sensible defaults. Optionally, create a `hub/.env` to override specific variables. See `.env.example` for all available options.

| Variable | Default | Description |
|----------|---------|-------------|
| `HUB_ENV` | `local` | Environment: `local`, `sandbox`, `web` |
| `CLOUD_API_URL` | `https://erplora.com` | Cloud URL (marketplace, sync) |
| `DATABASE_URL` | (required in web) | PostgreSQL connection URL |
| `MODULES_DIR` | auto (DataPaths) | Installed modules directory |
| `ERPLORA_DEV_MODE` | `true` | Relaxes module validation |
| `DEBUG_TOOLBAR` | `false` | Enables Django Debug Toolbar |
| `SECRET_KEY` | auto-generated | Django secret key |

---

## Project Structure

```
hub/
├── apps/                      # Django applications (11 core)
│   ├── accounts/             # LocalUser, Role, PIN auth, permissions
│   ├── auth/login/           # Login views
│   ├── configuration/        # HubConfig, StoreConfig (singletons + cache)
│   ├── core/                 # HTMX helpers, middleware, context processors, bridge_helpers
│   ├── main/                 # Dashboard, settings, employees, files, roles
│   ├── modules_runtime/      # Dynamic module loading, navigation, URL routing
│   ├── marketplace/          # Module store (Hub-side), cart, checkout
│   ├── setup/                # Setup wizard (Region → Modules → Business → Tax)
│   ├── sync/                 # Hub ↔ Cloud sync (JWT, heartbeat, commands)
│   └── system/modules/       # System info, diagnostics
├── config/
│   ├── settings/
│   │   ├── __init__.py      # Environment selector (HUB_ENV)
│   │   ├── base.py          # Common settings
│   │   ├── local.py         # Local development
│   │   ├── sandbox.py       # Sandbox (isolated testing)
│   │   └── web.py           # Docker/Cloud
│   ├── paths.py             # DataPaths (cross-platform)
│   └── urls.py
├── templates/               # Global templates
├── static/                  # CSS/JS/images
├── locale/                  # i18n translations (en, es)
├── Dockerfile
└── pyproject.toml
```

---

## Template Hierarchy

```
base.html → app_base.html (sidebar) → page_base.html (navbar + #main-content-area) → module_base.html (auto tabbar)
```

- Module pages extend `module_base.html`, use `{% block module_content %}`
- `module_base.html` auto-renders tabbar from `navigation` context variable
- On full-page requests, `@htmx_view` injects `content_template` so the correct partial renders on browser refresh

### @htmx_view Decorator

```python
from apps.core.htmx import htmx_view

@login_required
@htmx_view('module/pages/index.html', 'module/partials/content.html')
def index(request):
    # Normal request → full page | HTMX request → partial only
    return {'items': Item.objects.all()}
```

### Module View with Decorators

```python
from apps.accounts.decorators import login_required, permission_required
from apps.modules_runtime.navigation import with_module_nav
from apps.core.htmx import htmx_view

@login_required
@permission_required('inventory.view_product')
@with_module_nav('inventory', 'products')  # BEFORE @htmx_view
@htmx_view('inventory/pages/products.html', 'inventory/partials/products_list.html')
def products(request):
    return {'products': Product.objects.all()}
```

### HTMX Navigation

```html
<button hx-get="{% url 'module:view' %}" hx-target="#main-content-area" hx-push-url="true" class="tab">
    {% icon "cube-outline" %}
    <span>Module</span>
</button>
```

### Alpine.js Interactivity

```html
<div x-data="{ open: false }">
    <button @click="open = true" class="btn">Open</button>
    <div class="modal-backdrop" :data-state="open ? 'open' : 'closed'">
        <div class="modal">...</div>
    </div>
</div>
```

---

## Configuration System (Singleton + Cache)

Two singleton models with automatic 1-hour cache and auto-invalidation on save.

### HubConfig

`apps.configuration.models.HubConfig` — Hub credentials, language, theme, currency.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `hub_id` | UUIDField | null | Cloud ID |
| `cloud_api_token` | CharField | '' | HTTP auth token for Cloud API |
| `is_configured` | BooleanField | False | Setup wizard completed |
| `selected_blocks` | JSONField | [] | Functional block slugs |
| `solution_slug` | CharField | '' | Legacy, kept for retrocompat |
| `os_language` | CharField | 'en' | System language |
| `currency` | CharField | 'EUR' | Transaction currency |
| `color_theme` | CharField | 'default' | Color theme |
| `dark_mode` | BooleanField | False | Dark mode |
| `auto_print` | BooleanField | False | Auto-print tickets |

### StoreConfig

`apps.configuration.models.StoreConfig` — Business info, tax, receipts.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `business_name` | CharField | '' | Business name |
| `business_address` | TextField | '' | Address |
| `vat_number` | CharField | '' | NIF/CIF/VAT |
| `phone` / `email` / `website` | CharField | '' | Contact info |
| `logo` | ImageField | null | Business logo |
| `tax_rate` | DecimalField | 0.00 | Tax rate % |
| `tax_included` | BooleanField | True | Prices include tax |
| `receipt_header` / `receipt_footer` | TextField | '' | Receipt text |

### Usage

```python
from apps.configuration.models import HubConfig, StoreConfig

# Get singleton instance (cached)
hub_config = HubConfig.get_solo()

# Get/set specific values
currency = HubConfig.get_value('currency', 'EUR')
HubConfig.set_value('dark_mode', True)

# Update multiple fields
StoreConfig.update_values(business_name='Mi Tienda', tax_rate=21.00)
```

In templates (auto-injected via context processor):
```django
{{ HUB_CONFIG.currency }}
{{ STORE_CONFIG.business_name }}
{% if STORE_CONFIG.tax_included %}Tax included{% endif %}
```

---

## Module System (Filesystem-Based)

Modules are Django apps in an external directory. State is determined by folder name (no database).

| Prefix | State | Example |
|--------|-------|---------|
| (none) | Active, loaded | `inventory/` |
| `_` | Inactive, visible in UI | `_cash_register/` |
| `.` | Hidden | `.experimental/` |

### Module Structure

```
modules/{module_id}/
├── module.py          # Metadata (REQUIRED)
├── __init__.py
├── apps.py
├── models.py
├── views.py
├── urls.py
├── forms.py
├── templates/{module_id}/
│   ├── pages/         # Full page templates
│   └── partials/      # HTMX partials
├── static/{module_id}/
├── migrations/
└── locale/            # i18n (optional)
```

### module.py

```python
from django.utils.translation import gettext_lazy as _

MODULE_ID = 'inventory'
MODULE_NAME = _('Inventory')
MODULE_ICON = 'cube-outline'
MODULE_CATEGORY = 'commerce'
DEPENDENCIES = []  # Other module IDs

MENU = {
    'label': _('Inventory'),
    'icon': 'cube-outline',
    'order': 10,
}

NAVIGATION = [
    {'label': _('Products'), 'icon': 'storefront-outline', 'id': 'products'},
    {'label': _('Stock'), 'icon': 'layers-outline', 'id': 'stock'},
]

PERMISSIONS = [
    'inventory.view_product',
    'inventory.change_product',
    'inventory.delete_product',
]
```

### Activation Flow

1. Module downloaded as `_module_id/` (inactive)
2. User clicks "Activate" → folder renamed to `module_id/`
3. Server restart required (Django loads INSTALLED_APPS at startup)
4. On startup: `modules_runtime` scans filesystem → adds to INSTALLED_APPS → imports models → runs migrations → registers URLs at `/m/{module_id}/`
5. Menu items generated from `module.py` MENU config

### URL Registration

All modules mount under `/m/`:
```
/m/inventory/     → inventory.urls
/m/sales/         → sales.urls
/m/customers/     → customers.urls
```

### Active Modules (75)

accounting, accounting_sync, analytics, api_connect, appointments, approvals, assets, attendance, audit_log, bank_sync, budgets, campaigns, cash_register, commissions, contracts, course_mgmt, customers, data_export, discounts, doc_templates, ecommerce, email_marketing, esign, expenses, facturae, facturae_b2b, feedback, field_service, file_manager, fleet, gdpr, gift_cards, inventory, invoicing, knowledge_base, leads, leave, live_chat, loyalty, maintenance, manufacturing, marketplace_connect, messaging, multicurrency, notifications, online_booking, online_payments, patient_records, payroll, pricing, projects, property_mgmt, purchase_orders, quality, quotes, recruitment, referrals, rentals, reports, returns, sales, schedules, segments, services, shipping, sii, staff, student_mgmt, subscriptions, support, surveys, tasks, tax, training, voip, warehouse

### Disabled Modules (5, prefixed with `_`)

_kitchen, _orders, _reservations, _tables, _verifactu

---

## Roles & Permissions

### Models

- **Permission**: `codename` (e.g. `inventory.view_product`), `name`, `module_id`
- **Role**: `name`, `display_name`, `permissions` (M2M through RolePermission), `source` field, `is_system`, `is_active`
- **RolePermission**: `role`, `permission`, `wildcard` (supports `*`, `inventory.*`, `inventory.view_*`)
- **LocalUser**: `role_obj` (FK to Role), `extra_permissions` (M2M), legacy `role` CharField

### Role Sources

| Source | Examples | Editable | Deletable |
|--------|----------|----------|-----------|
| `basic` | admin, manager, employee, viewer | Yes | No (system) |
| `solution` | From selected functional blocks | Yes | Yes |
| `custom` | User-created | Yes | Yes |

### Default Roles

| Role | Permissions |
|------|-------------|
| admin | `*` (all) |
| manager | `inventory.*`, `sales.*`, `customers.*`, `cash_register.*` |
| employee | `inventory.view_*`, `sales.view_*`, `sales.add_sale`, `customers.view_*` |

### Decorators

```python
from apps.accounts.decorators import login_required, permission_required, role_required, admin_required

@login_required
@permission_required('inventory.view_product')
def product_list(request): ...

@permission_required('inventory.view_product', 'sales.view_sale', any_perm=True)
def dashboard(request): ...

@admin_required
def admin_view(request): ...
```

### User Permission Methods

| Method | Description |
|--------|-------------|
| `user.has_perm('inventory.view_product')` | Check specific permission |
| `user.has_perms(['perm1', 'perm2'])` | Check ALL permissions |
| `user.has_any_perm(['perm1', 'perm2'])` | Check ANY permission |
| `user.has_module_perms('inventory')` | Check any module permission |
| `user.get_permissions()` | Set of all codenames |

### PermissionService

```python
from apps.core.services.permission_service import PermissionService

PermissionService.sync_module_permissions(hub_id, 'inventory', [('view_product', 'Can view products')])
PermissionService.create_default_roles(hub_id)
PermissionService.create_solution_roles()
```

---

## Cloud Integration

Hub communicates with Cloud via HTTP REST API.

### Authentication

| Credential | Storage | Usage |
|------------|---------|-------|
| `hub_id` | HubConfig | Hub identity |
| `cloud_api_token` | HubConfig | Permanent token for Hub API calls |
| User JWT | Temporary | User login (discarded after use) |

### Key Endpoints

```
POST /api/auth/login/                     # Get user JWT
POST /api/hubs/register/                  # Hub auto-registration (one-time)
POST /api/hubs/{hub_id}/users/register/   # Register user in Hub
GET  /api/hubs/{hub_id}/users/check/{email}/ # Verify user access
GET  /api/hubs/me/                        # Hub info
POST /api/hubs/me/heartbeat/             # Health check
GET  /api/hubs/me/commands/              # Poll pending commands
GET  /api/auth/public-key/               # RSA public key for JWT validation
GET  /api/marketplace/modules/           # Module marketplace
GET  /api/marketplace/solutions/         # Functional blocks
```

### Sync Strategy: On-Access

- Verification happens **on-demand** during login, not proactively
- Cloud Login: user authenticates → JWT → Hub creates/updates LocalUser → registers with Cloud
- PIN Login: verify PIN locally → if online, check user status with Cloud → fallback to local state if offline

---

## Subscription Verification

Modules can be free, paid (one-time), or subscription.

### Decorator (Recommended)

```python
from apps.modules_runtime.decorators import require_active_subscription

@require_active_subscription
def premium_feature(request):
    # Only runs if subscription is active (402 otherwise)
    ...
```

### Manual Check

```python
from apps.modules_runtime.subscription_checker import get_subscription_checker

checker = get_subscription_checker()
has_access = checker.verify_module_access('analytics', 'subscription')
```

Cache: 5 minutes. Clear with `checker.clear_cache(module_id=X)`.

---

## Printing System

Decoupled printing via Django signals. Modules emit print events; the `printers` module handles routing.

### Usage from Modules

```python
from apps.core.print_helper import print_receipt, print_kitchen_order

print_receipt(receipt_id='SALE-123', items=[...], total=50.00, payment_method='Cash', paid=50.00, change=0.00)
```

### Signals

- `print_ticket_requested` — emitted by any module
- `print_completed` — emitted by printers module on success
- `print_failed` — emitted by printers module on failure

### Printer Selection Order

1. Specific printer (if `printer_id` passed)
2. Printer assigned to document type (lowest `priority` number first)
3. Default printer (`is_default=True`)
4. First active printer

### Document Types

`receipt`, `delivery_note`, `invoice`, `kitchen_order`, `barcode_label`, `cash_session_report`

---

## Internationalization (i18n)

Supported languages: English (default), Spanish.

### Templates

```django
{% load i18n %}
<button>{% trans "Save" %}</button>
{% blocktrans with name=user.name %}Hello {{ name }}{% endblocktrans %}
```

### Python

```python
from django.utils.translation import gettext as _
message = _("Product created successfully")
```

### Workflow

```bash
cd hub

# Extract strings
.venv/bin/python manage.py makemessages -l es --ignore=.venv

# Edit locale/es/LC_MESSAGES/django.po

# Compile
.venv/bin/python manage.py compilemessages --ignore=.venv
```

Modules include their own `locale/` directory.

---

## Static Files & Theming

### CSS Loading Order (base.html)

1. `ux/ux-full.min.css` — UX design system (includes Tailwind v4)
2. Color theme CSS (`css/themes/{theme}/theme.css`) — overrides CSS custom properties
3. `css/main.css` — Hub custom styles (fonts, HTMX/Alpine helpers)

### Themes

Themes override CSS custom properties (`--color-primary`, `--color-error`, etc.). Available: `default` (indigo), `blue` (sky).

Dark mode: `.dark` class on `<html>` or `[data-theme="dark"]`.

Font: Plus Jakarta Sans (loaded locally from `static/fonts/`).

---

## Setup Wizard

4 steps: **Region → Modules → Business → Tax**

- Step 2 (Modules): Fetches functional blocks from Cloud API, user multi-selects
- `HubConfig.selected_blocks` stores list of block slugs
- Roles created from all selected blocks via `PermissionService.create_solution_roles()`

---

## Sandbox (Clean Environment)

For testing the setup wizard, module installation, or any flow that requires starting from scratch **without touching your development data**.

The sandbox uses a dedicated settings file (`config/settings/sandbox.py`) with isolated paths in `ERPloraHub-sandbox/`.

```bash
cd hub
source .venv/bin/activate

# Start sandbox (wipes DB + modules, runs migrate, starts server)
HUB_ENV=sandbox python manage.py sandbox

# Custom port
HUB_ENV=sandbox python manage.py sandbox 8080

# Wipe + migrate only (no server)
HUB_ENV=sandbox python manage.py sandbox --no-run
```

### Behavior

- **First launch**: wipes DB and modules, runs migrate, starts server with auto-reload
- **Reloader restart** (after module install via setup wizard): runs migrate, loads new modules — NO wipe
- **Manual restart** (Ctrl+C + run `sandbox` again): wipes everything, starts fresh

---

## Docker Deployment (Cloud Hub)

### Environment Variables

**Required:**
```bash
HUB_ID=uuid                          # Hub identity
HUB_NAME=tienda-de-maria             # Hub name
DEPLOYMENT_MODE=web                   # Must be "web"
DATABASE_URL=postgresql://...         # PostgreSQL connection
CLOUD_BASE_URL=https://erplora.com   # Cloud API
HUB_JWT=hub_jwt_token                # JWT for Cloud auth
SECRET_KEY=random-secret-key         # Django secret key
```

**Optional:** `DEBUG`, `LOG_LEVEL`, `AWS_*` (S3 storage), `PARENT_DOMAIN`

### Volumes

| Path | Purpose | Persist |
|------|---------|---------|
| `/app/data/modules/` | Installed modules | Yes |
| `/app/media/` | Uploaded files | Yes |
| `/app/logs/` | Application logs | Optional |

### Health Check

```bash
curl http://localhost:8000/health/
# {"status": "ok", "database": "ok", "version": "..."}
```

### Build & Run

```bash
docker build -t erplora/hub:latest .
docker run -d -p 8000:8000 -e HUB_ID=test-hub-123 erplora/hub:latest
```

Dockerfile: single-stage with `uv` (no venv — Docker is the isolated environment).

---

## Testing

```bash
cd hub
source .venv/bin/activate

pytest                              # All tests (481+)
pytest apps/accounts/tests/ -v     # Specific app
pytest -m unit                      # By marker
pytest --cov=apps --cov-report=html # With coverage
```

### Markers

`unit`, `integration`, `core`, `pos`, `products`, `sales`, `modules`, `hardware`, `sync`, `slow`

### Key Fixtures

- `cleanup_test_artifacts` (autouse) — removes test directories after each test
- `admin_user`, `employee_user` — LocalUser with roles
- `authenticated_client` — Django client with admin session
- `configured_store`, `configured_hub` — Singleton configs

### Settings

`pytest.ini` sets `DJANGO_SETTINGS_MODULE = config.settings`. Use `@pytest.mark.django_db` or `db` fixture for DB access.

---

## License

ERPlora Hub is licensed under **Business Source License 1.1 (BUSL-1.1)**.

**Permitted uses (free):**
- Internal business use
- Personal and educational use
- Building modules for the ecosystem
- Consulting services

**Prohibited uses:**
- Offering as SaaS/PaaS
- Creating a competing POS platform
- Reselling or sublicensing

After **2036-01-02**, it converts to **Apache License 2.0**.
