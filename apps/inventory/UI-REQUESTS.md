# Peticiones de UI de la app `inventory`

Lo que la app necesita de `@erplora/ui` y todavía no está. Mientras tanto usa lo registrado o una
pieza propia en `apps/inventory/frontend/components/`; se cambia en cuanto llegue.

## Iconos

Los del módulo viejo que el shell no registra (`packages/ui/src/shell/icons.ts`):

- `ion:stats-chart-outline` — pestaña **Panel**; hoy `ion:speedometer-outline` (`composables/useInventoryTabs.ts`).
- `ion:pricetags-outline` — pestaña **Categorías**; hoy `ion:list-outline`.
- `ion:eye-outline` — acción **Detalles** de un producto; hoy `ion:information-circle-outline` (`pages/ProductsPage.vue`).
- `ion:calculator-outline` — acción **Contar stock** (fila y ficha); hoy `ion:keypad-outline`.
- `ion:remove-circle-outline` — acción **Dar de baja stock**; hoy `ion:warning-outline`.
- `ion:close-circle-outline` — cifra **Agotados** del panel; hoy `ion:close-outline` (`pages/DashboardPage.vue`).
- `ion:pricetag-outline` — cifra **Valor de existencias**; hoy `ion:wallet-outline`.
- `ion:cloud-upload-outline` — botón **Importar CSV**; hoy `ion:cloud-outline` (`components/CsvButtons.vue`).

## Componentes

- **`KpiCard`** (el `ok-kpi`): etiqueta en versalitas con icono, valor grande, nota o tendencia y, con
  `to`, toda la tarjeta enlaza. API: `label`, `value`, `icon`, `note?`, `tone?: 'neutral' | 'warning' | 'danger'`,
  `to?`, `testid?`. Uso: las cinco cifras del Panel. Hoy `components/KpiTile.vue`.
- **`SearchSelect`**: selector sobre una lista paginada en el servidor (≤ 100 filas por consulta). Con la
  lista entera, un `ion-select` normal; con más, campo de solo lectura que abre `ion-modal` + `ion-searchbar`
  (búsqueda en servidor) + lista; simple o múltiple, recuerda la etiqueta de lo elegido. API: `modelValue`,
  `options`, `complete`, `fixedOptions?`, `multiple?`, `label`, `placeholder?`, `testid`, `errorText?`;
  emite `update:modelValue` y `update:search`. Uso: categoría fiscal (producto y categoría), categorías del
  producto. Hoy `components/SearchSelect.vue`.
- **`DataTable`**, lo que el `ok-data-table` viejo tenía y el puerto aún no:
  - **importar / exportar CSV** (`importable`, `exportable`; el import entrega el texto ya decodificado: UTF-8
    con o sin BOM o Windows-1252 de Excel); hoy `components/CsvButtons.vue` en el hueco `toolbar`;
  - **panel lateral** de alta y edición (el `open('create'|'edit')` viejo); hoy los formularios van en `FormModal`.
- **`formatMoney`, `formatNumber`, `formatPercent`** en `components/format` (el índice ya lo anuncia: «and,
  later, money»), con `Intl.NumberFormat` del idioma de la página; hoy `lib/format.ts`.
- **`useI18n`** reexportado desde `@erplora/ui/shell`: el Hub no depende de `vue-i18n` y los scripts leen `$t`
  de la instancia; hoy `composables/useT.ts`.
- **Ayudas de test** en `@erplora/ui/testing`: el `IonModalStub` de FormModal y el registro de iconos
  (`addIcons(ION_ICONS)`), que hoy se importan por ruta relativa desde `packages/ui` y su `node_modules`.

## Librerías

- **PapaParse** (`papaparse`, MIT; desde 2013, cientos de colaboradores, versiones en 2024–2025) para leer el
  CSV de la importación (comillas, separador `,`/`;`, saltos de línea dentro de una celda). Hoy un lector
  propio mínimo con sus tests: `lib/csv.ts`.
- Para **INVENTORY-F25** (etiqueta con código de barras, cuando exista `printing`): **JsBarcode** (MIT, desde
  2013) o **bwip-js** (MIT, desde 2011) para pintar el Code128 del SKU en SVG, en vez de portar `code128.ts`.
