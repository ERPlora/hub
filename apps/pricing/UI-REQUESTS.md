# Peticiones de UI de la app `pricing`

Lo que las páginas de Tarifas necesitan de `@erplora/ui` y todavía no está. Mientras tanto usan lo más
parecido que ya existe (dicho en cada punto); se cambia en cuanto llegue.

**Estado (2026-10-23, FIX-UI-SHELL-ICONS-SERVICE-TASK)**: el icono del producto actual, `ion:pricetag`, ya llegó
a `ui` y salió de aquí (módulo y entrada de menú **Tarifas**, y, como en Servicios y Tareas, las tarjetas y las listas
vacías de Tarifas). Sigue abierto el panel lateral, con sustituto y
sin ningún flujo roto, en «Fuera por ahora» (`MIGRATION.md` §6) como `pricing:ui-datatable-side-panel`.

## Panel lateral de `DataTable`

- **Qué**: el panel lateral del `ok-data-table` del producto actual, donde se abría el alta de la tarifa.
  **Hoy**: `FormModal` para el alta y la edición de tarifas, precios y reglas (como `service` y `task`).
