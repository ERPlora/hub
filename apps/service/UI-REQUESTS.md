# Peticiones de UI de la app `service`

Lo que las páginas de Servicios necesitan de `@erplora/ui` y todavía no está. Mientras tanto usan lo
más parecido que ya existe (dicho en cada punto); se cambia en cuanto llegue.

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

## Filtros de rango de `DataTable` con su columna a la vista

- **Qué**: con dos columnas de rango (Precio y Duración en Servicios) los cuatro campos dicen solo
  «Desde» y «Hasta»; la columna está en su `aria-label`, no a la vista. **Propuesta**: el marcador
  «Precio desde» / «Precio hasta» (o la columna encima del par). **Hoy**: el `aria-label` lo dice.
