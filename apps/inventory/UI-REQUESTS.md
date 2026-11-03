# Peticiones de UI de la app `inventory`

Lo que la app necesita de `@erplora/ui` y todavía no está. Mientras tanto usa lo registrado o una
pieza propia en `apps/inventory/frontend/components/`; se cambia en cuanto llegue. Revisado al cerrar la
app (CLOSE-INVENTORY, 2026-10-31) contra `@erplora/ui` en `673e625`: lo hecho ha salido de esta lista, lo
que ya llegó y la app aún no usa está en su apartado, y cada punto que queda va a `## 6` del registro de la
migración con su clave `inventory:ui-…`. Ninguno rompe un flujo: todos tienen su sustituto en uso.

## Ya en `@erplora/ui`, falta usarlo en la app (`inventory:ui-use-landed`)

- Iconos ya registrados en el shell (`packages/ui/src/shell/icons.ts`):
  - `ion:pricetags-outline` — pestaña **Categorías**; hoy `ion:list-outline` (`composables/useInventoryTabs.ts`).
  - `ion:close-circle-outline` — cifra **Agotados** del panel; hoy `ion:close-outline` (`pages/DashboardPage.vue`).
  - `ion:pricetag-outline` — cifra **Valor de existencias**; hoy `ion:wallet-outline`.
  - `ion:cloud-upload-outline` — botón **Importar CSV**; hoy `ion:cloud-outline` (`components/CsvButtons.vue`).
- **`formatMoney`** (`@erplora/ui/components/format`): la app sigue con su `lib/format.ts`. Ninguno de los
  dos agrupa los millares de un importe de cuatro cifras en español («1234,56 €»): eso lo lleva hub#525.

## Iconos (`inventory:ui-icons`)

Los del módulo viejo que el shell no registra (`packages/ui/src/shell/icons.ts`):

- `ion:stats-chart-outline` — pestaña **Panel**; hoy `ion:speedometer-outline` (`composables/useInventoryTabs.ts`).
- `ion:eye-outline` — acción **Detalles** de un producto; hoy `ion:information-circle-outline` (`pages/ProductsPage.vue`).
- `ion:calculator-outline` — acción **Contar stock** (fila y ficha); hoy `ion:keypad-outline`.
- `ion:remove-circle-outline` — acción **Dar de baja stock**; hoy `ion:warning-outline`.
- `ion:print-outline` — botón **Imprimir código de barras** de la ficha; hoy `ion:pricetag-outline`
  (`components/ProductDetailModal.vue`).
- `ion:trending-down-outline` — panel «Productos con menos stock» del Inicio; hoy `ion:arrow-down-outline`
  (`widgets` de `apps.py`).

## Componentes

- **`KpiCard`** (`inventory:ui-kpi-card`; el `ok-kpi`): etiqueta en versalitas con icono, valor grande, nota o
  tendencia y, con `to`, toda la tarjeta enlaza. API: `label`, `value`, `icon`, `note?`,
  `tone?: 'neutral' | 'warning' | 'danger'`, `to?`, `testid?`. Uso: las cinco cifras del Panel. Hoy
  `components/KpiTile.vue`. Lo pide también `staff`.
- **`Combo` múltiple** (`inventory:ui-combo-multiple`; la petición `SearchSelect` llegó como `Combo`, de
  selección simple, y la categoría fiscal del producto, de la categoría y del import ya lo usan:
  `components/TaxCategorySelect.vue`): un `multiple` en `Combo` con `modelValue: ComboOption[]`, las elegidas
  como chips con su botón «Quitar» y sin ofrecer de nuevo las ya elegidas. Uso: «Categorías» del producto. Hoy
  `components/ProductCategoriesField.vue` compone un `Combo` simple (con `v-model` que se vacía tras cada
  elección) y los chips a mano, como `apps/appointment/frontend/components/ServicesField.vue`.
- **`DataTable`**, lo que el `ok-data-table` viejo tenía y el puerto aún no:
  - **importar / exportar CSV** (`inventory:ui-datatable-csv`; `importable`, `exportable`; el import entrega el
    texto ya decodificado: UTF-8 con o sin BOM o Windows-1252 de Excel); hoy `components/CsvButtons.vue` en el
    hueco `toolbar`. Para leer el CSV (comillas, separador `,`/`;`, saltos de línea dentro de una celda) se
    propone **PapaParse** (`papaparse`, MIT; desde 2013, cientos de colaboradores, versiones en 2024–2025); hoy
    un lector propio mínimo con sus tests: `lib/csv.ts`;
  - **panel lateral** de alta y edición (`inventory:ui-side-panel`; el `open('create'|'edit')` viejo); hoy los
    formularios van en `FormModal`. Lo piden también `service`, `customer`, `pricing` y `task`.
- **`formatNumber`, `formatPercent`** (`inventory:ui-number-format`) en `components/format`, con
  `Intl.NumberFormat` del idioma de la página, junto al `formatMoney` que ya llegó; hoy `lib/format.ts`.
- **`useI18n`** (`inventory:ui-use-i18n`) reexportado desde `@erplora/ui/shell`: el Hub no depende de
  `vue-i18n` y los scripts leen `$t` de la instancia; hoy `composables/useT.ts`.
- **Ayudas de test** (`inventory:ui-testing-helpers`) en `@erplora/ui/testing`: el `IonModalStub` de
  FormModal y el registro de iconos (`addIcons(ION_ICONS)`), que hoy se importan por ruta relativa desde
  `packages/ui` y su `node_modules`.

La placa del código de barras (`components/BarcodePlate.vue`, con JsBarcode, INVENTORY-F25) es de la app:
pasa a `@erplora/ui/components` solo si otra app necesita un código de barras.
