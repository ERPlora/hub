# Peticiones de UI de la app `invoice`

Lo que las páginas de Facturación necesitan de `@erplora/ui` y todavía no está. Mientras tanto usan lo
más parecido que ya existe (dicho en cada punto); se cambia en cuanto llegue.

## Iconos

- `ion:document-text-outline` — icono del módulo y pestaña/menú **Facturas** (el del producto actual).
  Hoy: `ion:receipt-outline` (`apps.py` `icon` y `navigation`, `frontend/tabs.ts`).
- `ion:bookmark-outline` — pestaña y menú **Series** (el del producto actual). Hoy: `ion:layers-outline`.
- `ion:business-outline` — pestaña y menú **Emisor** (nuevo). Hoy: `ion:storefront-outline`.
- `ion:print-outline` — botón «Imprimir / PDF» de la ficha (el del producto actual). Hoy:
  `ion:download-outline`.

Al registrarlos, cambiar a la vez `apps.py` (`icon` y `navigation`), `frontend/tabs.ts`, sus tests
(`tests/test_apps.py`, `frontend/tabs.test.ts`) y `pnpm gen:app-icons`.

## Formateadores de dinero, porcentaje, cantidad y día en `@erplora/ui/components/format`

- **Qué**: `formatMoney(cents, locale)`, `formatPercent(rate, locale)`, `formatQuantity(value, locale)` y
  `formatDate('YYYY-MM-DD', locale)` (un día de calendario, sin moverlo de zona).
- **Hoy**: `frontend/lib/format.ts` (copia del de Ventas, más `formatDate`). Se borra cuando lleguen.

## Motor de listas vivas por ventanas y tabla de servidor

- **Qué**: `useLiveWindows` y `useServerTable` (ventanas de hasta 100 filas, cada una su suscripción;
  búsqueda, orden, páginas y filtros propios), hoy copiados en cada app.
- **Hoy**: `frontend/composables/useLiveWindows.ts` y `useServerTable.ts`, copias de los de Ventas.

## Imprimir un papel por el navegador

- **Qué**: `printPaper(element)` (copia del papel en un contenedor del `body`, `window.print()`, se quita en
  `afterprint`) en `@erplora/ui`, para no depender de Ventas.
- **Hoy**: la ficha importa `apps/sale/frontend/lib/print.ts` (Ventas es requisito de Facturación).

## Filtros por columna en `DataTable`

- **Qué**: lo mismo que pide `apps/tax/UI-REQUESTS.md` (cajón de filtros del `ok-data-table`).
- **Hoy**: `frontend/components/InvoiceFilters.vue` en el slot `filters` (Estado, Tipo, Serie, Origen,
  fechas y total). Se borra cuando el `DataTable` lo traiga.
