# Peticiones de UI de la app `combo`

Lo que las páginas de Menús necesitan de `@erplora/ui` y todavía no está. Mientras tanto usan lo más
parecido que ya existe (dicho en cada punto); se cambia en cuanto llegue.

**Al cerrar la app (2026-10-21)**, contra `ERPlora/ui` `origin/main` `f62af6b`: no ha llegado nada de lo de abajo.
Ninguno rompe un flujo (todos tienen su sustituto), así que pasan a «Fuera por ahora» (`## 6` de `MIGRATION.md`) con
las claves `combo:ui-icons`, `combo:ui-money-reader` y `combo:ui-live-server-table`. Quien los suba a `ui` los borra
de aquí y cambia el sustituto en la misma PR del puntero.

## Iconos (registrarlos en `packages/ui/src/shell/icons.ts`, `ION_ICONS`)

- `ion:restaurant-outline` — icono del módulo y de la entrada de menú **Menús** (`apps.py`: `icon` y
  `navigation`), y de las tarjetas y el vacío de la lista. Es el del producto actual. Hoy:
  `ion:layers-outline`. Al registrarlo, cambiar a la vez `apps.py`, `tests/test_apps.py`,
  `frontend/pages/MenusPage.vue` y volver a correr `pnpm gen:app-icons`.
- `ion:arrow-up-outline` — «Subir» de un plato y de una elección (el del producto actual; `arrow-down-outline`
  sí está). Hoy: `ion:chevron-up-outline` y, para que suban y bajen igual, `ion:chevron-down-outline`.

## Componentes compartidos

- **Lector de importes** (`lib/money.ts` + `components/MoneyInput.vue`): es el mismo de Servicios e
  Inventario con el signo opcional (`signed`) que necesita el suplemento. Cada app lleva hoy su copia
  porque una app no importa el código de otra; debería vivir en `@erplora/ui/components` como
  `MoneyInput` con la prop `signed`. Al llegar, se borran las copias.
- **`useLiveList` / `useServerTable` / `useT`**: copias de las de Impuestos, como en el resto de apps;
  mismo destino (`@erplora/ui/sdk`).
- **Nombre de un buscador suelto** (`useSearchbarName`, la misma petición que `sale`): Ionic 8 anuncia el campo de
  todo `ion-searchbar` como «search text», en inglés. Hoy el buscador de «Añadir varios»
  (`components/BulkAddModal.vue`) llama a `syncSearchbarInputName` de `@erplora/ui/components` con su propio
  `watch` (al abrirse la ventana y al cambiar el idioma); al llegar el composable, se cambia por él.

## Cerradas

- `ion:reorder-three-outline` (el asa de arrastre): no hace falta registrarlo; lo pinta el propio `ion-reorder`
  con su icono interno, y el constructor no usa el asa fuera de un `ion-reorder-group`.
