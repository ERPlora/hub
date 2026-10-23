# Peticiones de UI de la app `payment`

Lo que las páginas de Pagos necesitan de `@erplora/ui` y todavía no está. Mientras tanto usan lo más
parecido que ya existe (dicho en cada punto); se cambia en cuanto llegue.

**Al cerrar la app** (CLOSE-PAYMENT, 2026-10-23): nada de esto ha llegado a `ERPlora/ui` (`origin/main`
53db78c); todo tiene sustituto en uso y ningún flujo está roto. Queda propuesto para `## 6` de
`MIGRATION.md` como `payment:ui-icons`, `payment:ui-live-server-table` y `payment:ui-money-reader`.

## Iconos (registrarlos en `packages/ui/src/shell/icons.ts`, `ION_ICONS`)

- `ion:send-outline` — icono del módulo, de la entrada de menú y de la pestaña **Pagos** (el del producto
  actual era `send`). **Hoy:** `lucide:send`, el mismo avión de papel, ya registrado.
- `ion:arrow-forward-outline` — la acción de fila que avanza un pago (Aprobar, Marcar como enviado,
  Marcar como completado; el producto actual usaba `arrow-forward`). **Hoy:** `ion:chevron-forward-outline`.

Al registrarlos, cambiar a la vez `apps.py` (`icon` y `navigation`), `frontend/tabs.ts` y sus tests
(`tests/test_apps.py`, `frontend/tabs.test.ts`), correr `pnpm gen:app-icons`, y la acción de
`frontend/pages/PaymentsPage.vue`.

## Piezas compartidas que viven copiadas en la app

- **Tabla de servidor viva**: `frontend/composables/useServerTable.ts`, `useLiveList.ts`, `useT.ts` y
  `frontend/components/PageNotices.vue`, copias de las de `apps/service` (como las de `inventory`,
  `customer`, `sale`, `invoice`). Ya están pedidas en `apps/sale/UI-REQUESTS.md` e
  `apps/invoice/UI-REQUESTS.md` («Tabla de servidor viva»; en el registro, `cart_checkout:`, `combo:`,
  `tax:` y `kitchen:ui-live-server-table`).
- **Dinero**: `frontend/lib/money.ts` (leer lo que se teclea, sin adivinar un «1.250») y
  `frontend/components/MoneyInput.vue`. Es la misma pieza que piden `cash_register:ui-money-format`,
  `cart_checkout:ui-money-reader` y `combo:ui-money-reader`.

Cuando lleguen a `@erplora/ui`, se borran de aquí con sus tests.
