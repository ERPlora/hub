# Peticiones de UI de la app `cart_checkout`

Lo que las páginas de Carrito y pago necesitan de `@erplora/ui` y todavía no está. Mientras tanto usan
lo más parecido que ya existe (dicho en cada punto); se cambia en cuanto llegue.

**Al cerrar la app (2026-10-21)**, contra `ERPlora/ui` `origin/main` `89eaf98`: no ha llegado ninguna de
las tres (ni los dos iconos en `ION_ICONS`, ni la tabla de servidor viva, ni un lector común de importes).
Ninguna rompe un flujo (todas tienen su sustituto, dicho abajo), así que pasan a «Fuera por ahora» (`## 6`
de `MIGRATION.md`) con las claves `cart_checkout:ui-icons`, `cart_checkout:ui-live-server-table` y
`cart_checkout:ui-money-reader`. Quien entregue una en `ui` la borra de aquí y cambia su sustituto en la
misma PR del puntero.

## Iconos (registrarlos en `packages/ui/src/shell/icons.ts`, `ION_ICONS`)

- `ion:bag-check-outline` — icono del módulo, de la entrada de menú y de la pestaña **Carritos** (el del
  producto actual). **Hoy:** `lucide:shopping-bag`, la misma bolsa sin la marca, ya registrada.
- `ion:checkmark-done-outline` — la acción de fila **Completar** de Pedidos (el del producto actual).
  **Hoy:** `ion:checkmark-circle-outline`.

Al registrarlos, cambiar a la vez `apps.py` (`icon` y `navigation`), `frontend/tabs.ts` y sus tests
(`tests/test_apps.py`, `frontend/tabs.test.ts`), la acción de `frontend/pages/OrdersPage.vue`, y correr
`pnpm gen:app-icons`.

## Piezas compartidas que viven copiadas en la app

`frontend/composables/useServerTable.ts`, `useLiveList.ts`, `useT.ts` y `frontend/components/PageNotices.vue`
son copias de las de `apps/payment` (como las de `inventory`, `customer`, `sale`, `invoice`). Ya están
pedidas en `apps/sale/UI-REQUESTS.md` e `apps/invoice/UI-REQUESTS.md` («Tabla de servidor viva»); cuando
lleguen a `@erplora/ui/components`, se borran de aquí con sus tests.

La lectura de un importe tecleado o pegado en un filtro, en la moneda del negocio («1.250,50», «12,50 zł»,
«PLN 12,50»; lo ambiguo, «1.250», no se adivina, ni el símbolo de otra moneda) vive en `frontend/lib/format.ts` (`toMinor`, `unreadableTotals`), como la de `payment`,
`customer`, `inventory`, `sale`, `invoice` y `verifactu`, cada una con su copia (el producto actual lo
pedía en pm#501). Cuando `@erplora/ui` lleve un lector común de importes para los filtros de rango con
`amount: true`, la app lo usa y borra el suyo con sus tests.
