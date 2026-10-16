# Peticiones de UI de la app `tax`

Lo que las páginas de Impuestos necesitan de `@erplora/ui` y todavía no está. Mientras tanto usan lo
más parecido que ya existe (dicho en cada punto); se cambia en cuanto llegue.

## `useServerTable` y `useLiveList` en el SDK (`@erplora/ui/sdk`)

- **Qué**: el estado de una lista del servidor (búsqueda ≤ 120, orden, página, tamaño, «Cargar más») y su
  seguimiento en vivo en **ventanas de 100 filas como máximo** (el servidor rechaza un `limit` mayor con
  un 422), cada una una suscripción, fusionadas en una página para el `DataTable`.
- **Por qué compartido**: el patrón de la lista de demo ya está copiado en `inventory` y `staff`, y la
  copia de demo pide `limit: pageSize * windowPages` (más de 100 tras varios «Cargar más»).
- **API (la de `apps/tax/frontend/composables/`)**: `useServerTable({ sort, dir?, pageSize? })` →
  `{ search, page, pageSize, sort, dir, filtered, query, windows, params, goToPage, setPageSize, setSort,
  loadMore, restart, followResult }`; `useLiveList(op, query, windows)` → `{ data, status, error,
  refresh }`.

## Formateadores de porcentaje y de fecha

- **Qué**: `formatPercent(valor, idioma)` («21,00 %», «21.00%») y `formatDate('YYYY-MM-DD', idioma)`
  («1 sept 2012», «Sep 1, 2012»; un día de calendario, sin zona horaria) en
  `@erplora/ui/components/format`, junto a `formatDateTime`.
- **Hoy**: `apps/tax/frontend/lib/format.ts`.

## Servidas por `@erplora/ui` (ya no se piden)

- Iconos `ion:pricetags-outline`, `ion:swap-horizontal-outline`, `ion:ban-outline` y
  `ion:arrow-undo-outline`: los llevan las pestañas, el menú y las acciones de Reglas.
- `Combo` (el `ok-combo` del producto actual): el País y la Categoría de las altas de regla y de alias;
  el `SearchSelect` propio se ha borrado.
- `cardTitleColumn` de `DataTable`: la tarjeta de Reglas usa el cuerpo de la tabla.
