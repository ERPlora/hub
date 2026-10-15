# Peticiones de UI de la app `payment`

Lo que las páginas de Pagos necesitan de `@erplora/ui` y todavía no está. Mientras tanto usan lo más
parecido que ya existe (dicho en cada punto); se cambia en cuanto llegue.

## Filtro de rango de fechas en `DataTable`

- **Qué:** el `ok-data-table` viejo filtraba la columna Fecha de Pagos por rango (`daterange`). El
  `DataTable` filtra un día (`date`) o un rango de números (`range`). Es la misma petición que
  `apps/schedule/UI-REQUESTS.md` («Filtro de rango de fechas en `DataTable`»): `filter: { type:
  'daterange' }` con `<key>_from` y `<key>_to`.
- **Hoy:** la columna Fecha filtra un día y la página manda ese día como los dos extremos
  (`payment_date_from` = `payment_date_to`). La consulta `payment.payment.list` ya acepta el rango: al
  llegar el filtro, solo cambia `frontend/pages/PaymentsPage.vue` (y su test).

## Iconos (registrarlos en `packages/ui/src/shell/icons.ts`, `ION_ICONS`)

- `ion:send-outline` — icono del módulo, de la entrada de menú y de la pestaña **Pagos** (el del producto
  actual era `send`). **Hoy:** `lucide:send`, el mismo avión de papel, ya registrado.
- `ion:arrow-forward-outline` — la acción de fila que avanza un pago (Aprobar, Marcar como enviado,
  Marcar como completado; el producto actual usaba `arrow-forward`). **Hoy:** `ion:chevron-forward-outline`.

Al registrarlos, cambiar a la vez `apps.py` (`icon` y `navigation`), `frontend/tabs.ts` y sus tests
(`tests/test_apps.py`, `frontend/tabs.test.ts`), correr `pnpm gen:app-icons`, y la acción de
`frontend/pages/PaymentsPage.vue`.

## Piezas compartidas que viven copiadas en la app

`frontend/composables/useServerTable.ts`, `useLiveList.ts`, `useT.ts`, `frontend/lib/money.ts`,
`frontend/components/MoneyInput.vue` y `PageNotices.vue` son copias de las de `apps/service` (como las
de `inventory`, `customer`, `sale`, `invoice`). Ya están pedidas en `apps/sale/UI-REQUESTS.md` e
`apps/invoice/UI-REQUESTS.md` («Tabla de servidor viva»); cuando lleguen a `@erplora/ui/components`, se
borran de aquí con sus tests.
