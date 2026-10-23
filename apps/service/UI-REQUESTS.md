# Peticiones de UI de la app `service`

Lo que las páginas de Servicios necesitan de `@erplora/ui` y todavía no está. Mientras tanto usan lo
más parecido que ya existe (dicho en cada punto); se cambia en cuanto llegue.

**Estado (2026-10-23, FIX-UI-SHELL-ICONS-SERVICE-TASK)**: los iconos ya llegaron a `ui` y salieron de aquí
(«Hechas»). Sigue abierto el panel lateral, en «Fuera por ahora» (`## 6` de `MIGRATION.md`), como lo piden
también Inventario, Clientes, Tarifas y Tareas.

## Panel lateral de `DataTable`

- **Qué**: el panel lateral del `ok-data-table` del producto actual, donde se abrían «Nuevo servicio»,
  «Editando servicio — …», la categoría y el bono. **Hoy**: un `FormModal` (como `inventory` y `staff`).

## Hechas

- Los filtros por columna de Servicios y de Bonos y paquetes van tras el botón «Filtros» del `DataTable`
  (`filterable`), como en el producto actual, y en su panel cada rango dice su columna (hub#107).
- Los iconos del producto actual, registrados en `ION_ICONS` (FIX-UI-SHELL-ICONS-SERVICE-TASK):
  `ion:briefcase-outline` en el módulo, el menú y la pestaña **Servicios** (y en sus tarjetas y su lista
  vacía), `ion:gift-outline` en **Bonos y paquetes**, `ion:archive-outline` en **Archivar** y la estrella de
  «Servicio principal» en «Profesionales que lo hacen» (`ion:star` el suyo, `ion:star-outline` el botón que
  lo hace su servicio principal), como la ficha de Personal del producto actual.
