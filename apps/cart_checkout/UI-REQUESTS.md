# Peticiones de UI de la app `cart_checkout`

Lo que las páginas de Carrito y pago necesitan de `@erplora/ui` y todavía no está. Mientras tanto usan
lo más parecido que ya existe (dicho en cada punto); se cambia en cuanto llegue.

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

La lectura de un importe tecleado o pegado en un filtro («1.250,50», «12,50 €»; lo ambiguo, «1.250», no
se adivina) vive en `frontend/lib/format.ts` (`toMinor`, `unreadableTotals`), como la de `payment`,
`customer`, `inventory`, `sale`, `invoice` y `verifactu`, cada una con su copia (el producto actual lo
pedía en pm#501). Cuando `@erplora/ui` lleve un lector común de importes para los filtros de rango con
`amount: true`, la app lo usa y borra el suyo con sus tests.
