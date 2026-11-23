# Peticiones de UI de la app `online_booking`

Lo que las páginas de Reservas online necesitan de `@erplora/ui` (y de la plataforma) y todavía no está.
Mientras tanto usan lo más parecido que ya existe (dicho en cada punto); se cambia en cuanto llegue.

Ninguna rompe un flujo de esta app (todas tienen su sustituto, dicho abajo): `online_booking:ui-icons` (la pide
también Citas). Quien entregue una la borra de aquí y cambia su sustituto en la misma PR. La página pública de
reservas ya la sirve la puerta pública de `base` (`/p/<slug>/book`).

## Ya en `@erplora/ui`, sin usar todavía

- `ion:checkmark-done-outline` — acción **Completar** de la bandeja, la misma que Citas; ya registrado en
  `packages/ui/src/shell/icons.ts`. Hoy: `ion:checkmark-circle-outline`. Al usarlo, cambiar `ICONS` en
  `frontend/pages/BookingsPage.vue` y su test.
