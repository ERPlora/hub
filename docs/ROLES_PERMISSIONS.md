# Sistema de Roles y Permisos - ERPlora Hub

## Resumen

El sistema de permisos es **granular** y **multi-tenant** (por Hub). Usa:
- **Permisos**: Acciones específicas (`module.action`)
- **Roles**: Colecciones de permisos con soporte para **wildcards**
- **LocalUser**: Usuario con un rol + permisos extras opcionales

---

## 1. Definir Permisos en un Módulo

Los permisos se definen en `module.py` de cada módulo:

```python
# modules/inventory/module.py

MODULE_ID = 'inventory'
MODULE_NAME = 'Inventory'

PERMISSIONS = [
    ('view_product', 'Can view products'),
    ('add_product', 'Can add products'),
    ('change_product', 'Can edit products'),
    ('delete_product', 'Can delete products'),
    ('export_data', 'Can export inventory data'),
]
```

**Formato**: `(action_suffix, description)` → Se convierte en `{module_id}.{action_suffix}`

Ejemplo: `('view_product', '...')` → `inventory.view_product`

---

## 2. Sincronizar Permisos

Los permisos se sincronizan desde los módulos a la base de datos:

```python
from apps.core.services.permission_service import PermissionService

# Sincronizar todos los módulos
PermissionService.sync_all_module_permissions(hub_id)

# O sincronizar un módulo específico
PermissionService.sync_module_permissions(hub_id, 'inventory', PERMISSIONS)
```

**Via UI**: `/roles/sync-permissions/` (requiere admin)

---

## 3. Roles por Defecto

El sistema crea 3 roles por defecto:

| Rol | Wildcards | Descripción |
|-----|-----------|-------------|
| `admin` | `*` | Acceso total |
| `manager` | `inventory.*`, `sales.*`, `customers.*`, `cash_register.*` | Acceso a módulos principales |
| `employee` | `inventory.view_*`, `sales.view_*`, `sales.add_sale`, etc. | Solo operaciones básicas |

```python
# Crear roles por defecto
PermissionService.create_default_roles(hub_id)
```

**Via UI**: `/roles/create-defaults/`

---

## 4. Wildcards

Los wildcards permiten asignar grupos de permisos:

| Patrón | Significado |
|--------|-------------|
| `*` | Todos los permisos |
| `inventory.*` | Todos los permisos del módulo inventory |
| `inventory.view_*` | Todos los permisos que empiecen con `view_` en inventory |
| `*.view_*` | Todos los permisos `view_` de todos los módulos |

---

## 5. Crear un Rol Personalizado

### Via UI

1. Ir a `/roles/create/`
2. Ingresar nombre (ej: `accountant`) y display name
3. Ir al detalle del rol
4. Asignar permisos individuales o wildcards

### Via Código

```python
from apps.accounts.models import Role, RolePermission, Permission

# Crear el rol
role = Role.objects.create(
    hub_id=hub_id,
    name='accountant',
    display_name='Accountant',
    is_system=False,
)

# Opción A: Asignar wildcard (todos los permisos de un módulo)
RolePermission.objects.create(
    hub_id=hub_id,
    role=role,
    permission=None,  # NULL porque es wildcard
    wildcard='invoicing.*'
)

# Opción B: Asignar permiso específico
perm = Permission.objects.get(codename='sales.view_sale', hub_id=hub_id)
RolePermission.objects.create(
    hub_id=hub_id,
    role=role,
    permission=perm,
    wildcard=''  # Vacío porque es permiso directo
)
```

---

## 6. Asignar Rol a Usuario

```python
from apps.accounts.models import LocalUser, Role

user = LocalUser.objects.get(email='john@example.com', hub_id=hub_id)
role = Role.objects.get(name='accountant', hub_id=hub_id)

user.role_obj = role
user.role = role.name  # Campo legacy
user.save()
```

---

## 7. Verificar Permisos

### En Views (Decorators)

```python
from apps.accounts.decorators import permission_required, admin_required

# Requiere UN permiso
@permission_required('inventory.view_product')
def product_list(request):
    ...

# Requiere TODOS los permisos
@permission_required('inventory.view_product', 'inventory.change_product')
def product_edit(request):
    ...

# Requiere CUALQUIERA de los permisos
@permission_required('inventory.view_product', 'sales.view_sale', any_perm=True)
def dashboard(request):
    ...

# Solo admin
@admin_required
def admin_settings(request):
    ...
```

### En Código

```python
user = LocalUser.objects.get(id=user_id)

# Verificar un permiso
if user.has_perm('inventory.add_product'):
    # Puede agregar productos
    ...

# Obtener todos los permisos
perms = user.get_permissions()  # Set de codenames
```

### En Templates

```django
{% if request.user.has_perm 'sales.add_sale' %}
    <ion-button>Nueva Venta</ion-button>
{% endif %}
```

---

## 8. Modelos de Base de Datos

```
accounts_permission
├── codename (UNIQUE per hub)  # "inventory.view_product"
├── name                        # "Can view products"
├── module_id                   # "inventory"
└── hub_id

accounts_role
├── name (UNIQUE per hub)       # "admin", "manager", "accountant"
├── display_name                # "Administrator"
├── is_system                   # true = no se puede eliminar
├── is_active                   # false = no se puede asignar
└── hub_id

accounts_rolepermission
├── role_id
├── permission_id (NULLABLE)    # Si es permiso directo
├── wildcard                    # Si es patrón ("inventory.*")
└── hub_id
# REGLA: permission XOR wildcard (uno u otro, no ambos)

accounts_localuser
├── role_obj (FK → Role)        # Rol principal
├── extra_permissions (M2M)     # Permisos adicionales
└── ...
```

---

## 9. Flujo Completo

```
┌──────────────────────────────────────────────────────────┐
│  Usuario accede a /products/                             │
└──────────────────────────────────────────────────────────┘
                           ↓
┌──────────────────────────────────────────────────────────┐
│  @permission_required('inventory.view_product')          │
│  Decorator verifica sesión y obtiene LocalUser           │
└──────────────────────────────────────────────────────────┘
                           ↓
┌──────────────────────────────────────────────────────────┐
│  user.has_perm('inventory.view_product')                 │
│  - Si es admin → PASA                                    │
│  - Si no → busca en get_permissions()                    │
└──────────────────────────────────────────────────────────┘
                           ↓
┌──────────────────────────────────────────────────────────┐
│  user.get_permissions()                                  │
│  = role_obj.get_all_permissions()                        │
│    + extra_permissions                                   │
└──────────────────────────────────────────────────────────┘
                           ↓
┌──────────────────────────────────────────────────────────┐
│  role.get_all_permissions() expande wildcards:           │
│  "inventory.*" → {"inventory.view_product",              │
│                   "inventory.add_product", ...}          │
└──────────────────────────────────────────────────────────┘
                           ↓
┌──────────────────────────────────────────────────────────┐
│  RESULTADO:                                              │
│  - Si permiso está en el set → Acceso permitido          │
│  - Si no → 403 Forbidden                                 │
└──────────────────────────────────────────────────────────┘
```

---

## 10. Archivos Clave

| Archivo | Descripción |
|---------|-------------|
| `apps/accounts/models.py` | Permission, Role, RolePermission, LocalUser |
| `apps/core/services/permission_service.py` | Sync, wildcards, roles por defecto |
| `apps/accounts/decorators.py` | @permission_required, @admin_required |
| `apps/main/roles/views.py` | CRUD de roles |
| `apps/main/roles/api.py` | API para asignar permisos |
| `modules/{module}/module.py` | Define PERMISSIONS del módulo |

---

## 11. Ejemplo: Nuevo Módulo con Permisos

```python
# modules/reservations/module.py

MODULE_ID = 'reservations'
MODULE_NAME = 'Reservations'
MODULE_ICON = 'calendar-outline'

PERMISSIONS = [
    ('view_reservation', 'Can view reservations'),
    ('add_reservation', 'Can create reservations'),
    ('change_reservation', 'Can edit reservations'),
    ('delete_reservation', 'Can delete reservations'),
    ('confirm_reservation', 'Can confirm reservations'),
    ('cancel_reservation', 'Can cancel reservations'),
]

# Navigation items del módulo
NAVIGATION = [
    {'label': 'Reservations', 'url': 'list', 'icon': 'calendar-outline'},
]
```

Después de crear el módulo:

```python
# Sincronizar para que aparezcan en la DB
PermissionService.sync_all_module_permissions(hub_id)
```

Los permisos quedarán disponibles para asignar a roles:
- `reservations.view_reservation`
- `reservations.add_reservation`
- etc.
