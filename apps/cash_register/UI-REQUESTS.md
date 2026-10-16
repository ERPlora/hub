# Peticiones de UI de la app `cash_register`

Lo que las páginas de Caja necesitan de `@erplora/ui` y todavía no está. Mientras tanto usan lo más
parecido que ya existe (dicho en cada punto); se cambia en cuanto llegue.

## Iconos

- `ion:document-text-outline` — acción de fila «Detalle» de la tabla de sesiones (el icono del producto
  actual). Hoy: `ion:list-outline`.
- `ion:calculator-outline` — acción de fila «Arqueo» y tarjeta de un arqueo (el del producto actual).
  Hoy: `ion:keypad-outline`.
- `ion:print-outline` — botón «Imprimir» del detalle de la sesión. Hoy: `ion:receipt-outline`.

Al registrarlos, cambiar `frontend/pages/SessionsPage.vue` (acciones), `frontend/components/SessionCounts.vue`
(icono de la tarjeta) y `frontend/pages/SessionDetailPage.vue` (botón).

## Dinero en `@erplora/ui/components/format`

- **Qué**: un formateador de dinero (`formatMoney(cents, locale, currency)`, con signo explícito para
  las diferencias) y un lector de importes tecleados («150,50», «1.250,50», «1.250» ambiguo) con su motivo
  de rechazo, los dos en la moneda del negocio.
- **Hoy**: `frontend/lib/money.ts` (`formatMoney`, `formatSignedMoney`, `moneyFieldText`, `readMoney`,
  `moneyRefusal`). Ventas tiene el suyo en `apps/sale/frontend/lib/format.ts`: los dos se borran cuando
  llegue el compartido.

## Lista de detalle (`ok-detail-list`)

- **Qué**: la lista de etiqueta/valor en dos columnas del producto actual (resumen de la sesión).
- **Hoy**: `frontend/components/SessionSummary.vue` (un `<dl>` en rejilla de dos columnas).
