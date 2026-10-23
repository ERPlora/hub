# Peticiones de UI de la app `task`

Lo que las páginas de Tareas necesitan de `@erplora/ui` y todavía no está. Mientras tanto usan lo más
parecido que ya existe (dicho en cada punto); se cambia en cuanto llegue.

**Estado (2026-10-23, FIX-UI-SHELL-ICONS-SERVICE-TASK)**: los iconos del producto actual ya llegaron a `ui` y
salieron de aquí: `ion:checkbox-outline` en el módulo, el menú y la pestaña **Tareas** (y en sus tarjetas y sus
listas vacías), `ion:open-outline` en **Detalle** y **Abrir**, `ion:play-circle-outline` en **Iniciar** y
`ion:checkmark-done-outline` en **Completar**; la carpeta de Proyectos (`ion:folder-outline`) también en sus
tarjetas y su lista vacía. Siguen abiertos los dos puntos de abajo, con sustituto, en «Fuera por ahora»
(`MIGRATION.md` §6) como `task:ui-datatable-side-panel` y `task:ui-color-picker`.

## Panel lateral de `DataTable`

- **Qué**: el panel lateral del `ok-data-table` del producto actual, donde se abría el alta de tarea y
  de proyecto, y la hoja de la tarea y del proyecto encima de la tabla. **Hoy**: `FormModal` para el
  alta y un `ion-modal` para cada hoja (como `service` y `staff`).

## Selector de color

- **Qué**: un campo de color (muestra y paleta) para el color del proyecto. **Hoy**: un `ion-input`
  de texto que acepta `#RRGGBB`, como el campo de texto del producto actual, con la muestra pintada
  al lado en la tabla y en la hoja.
