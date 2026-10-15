# Peticiones de UI de la app `pricing`

Lo que las páginas de Tarifas necesitan de `@erplora/ui` y todavía no está. Mientras tanto usan lo más
parecido que ya existe (dicho en cada punto); se cambia en cuanto llegue.

## Iconos (registrarlos en `packages/ui/src/shell/icons.ts`, `ION_ICONS`)

- `ion:pricetag` — icono del módulo y de la entrada de menú **Tarifas** (`apps.py` `icon` y
  `navigation`). Es el del producto actual. Hoy: `ion:pricetags-outline`.

Al registrarlo, cambiar a la vez `apps.py` (`icon` y `navigation`) y sus tests (`tests/test_apps.py`,
`frontend/routes.test.ts`) y correr `pnpm gen:app-icons`.

## Panel lateral de `DataTable`

- **Qué**: el panel lateral del `ok-data-table` del producto actual, donde se abría el alta de la tarifa.
  **Hoy**: `FormModal` para el alta y la edición de tarifas, precios y reglas (como `service` y `task`).
