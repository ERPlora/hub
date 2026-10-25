# Peticiones de UI de la app `cash_register`

Lo que las páginas de Caja necesitan de `@erplora/ui` y todavía no está. Mientras tanto usan lo más
parecido que ya existe (dicho en cada punto); se cambia en cuanto llegue.

**Al cerrar la app (2026-10-21)**, contra `ERPlora/ui` `origin/main` `83aeacc`: no ha llegado ninguna de
las cinco. Ninguna rompe un flujo (todas tienen su sustituto, dicho abajo), así que pasan a «Fuera por
ahora» (`## 6` de `MIGRATION.md`) con las claves `cash_register:ui-icons`, `cash_register:ui-money-format`,
`cash_register:ui-detail-list`, `cash_register:ui-bar-list` y `cash_register:ui-readonly-modal`. Quien
entregue una en `ui` la borra de aquí y cambia su sustituto en la misma PR del puntero.

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
- **Hoy**: `frontend/lib/money.ts` (`formatMoney`, `formatSignedMoney`, `formatFace` —un billete o moneda
  entera sin decimales, «500 €»—, `moneyFieldText`, `readMoney`, `moneyRefusal`). Ventas tiene el suyo en `apps/sale/frontend/lib/format.ts`: los dos se borran cuando
  llegue el compartido.

## Lista de detalle (`ok-detail-list`)

- **Qué**: la lista de etiqueta/valor en dos columnas del producto actual (resumen de la sesión).
- **Hoy**: `frontend/components/SessionSummary.vue` (un `<dl>` en rejilla de dos columnas).

## Lista de barras (`ok-bar-list`)

- **Qué**: la lista de barras horizontales con su etiqueta y su valor del panel «Sesiones recientes» del
  producto actual, con color por signo (falta en rojo, sobra en verde).
- **Hoy**: `frontend/components/CashFigures.vue` («Descuadres recientes»: las barras con su propio CSS, ancho
  proporcional al mayor descuadre de las ocho). El panel «Descuadres recientes» del Inicio lo pinta el
  `bar-list` de `base` (`base/frontend/components/WidgetPanel.vue`), sin color por signo: cuando llegue el
  componente, también ese.

## Ventana de solo lectura (`FormModal` sin envío)

- **Qué**: una ventana que solo enseña una lista, con un único botón para cerrarla.
- **Hoy**: `frontend/components/UnassignedModal.vue` («Cobros fuera de turno») usa `FormModal`, que pinta
  «Cancelar» y «Cerrar», los dos con el mismo efecto.
