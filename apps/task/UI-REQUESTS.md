# Peticiones de UI de la app `task`

Lo que las páginas de Tareas necesitan de `@erplora/ui` y todavía no está. Mientras tanto usan lo más
parecido que ya existe (dicho en cada punto); se cambia en cuanto llegue.

## Iconos (registrarlos en `packages/ui/src/shell/icons.ts`, `ION_ICONS`)

- `ion:checkbox-outline` — icono del módulo, de la entrada de menú y de la pestaña **Tareas**
  (`apps.py` `icon` y `navigation`, `frontend/tabs.ts`). Es el del producto actual. Hoy:
  `ion:checkmark-circle-outline`.
- `ion:folder-outline` — entrada de menú y pestaña **Proyectos**. Es el del producto actual. Hoy:
  `ion:file-tray-outline`.
- `ion:open-outline` — acciones de fila **Detalle** (Tareas) y **Abrir** (Proyectos), las del producto
  actual. Hoy: `ion:chevron-forward-outline`.
- `ion:play-circle-outline` — acción de fila **Iniciar**. Hoy: `ion:time-outline`.
- `ion:checkmark-done-outline` — acción de fila **Completar**. Hoy: `ion:checkmark-circle-outline`.

Al registrarlos, cambiar a la vez `apps.py` (`icon` y `navigation`), `frontend/tabs.ts` y sus tests
(`tests/test_apps.py`, `frontend/tabs.test.ts`), correr `pnpm gen:app-icons`, y las acciones de
`frontend/pages/TasksPage.vue` y `frontend/pages/ProjectsPage.vue`.

## Panel lateral de `DataTable`

- **Qué**: el panel lateral del `ok-data-table` del producto actual, donde se abría el alta de tarea y
  de proyecto, y la hoja de la tarea y del proyecto encima de la tabla. **Hoy**: `FormModal` para el
  alta y un `ion-modal` para cada hoja (como `service` y `staff`).

## Selector de color

- **Qué**: un campo de color (muestra y paleta) para el color del proyecto. **Hoy**: un `ion-input`
  de texto que acepta `#RRGGBB`, como el campo de texto del producto actual, con la muestra pintada
  al lado en la tabla y en la hoja.
