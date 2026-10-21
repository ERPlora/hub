# Peticiones de UI de la app `service`

Lo que las páginas de Servicios necesitan de `@erplora/ui` y todavía no está. Mientras tanto usan lo
más parecido que ya existe (dicho en cada punto); se cambia en cuanto llegue.

**Al cerrar la app (2026-10-21)**, contra `ERPlora/ui` `origin/main` `f62af6b`: no ha llegado ninguno de los
cuatro iconos ni el panel lateral. Ninguno rompe un flujo (todos tienen su sustituto, dicho abajo). Los iconos
ya están en la cola como `FIX-UI-SHELL-ICONS-SERVICE-TASK` (`TODO.md`, junto con los de Tareas); el panel
lateral pasa a «Fuera por ahora» (`## 6` de `MIGRATION.md`), como lo piden también Inventario, Clientes,
Tarifas y Tareas. Quien los registre en `ui` los borra de aquí y cambia el sustituto en la misma PR del
puntero.

## Iconos (registrarlos en `packages/ui/src/shell/icons.ts`, `ION_ICONS`)

- `ion:briefcase-outline` — icono del módulo, de la entrada de menú y de la pestaña **Servicios**
  (`apps.py` `icon` y `navigation`, `frontend/tabs.ts`). Es el del producto actual (`briefcase`).
  Hoy: `ion:pricetag-outline`.
- `ion:gift-outline` — entrada de menú y pestaña **Bonos y paquetes**. Es el del producto actual
  (`gift`). Hoy: `ion:ticket-outline`.
- `ion:archive-outline` — acción de fila **Archivar** de Servicios (la del producto actual). Hoy:
  `ion:file-tray-outline`.
- `ion:star` / `ion:star-outline` — la estrella de «Servicio principal» en «Profesionales que lo
  hacen» (la del producto actual). Hoy: una etiqueta «Servicio principal» y el botón «Hacerlo su
  servicio principal».

Al registrarlos, cambiar a la vez `apps.py` (`icon` y `navigation`), `frontend/tabs.ts` y sus tests
(`tests/test_apps.py`, `frontend/tabs.test.ts`), correr `pnpm gen:app-icons`, y las acciones de
`frontend/pages/ServicesPage.vue`.

## Panel lateral de `DataTable`

- **Qué**: el panel lateral del `ok-data-table` del producto actual, donde se abrían «Nuevo servicio»,
  «Editando servicio — …», la categoría y el bono. **Hoy**: un `FormModal` (como `inventory` y `staff`).

## Hechas

- Los filtros por columna de Servicios y de Bonos y paquetes van tras el botón «Filtros» del `DataTable`
  (`filterable`), como en el producto actual, y en su panel cada rango dice su columna (hub#107).
