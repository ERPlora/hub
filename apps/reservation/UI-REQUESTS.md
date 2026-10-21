# Peticiones de UI de la app `reservation`

Lo que las páginas de Reservas necesitan de `@erplora/ui` (y de otras apps) y todavía no está. Mientras
tanto usan lo más parecido que ya existe (dicho en cada punto); se cambia en cuanto llegue.

## Iconos (registrarlos en `packages/ui/src/shell/icons.ts`)

- `material-symbols:table-restaurant-outline` (o `ion:restaurant-outline`) — icono del módulo en la
  página de apps y en la tienda (`apps.py` `icon`): hoy `ion:calendar-outline`, el mismo que Citas, que
  confunde en la rejilla de apps. Es el primer icono de menú del módulo viejo.
- `ion:restaurant-outline` — acción «Sentar» de cada reserva (el icono del módulo viejo). Hoy:
  `ion:people-outline`.
- `ion:checkmark-done-outline` — acción «Completar» (la del módulo viejo). Hoy:
  `ion:checkmark-circle-outline`.
- `ion:call-outline` — acción «Contactado» de la lista de espera (la del módulo viejo). Hoy:
  `ion:chatbubbles-outline`.

Al registrarlos, cambiar a la vez `apps.py` (`icon`), `frontend/tabs.ts`, las acciones de
`frontend/pages/ReservationsPage.vue` y `WaitlistPage.vue` y sus tests (`tests/test_apps.py`,
`frontend/tabs.test.ts`) y correr `pnpm gen:app-icons`.

## De Mesas

- Que `table.hold.sync_reservation` trate `seated` y `completed` como gastar la retención (hoy no hace
  nada con ellos): Reservas suelta con `table.hold.release` la retención que no entró en su ventana al
  sentar, y la marca queda «soltada» en vez de «gastada».
- Mesas unidas para un grupo grande (su duda 3): una reserva tiene hoy una sola mesa, porque la retención
  es una por reserva (`(source, source_ref)` única).
