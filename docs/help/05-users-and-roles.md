# Usuarios y Roles

ERPlora usa un sistema de usuarios locales con autenticación por PIN y roles con permisos granulares.

## Usuarios

Cada persona que usa el Hub tiene un **usuario local** con:
- Nombre y apellidos
- PIN numérico (para acceso rápido)
- Rol asignado
- Idioma preferido
- Avatar (opcional)

### Crear un usuario

1. Ve a **Empleados** en la barra lateral
2. Pulsa **"Nuevo Empleado"**
3. Rellena nombre, apellidos y PIN
4. Asigna un rol
5. Guarda

### Autenticación por PIN

El sistema usa PINs numéricos para acceso rápido, ideal para entornos de punto de venta donde la velocidad es importante.

- El PIN debe ser único por usuario
- Se recomienda un mínimo de 4 dígitos
- Para más seguridad, usar 6 o más dígitos

## Roles

Los roles definen qué puede hacer cada usuario. Hay tres tipos:

### Roles Básicos (predefinidos)

| Rol | Descripción |
|-----|-------------|
| **Administrador** | Acceso total al sistema |
| **Gerente** | Acceso a gestión, informes y configuración |
| **Empleado** | Acceso a operaciones diarias (ventas, caja) |
| **Visor** | Solo lectura, sin modificar datos |

### Roles de Solución (del blueprint)

Se crean automáticamente según tu tipo de negocio. Por ejemplo, un restaurante tendrá roles como "Camarero", "Cocinero", "Maitre".

### Roles Personalizados

Puedes crear roles a medida:

1. Ve a **Roles** en la barra lateral
2. Pulsa **"Nuevo Rol"**
3. Asigna un nombre
4. Selecciona los permisos que quieras otorgar
5. Guarda

### Permisos

Los permisos controlan el acceso a cada funcionalidad:

- `inventory.view_product` — Ver productos
- `inventory.change_product` — Editar productos
- `inventory.delete_product` — Eliminar productos
- `sales.*` — Todos los permisos de ventas

Los permisos se agrupan por módulo, facilitando la asignación.
