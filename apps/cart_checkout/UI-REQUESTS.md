# Peticiones de UI de la app `cart_checkout`

Lo que las páginas de Carrito y pago necesitan de `@erplora/ui` y todavía no está. Mientras tanto usan
lo más parecido que ya existe (dicho en cada punto); se cambia en cuanto llegue.

**Al cerrar la app (2026-10-21)**, contra `ERPlora/ui` `origin/main` `89eaf98`: no ha llegado ninguna de las tres (ni
los dos iconos en `ION_ICONS`, ni la tabla de servidor viva, ni un lector común de importes). Ninguna rompe un flujo
(todas tienen su sustituto, dicho abajo), así que pasan a «Fuera por ahora» (`## 6` de
`archive/migration/MIGRATION.md` de `ERPlora/erplora-next`) con las claves `cart_checkout:ui-icons`,
`cart_checkout:ui-live-server-table` y `cart_checkout:ui-money-reader`. Quien entregue una en `ui` la borra de aquí y
cambia su sustituto en la misma PR del puntero.

## Ya en `@erplora/ui`, sin usar todavía

- `ion:checkmark-done-outline` — la acción de fila **Completar** de Pedidos (el del producto actual), ya
  registrado en `packages/ui/src/shell/icons.ts`. **Hoy:** `ion:checkmark-circle-outline`. Al usarlo, cambiar
  a la vez la acción de `frontend/pages/OrdersPage.vue` y su test.

## Iconos (registrarlos en `packages/ui/src/shell/icons.ts`, `ION_ICONS`)

- `ion:bag-check-outline` — icono del módulo, de la entrada de menú y de la pestaña **Carritos** (el del
  producto actual). **Hoy:** `lucide:shopping-bag`, la misma bolsa sin la marca, ya registrada.

Al registrarlo, cambiar a la vez `apps.py` (`icon` y `navigation`), `frontend/tabs.ts` y sus tests
(`tests/test_apps.py`, `frontend/tabs.test.ts`), y correr `pnpm gen:app-icons`.

## Piezas compartidas que viven copiadas en la app

`frontend/composables/useServerTable.ts`, `useLiveList.ts`, `useT.ts` y `frontend/components/PageNotices.vue`
son copias de las de `apps/payment` (como las de `inventory`, `customer`, `sale`, `invoice`). Ya están
pedidas en `apps/sale/UI-REQUESTS.md` e `apps/invoice/UI-REQUESTS.md` («Tabla de servidor viva»); cuando
lleguen a `@erplora/ui/components`, se borran de aquí con sus tests.
