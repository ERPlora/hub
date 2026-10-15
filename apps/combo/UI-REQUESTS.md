# Peticiones de UI de la app `combo`

Lo que las páginas de Menús necesitan de `@erplora/ui` y todavía no está. Mientras tanto usan lo más
parecido que ya existe (dicho en cada punto); se cambia en cuanto llegue.

## Iconos

- `ion:restaurant-outline` — icono del módulo y de la entrada de menú **Menús** (`apps.py`: `icon` y
  `navigation`), y de las tarjetas y el vacío de la lista. Es el del producto actual. Hoy:
  `ion:layers-outline`. Al registrarlo, cambiar a la vez `apps.py`, `tests/test_apps.py`,
  `frontend/pages/MenusPage.vue` y volver a correr `pnpm gen:app-icons`.
- `ion:arrow-up-outline` — «Subir» de un plato y de una elección (el del producto actual; `arrow-down-outline`
  sí está). Hoy: `ion:chevron-up-outline` y, para que suban y bajen igual, `ion:chevron-down-outline`.
- `ion:reorder-three-outline` — el asa de arrastre. Hoy lo pinta el propio `ion-reorder` con su icono
  interno, así que no hace falta registrarlo salvo que se quiera el asa fuera de un `ion-reorder-group`.

## Componentes compartidos

- **Lector de importes** (`lib/money.ts` + `components/MoneyInput.vue`): es el mismo de Servicios e
  Inventario con el signo opcional (`signed`) que necesita el suplemento. Cada app lleva hoy su copia
  porque una app no importa el código de otra; debería vivir en `@erplora/ui/components` como
  `MoneyInput` con la prop `signed`. Al llegar, se borran las copias.
- **`useLiveList` / `useServerTable` / `useT`**: copias de las de Impuestos, como en el resto de apps;
  mismo destino (`@erplora/ui/sdk`).
