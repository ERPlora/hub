# Peticiones de UI de la app `tax`

Lo que las páginas de Impuestos necesitan de `@erplora/ui` y todavía no está. Mientras tanto usan lo
más parecido que ya existe (dicho en cada punto); se cambia en cuanto llegue.

## Iconos

- `ion:pricetags-outline` — pestaña y entrada de menú **Categorías** (`frontend/tabs.ts`, `apps.py`).
  Es el icono del producto actual (`pricetags`; `customer` pide `ion:pricetags` para sus Etiquetas).
  Hoy: `ion:list-outline`.
- `ion:swap-horizontal-outline` — pestaña y entrada de menú **Alias**. Hoy: `ion:swap-vertical-outline`.
- `ion:ban-outline` — acción de fila «Desactivar» de Reglas (el icono del producto actual). Hoy:
  `ion:close-outline`.
- `ion:arrow-undo-outline` — acción de fila «Reactivar» de Reglas. Hoy: `ion:refresh-outline`.

Al registrarlos, cambiar a la vez `frontend/tabs.ts`, `apps.py` (`navigation`) y su test
(`tests/test_apps.py`), y las acciones de `frontend/pages/RulesPage.vue`; `tabs.test.ts` exige que
menú y pestañas lleven el mismo icono.

## Filtros por columna en `DataTable`

- **Qué**: el cajón de filtros de `ok-data-table` (columnas `filterable` con `filterType`
  `text` | `select` | `range`, evento `filterChange`, botón con embudo y contador). El port de
  `DataTable` lo dejó fuera («column filters … not ported», `DataTable.lit-parity.test.ts`).
- **API propuesta**: en `DataTableColumn`, `filter?: { kind: 'text' } | { kind: 'select'; options } |
  { kind: 'range'; keys: [from, to] }`; `v-model:filters` (`Record<string, string>`); hooks
  `<testid>-filters`, `-filters-count`, `-filter-<key>`.
- **Uso**: Categorías (Clave, Nombre, Descripción, Origen), Reglas (País, Región, Categoría, Tipo,
  Calificación, Régimen, % desde–hasta), Alias (Alias, Categoría, Origen).
- **Hoy**: `frontend/components/FilterPanel.vue` en el slot `filters` (botón «Filtros» con contador que
  abre un `FormModal` con un control por filtro). Se borra cuando el `DataTable` lo traiga.

## `SearchSelect`: un selector con buscador (modal + barra de búsqueda + lista)

- **Qué**: el `ok-combo` del producto actual, con el patrón que Ionic recomienda para listas largas (un
  `ion-select` no busca): un campo de solo lectura que abre un `ion-modal` con `ion-searchbar` y la
  lista. Filtra en el cliente o, con `v-model:query`, pide al servidor lo que se escribe.
- **API (la de `apps/tax/frontend/components/SearchSelect.vue`)**: `v-model` (valor), `v-model:query`
  (opcional: búsqueda en el servidor), `options: { value, label }[]`, `label`, `placeholder`,
  `anyLabel` (un «Cualquiera» al principio, para filtros), `errorText`, `disabled`, `loading`, `testid`
  (`<testid>`, `-modal`, `-search`, `-option` con `data-value`, `-empty`). Conserva el nombre de la opción
  elegida aunque la siguiente respuesta ya no la traiga.
- **Uso**: el País (249) y la Categoría (búsqueda en el servidor) de las altas de regla y de alias, y el
  filtro Categoría de Reglas y Alias.
- **Hoy**: vive en `apps/tax/frontend/components/SearchSelect.vue`. Al pasar a `@erplora/ui` se borra de
  aquí.

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

## Cuerpo de tarjeta sin la columna del título

- **Qué**: que el cuerpo por defecto de la tarjeta de `DataTable` pueda omitir la columna que el título
  ya nombra aunque su texto no coincida (en Reglas el título es el nombre de la categoría y la columna,
  su clave). Propuesta: `cardTitleColumn?: string` (la clave de esa columna).
- **Hoy**: `RulesPage.vue` pinta su propio cuerpo en el slot `card`, con las mismas medidas que el de la
  tabla (`.tax-rule-card__*`) y respetando las columnas ocultas en el selector de columnas.
