# Sistema de Roles y Permisos

Este documento describe el sistema de roles y permisos implementado en ERPlora Hub.

---

## Tabla de Contenidos

1. [Resumen](#resumen)
2. [Arquitectura](#arquitectura)
3. [Modelos](#modelos)
4. [Roles del Sistema](#roles-del-sistema)
5. [Permisos](#permisos)
6. [PermissionService](#permissionservice)
7. [Decorators](#decorators)
8. [API de Roles](#api-de-roles)
9. [UI de Gestión](#ui-de-gestión)
10. [Uso en Módulos](#uso-en-módulos)
11. [Tests](#tests)

---

## Resumen

El sistema de roles y permisos permite:

- **Roles editables**: admin, manager, employee (y roles personalizados)
- **Permisos granulares**: Derivados de los módulos activos
- **Asignación flexible**: Permisos por rol + permisos extra por usuario
- **Enforcement**: Decorators para proteger vistas

### Diagrama de Relaciones

```
┌─────────────────────────────────────────────────────────────────┐
│                    PERMISSION SYSTEM                             │
│                                                                  │
│  ┌──────────────────┐    ┌──────────────────┐                   │
│  │      Role        │───▶│  RolePermission  │◀──┐               │
│  │  - name          │    │  (M2M through)   │   │               │
│  │  - description   │    └──────────────────┘   │               │
│  │  - is_system     │                           │               │
│  │  - is_active     │    ┌──────────────────┐   │               │
│  └──────────────────┘    │   Permission     │───┘               │
│           │              │  - codename      │                    │
│           │              │  - name          │                    │
│           ▼              │  - module_id     │                    │
│  ┌──────────────────┐    └──────────────────┘                    │
│  │    LocalUser     │                                            │
│  │  - role_obj (FK) │                                            │
│  │  - extra_perms   │ ◀── Permisos adicionales por usuario      │
│  └──────────────────┘                                            │
└─────────────────────────────────────────────────────────────────┘
```

---

## Arquitectura

### Archivos Principales

| Archivo | Descripción |
|---------|-------------|
| `apps/accounts/models.py` | Modelos: Permission, Role, RolePermission, LocalUser |
| `apps/accounts/decorators.py` | Decorators: @login_required, @role_required, @permission_required, @admin_required |
| `apps/core/services/permission_service.py` | Servicio para sincronizar permisos y crear roles |
| `apps/main/roles/views.py` | Vistas y API para gestión de roles |
| `apps/main/roles/urls.py` | URLs del módulo de roles |
| `apps/main/roles/templates/` | Templates de UI |

### Flujo de Datos

```
1. Startup del Hub
   └── PermissionService.initialize()
       ├── sync_module_permissions()  → Sincroniza PERMISSIONS de módulos a BD
       └── create_default_roles()      → Crea admin, manager, employee

2. Request a vista protegida
   └── @permission_required('inventory.view_product')
       ├── Obtiene LocalUser de session
       ├── Verifica user.has_perm('inventory.view_product')
       └── Permite o deniega acceso

3. Admin edita rol
   └── UI de Roles → API → Actualiza RolePermission
```

---

## Modelos

### Permission

Representa un permiso granular que puede asignarse a roles.

```python
class Permission(HubBaseModel):
    codename = models.CharField(max_length=100)  # "inventory.view_product"
    name = models.CharField(max_length=255)       # "Can view product"
    module_id = models.CharField(max_length=50)   # "inventory"
```

**Formato del codename**: `{module_id}.{action}_{model}`

Ejemplos:
- `customers.view_customer`
- `inventory.add_product`
- `sales.delete_sale`
- `accounts.change_user`

### Role

Agrupa permisos. Los roles del sistema (admin, manager, employee) están protegidos.

```python
class Role(HubBaseModel):
    name = models.CharField(max_length=50)
    display_name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    permissions = models.ManyToManyField(Permission, through='RolePermission')
    is_system = models.BooleanField(default=False)  # No se puede eliminar
    is_active = models.BooleanField(default=True)   # Si False, no se puede asignar
```

### RolePermission

Modelo through para la relación M2M entre Role y Permission. Soporta wildcards.

```python
class RolePermission(HubBaseModel):
    role = models.ForeignKey(Role, on_delete=models.CASCADE)
    permission = models.ForeignKey(Permission, null=True, on_delete=models.CASCADE)
    wildcard = models.CharField(max_length=100, blank=True)  # e.g., "*", "inventory.*"
```

### LocalUser (campos relacionados)

```python
class LocalUser(HubBaseModel):
    # Legacy role (para compatibilidad)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='employee')

    # Nuevo sistema de roles
    role_obj = models.ForeignKey(Role, on_delete=models.SET_NULL, null=True)

    # Permisos extra individuales
    extra_permissions = models.ManyToManyField(Permission, related_name='users_extra')
```

**Métodos de permisos**:

| Método | Descripción |
|--------|-------------|
| `get_role_name()` | Nombre del rol (usa role_obj o fallback a legacy) |
| `get_permissions()` | Set de codenames de permisos (rol + extra) |
| `has_perm(codename)` | Verifica si tiene un permiso específico |
| `has_perms([codenames])` | Verifica si tiene TODOS los permisos |
| `has_any_perm([codenames])` | Verifica si tiene ALGUNO de los permisos |
| `has_module_perms(module_id)` | Verifica si tiene algún permiso del módulo |

---

## Roles del Sistema

### Roles por Defecto

| Rol | Descripción | Permisos |
|-----|-------------|----------|
| `admin` | Acceso completo | `*` (todos) |
| `manager` | Gestión de ventas, inventario | `inventory.*`, `sales.*`, `customers.*`, `cash_register.*` |
| `employee` | Operaciones básicas POS | `inventory.view_*`, `sales.view_*`, `sales.add_sale`, `sales.process_payment`, `customers.view_*` |

### Características de Roles del Sistema

- **No se pueden eliminar** (`is_system=True`)
- **Se pueden editar** (cambiar permisos asignados)
- **El rol admin no se puede desactivar**

### Roles Personalizados

Los usuarios admin pueden crear roles personalizados:
- Se crean con `is_system=False`
- Se pueden eliminar (si no tienen usuarios asignados)
- Se pueden activar/desactivar

---

## Permisos

### Permisos de Módulos

Cada módulo define sus permisos en `module.py`:

```python
# modules/inventory/module.py
PERMISSIONS = [
    ("view_product", "Can view products"),
    ("add_product", "Can add products"),
    ("change_product", "Can edit products"),
    ("delete_product", "Can delete products"),
]
```

### Wildcards en Patrones

El sistema soporta wildcards para asignar permisos:

| Patrón | Significado | Ejemplo |
|--------|-------------|---------|
| `*` | Todos los permisos | `*` |
| `module.*` | Todos los permisos del módulo | `sales.*` |
| `module.action_*` | Todos los permisos de una acción | `inventory.view_*` |
| `module.action_model` | Permiso exacto | `customers.add_customer` |

---

## PermissionService

Servicio central para gestión de permisos.

### Métodos Principales

#### sync_module_permissions(hub_id, module_id, permissions)

Sincroniza permisos de un módulo a la base de datos.

```python
from apps.core.services.permission_service import PermissionService

count = PermissionService.sync_module_permissions(
    hub_id=str(hub_id),
    module_id='inventory',
    permissions=[
        ('view_product', 'Can view products'),
        ('add_product', 'Can add products'),
    ]
)
```

#### create_default_roles(hub_id)

Crea los roles del sistema si no existen.

```python
roles = PermissionService.create_default_roles(str(hub_id))
# Returns: [Role(admin), Role(manager), Role(employee)]
```

#### expand_role_permissions(role)

Expande wildcards y retorna todos los permisos de un rol.

```python
permissions = PermissionService.expand_role_permissions(role)
# Returns: {'inventory.view_product', 'inventory.add_product', ...}
```

---

## Decorators

### @login_required

Requiere que el usuario esté autenticado.

```python
from apps.accounts.decorators import login_required

@login_required
def my_view(request):
    ...

# Con URL de redirección personalizada
@login_required(redirect_url='/custom-login/')
def my_view(request):
    ...
```

### @role_required

Requiere que el usuario tenga uno de los roles especificados.

```python
from apps.accounts.decorators import role_required

@login_required
@role_required('admin', 'manager')
def manager_view(request):
    ...
```

### @permission_required

Requiere que el usuario tenga permisos específicos.

```python
from apps.accounts.decorators import permission_required

# Requiere UN permiso
@permission_required('inventory.view_product')
def product_list(request):
    ...

# Requiere TODOS los permisos
@permission_required('inventory.view_product', 'inventory.change_product')
def product_edit(request):
    ...

# Requiere ALGUNO de los permisos
@permission_required('inventory.view_product', 'sales.view_sale', any_perm=True)
def dashboard(request):
    ...
```

### @admin_required

Shortcut para requerir rol admin.

```python
from apps.accounts.decorators import admin_required

@admin_required
def admin_only_view(request):
    ...
```

---

## API de Roles

### Endpoints

Base URL: `/main/roles/`

| Método | URL | Descripción |
|--------|-----|-------------|
| GET | `/` | Lista de roles |
| GET | `/create/` | Formulario crear rol |
| POST | `/create/` | Crear rol |
| GET | `/<uuid>/` | Detalle de rol |
| GET | `/<uuid>/edit/` | Formulario editar rol |
| POST | `/<uuid>/edit/` | Actualizar rol |
| GET | `/<uuid>/delete/` | Confirmación eliminar |
| POST | `/<uuid>/delete/` | Eliminar rol |
| GET | `/<uuid>/toggle-active/` | Activar/desactivar rol |
| GET | `/sync-permissions/` | Sincronizar permisos de módulos |
| GET | `/create-defaults/` | Crear roles por defecto |

### API JSON

#### Actualizar Permisos

```javascript
POST /main/roles/api/<uuid>/permissions/
Content-Type: application/json

{
    "add": ["inventory.view_product", "inventory.add_product"],
    "remove": ["inventory.delete_product"]
}

// Response
{
    "success": true,
    "added": 2,
    "removed": 1
}
```

#### Añadir Wildcard

```javascript
POST /main/roles/api/<uuid>/wildcard/
Content-Type: application/json

{
    "wildcard": "inventory.*"
}

// Response
{
    "success": true,
    "wildcard": "inventory.*"
}
```

#### Eliminar Wildcard

```javascript
POST /main/roles/api/<uuid>/wildcard/<pattern>/

// Response
{
    "success": true
}
```

---

## UI de Gestión

### Ubicación

```
apps/main/roles/
├── __init__.py
├── apps.py
├── urls.py
├── views.py
├── api.py
└── templates/main/roles/
    ├── role_list.html
    ├── role_detail.html
    ├── role_form.html
    └── role_confirm_delete.html
```

### Vista de Lista

- Muestra todos los roles (sistema primero)
- Badge de sistema para roles protegidos
- Contador de usuarios por rol
- Botones: Crear, Sync Permissions, Create Defaults

### Vista de Detalle

- Información del rol
- Wildcards asignados (con posibilidad de añadir/eliminar)
- Permisos agrupados por módulo con checkboxes
- Botones: Edit, Delete, Toggle Active

---

## Uso en Módulos

### Definir Permisos en un Módulo

```python
# modules/my_module/module.py
MODULE_ID = "my_module"
VERSION = "1.0.0"

PERMISSIONS = [
    ("view_item", "Can view items"),
    ("add_item", "Can add items"),
    ("change_item", "Can edit items"),
    ("delete_item", "Can delete items"),
]
```

### Proteger Vistas del Módulo

```python
# modules/my_module/views.py
from apps.accounts.decorators import permission_required

@permission_required('my_module.view_item')
def item_list(request):
    ...

@permission_required('my_module.add_item')
def item_create(request):
    ...

@permission_required('my_module.view_item', 'my_module.change_item')
def item_edit(request, item_id):
    ...
```

### Verificar Permisos en Templates

```html
{% if request.user.has_perm 'my_module.add_item' %}
    <ion-button href="{% url 'my_module:item_create' %}">
        <ion-icon name="add-outline"></ion-icon>
        New Item
    </ion-button>
{% endif %}
```

---

## Tests

### Ubicación

```
apps/accounts/tests/
├── __init__.py
├── conftest.py              # Fixtures compartidas
├── test_models.py           # Tests de modelos
├── test_permission_service.py # Tests del servicio
├── test_decorators.py       # Tests de decorators
└── test_roles_views.py      # Tests E2E de UI
```

### Ejecutar Tests

```bash
cd hub

# Todos los tests de accounts
pytest apps/accounts/tests/ -v

# Solo modelos
pytest apps/accounts/tests/test_models.py -v

# Solo servicio
pytest apps/accounts/tests/test_permission_service.py -v

# Solo decorators
pytest apps/accounts/tests/test_decorators.py -v

# Solo UI
pytest apps/accounts/tests/test_roles_views.py -v

# Con coverage
pytest apps/accounts/tests/ --cov=apps/accounts --cov-report=html
```

### Fixtures Disponibles

```python
# conftest.py
@pytest.fixture
def hub_id():
    """UUID de hub para tests."""

@pytest.fixture
def admin_user(db, hub_id):
    """LocalUser con rol admin."""

@pytest.fixture
def employee_user(db, hub_id):
    """LocalUser con rol employee."""

@pytest.fixture
def permission_view_product(db, hub_id):
    """Permission: inventory.view_product"""

@pytest.fixture
def role_custom(db, hub_id):
    """Role personalizado no-sistema."""

@pytest.fixture
def authenticated_client(db, admin_user, configured_store, configured_hub):
    """Cliente Django con sesión de admin."""
```

---

## Migración desde Sistema Legacy

### Estado Actual

El sistema mantiene compatibilidad con el campo legacy `role` (CharField) mientras se migra a `role_obj` (FK).

```python
class LocalUser:
    # Legacy - mantener para compatibilidad
    role = models.CharField(choices=ROLE_CHOICES, default='employee')

    # Nuevo
    role_obj = models.ForeignKey(Role, null=True)
```

### get_role_name()

Este método maneja la transición:

```python
def get_role_name(self):
    if self.role_obj:
        return self.role_obj.name  # Nuevo sistema
    return self.role  # Fallback a legacy
```

---

## Troubleshooting

### "Hub not configured"

El sistema requiere `HubConfig` con `hub_id` válido:

```python
from apps.configuration.models import HubConfig
config = HubConfig.get_config()
print(config.hub_id)  # Debe ser UUID válido
```

### Permisos no aparecen

Verificar que:
1. El módulo está activo (sin `_` prefix)
2. El módulo define `PERMISSIONS` en `module.py`
3. Se ejecutó `PermissionService.sync_module_permissions()`

### Usuario admin sin acceso

El rol admin tiene bypass automático. Verificar:

```python
user = LocalUser.objects.get(email='admin@example.com')
print(user.get_role_name())  # Debe ser 'admin'
```

---

*Última actualización: 2026-01-02*
