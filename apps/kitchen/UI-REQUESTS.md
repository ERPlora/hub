# Peticiones de UI de la app `kitchen`

Lo que las páginas de Cocina necesitan de `@erplora/ui` (y de otras apps) y todavía no está. Mientras tanto
usan lo más parecido que ya existe (dicho en cada punto); se cambia en cuanto llegue.

## Iconos (registrarlos en `packages/ui/src/shell/icons.ts`, `ION_ICONS`)

- `ion:restaurant-outline` — icono del módulo en la página de apps y en la tienda (`apps.py` `icon`), el
  del bloque de ajustes del módulo viejo. Hoy: `ion:ticket-outline`.
- `ion:tv-outline` — entrada de menú y pestaña **Pantalla**. Hoy: `ion:desktop-outline`.
- `ion:clipboard-outline` — entrada de menú y pestaña **Comandas**. Hoy: `ion:list-outline`.
- `ion:flame-outline` — entrada de menú y pestaña **Estaciones**, y la acción «Lanzar» de la lista de
  Comandas. Hoy: `ion:layers-outline` y `ion:chevron-forward-outline`.
- `ion:expand-outline` / `ion:contract-outline` — botón «Pantalla completa» / «Salir de pantalla
  completa» de la Pantalla. Hoy: `ion:chevron-expand-outline` en los dos estados (el texto cambia).
- `ion:print-outline` — el plato «Solo papel» de la tarjeta y la acción «Reimprimir». Hoy:
  `ion:receipt-outline`.

Al registrarlos, cambiar a la vez `apps.py` (`icon` y `navigation`), `frontend/tabs.ts` y sus tests
(`tests/test_apps.py`, `frontend/tabs.test.ts`) y correr `pnpm gen:app-icons`.

## Componentes y composables

- `useServerTable`, `useLiveList`, `useT`/`useLocale` y `useNow` son copias de los de Mesas (que a su vez
  copió Impuestos): deberían vivir una sola vez en `@erplora/ui/sdk` o `@erplora/ui/components`. Hasta
  entonces, cada app lleva la suya con sus tests.
- Un selector de color con paleta (`ColorPicker`): el formulario de estación usa un `ion-select` con la
  paleta del módulo viejo y conserva un color propio que viniera de la API.

## De otras apps

- **Ventas**: la pestaña «Comanda actual» con «Enviar comanda» y la llama de urgencia
  (`kitchen.ticket.send`) y la hoja «Comandas de la cuenta» (`kitchen.ticket.by_order`,
  `kitchen.ticket.set_rush`); ver «Lo que pide a otras apps» del `WORKBOOK.md`.
