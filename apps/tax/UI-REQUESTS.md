# Peticiones de UI de la app `tax`

Lo que las páginas de Impuestos necesitan de `@erplora/ui` y todavía no está. Mientras tanto usan lo
más parecido que ya existe (dicho en cada punto); se cambia en cuanto llegue.

**Estado al cerrar la app (CLOSE-TAX, 2026-10-22):** las dos peticiones siguen abiertas: ninguna ha llegado
a `ERPlora/ui` (`origin/main` de635ff; el puntero del Hub, 07b4392). Sus sustitutos funcionan y ningún flujo
está roto; van propuestas para `## 6` de `MIGRATION.md` como `tax:ui-live-server-table` y
`tax:ui-percent-date-format`. La primera es la misma que `cart_checkout:ui-live-server-table` y
`combo:ui-live-server-table` (las copias de casi todas las apps salen de las de Impuestos): con una
compartida se cierran todas.

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
- **Hoy**: `apps/tax/frontend/lib/format.ts` (dos decimales: «21,00 %»; la fecha, en UTC para que nunca
  se mueva un día). Otras diez apps tienen su propio `frontend/lib/format.ts`.

## Servidas por `@erplora/ui` (ya no se piden)

- Iconos `ion:pricetags-outline`, `ion:swap-horizontal-outline`, `ion:ban-outline` y
  `ion:arrow-undo-outline`: los llevan las pestañas, el menú y las acciones de Reglas.
- `Combo` (el `ok-combo` del producto actual): el País y la Categoría de las altas de regla y de alias;
  el `SearchSelect` propio se ha borrado.
- `cardTitleColumn` de `DataTable`: la tarjeta de Reglas usa el cuerpo de la tabla.
- Los filtros de columna en el embudo del `DataTable` (hub#27) y la tabla a altura completa (`fill`,
  hub#24): el `FilterPanel` propio se ha borrado; el selector Estado de Reglas sigue fuera del embudo
  (taxes#50).
