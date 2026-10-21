# Peticiones de UI de la app `flow`

Lo que las páginas de Automatizaciones necesitan de `@erplora/ui` y todavía no está. Mientras tanto
usan lo más parecido que ya existe (dicho en cada punto); se cambia en cuanto llegue.

## Iconos (registrarlos en `packages/ui/src/shell/icons.ts`, `ION_ICONS`)

- `ion:git-branch-outline` — icono del módulo y de la entrada de menú **Automatizaciones** (`apps.py`
  `icon` y `navigation`). Es el del producto actual (`git-branch`). Hoy: `ion:sync-outline`.
- `ion:happy-outline` — tarjeta «Dar la bienvenida a un cliente nuevo» de la galería. Hoy:
  `ion:person-add-outline`.
- `ion:stats-chart-outline` — tarjeta «Repasar la semana el viernes». Hoy: `ion:speedometer-outline`.
- `ion:call-outline` — tarjeta «Llamar a quien no vino». Hoy: `ion:notifications-outline`.
- `ion:chatbubble-ellipses-outline` — tarjeta «Contestar los WhatsApp», cuando vuelva. Hoy no sale.
- `ion:reorder-three-outline` — asa para arrastrar un paso. Hoy: el carácter `⠿` dentro de
  `ion-reorder`, como en el producto actual.
- `ion:play-outline` y `ion:pause-outline` — botones **Encenderla** y **Ponerla en pausa** de las tarjetas de
  **Viene con …** (FLOW-F33, F34). Hoy: sin icono, solo el texto.

Al registrarlos, cambiar a la vez `apps.py` (`icon` y `navigation`) y sus tests
(`tests/test_apps.py`), correr `pnpm gen:app-icons`, y `frontend/lib/templates.ts`.
