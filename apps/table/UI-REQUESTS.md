# Peticiones de UI de la app `table`

Lo que las páginas de Mesas necesitan de `@erplora/ui` (y de otras apps) y todavía no está. Mientras tanto
usan lo más parecido que ya existe (dicho en cada punto); se cambia en cuanto llegue.

## Iconos (registrarlos en `packages/ui/src/shell/icons.ts`, `ION_ICONS`)

- `ion:restaurant-outline` — icono del módulo en la página de apps y en la tienda (`apps.py` `icon`). Hoy:
  `ion:grid-outline`, el del bloque de ajustes del módulo viejo.
- `ion:map-outline` — entrada de menú y pestaña **Plano de sala** (la del producto actual). Hoy:
  `ion:apps-outline`.

Al registrarlos, cambiar a la vez `apps.py` (`icon` y `navigation`), `frontend/tabs.ts` y sus tests
(`tests/test_apps.py`, `frontend/tabs.test.ts`) y correr `pnpm gen:app-icons`.

## Hechas

- Ventas abre una cuenta por la dirección (`/sale/pos?order=<id>`) y monta «Elegir mesa» en la cabecera
  de la cuenta (SALE-F19): ver TABLE-F11, F12, F13 y F24 en el `WORKBOOK.md`.
