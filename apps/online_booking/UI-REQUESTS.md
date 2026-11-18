# Peticiones de UI de la app `online_booking`

Lo que las páginas de Reservas online necesitan de `@erplora/ui` (y de la plataforma) y todavía no está.
Mientras tanto usan lo más parecido que ya existe (dicho en cada punto); se cambia en cuanto llegue.

Ninguna rompe un flujo de esta app (todas tienen su sustituto, dicho abajo): `online_booking:ui-date-field` y
`online_booking:ui-icons` (las dos las pide también Citas). Quien entregue una la borra de aquí y cambia su sustituto
en la misma PR. La página pública de reservas ya la sirve la puerta pública de `base` (`/p/<slug>/book`).

## `DateField` en `@erplora/ui/components` (el día en el idioma del hub)

- **Qué**: el mismo campo de fecha que pide Citas (`apps/appointment/UI-REQUESTS.md`): pintado en el idioma
  del hub con su selector de un mes, en vez del `input` nativo, que pinta el idioma del dispositivo.
- **Hoy**: `ion-input type="date"` en el día de la vista previa (`ob-preview-day`) y el filtro «Fecha» de la
  bandeja (el de la `DataTable`). El valor que viaja es el mismo (`AAAA-MM-DD`).
- Al llegar: cambiar esos campos conservando sus `data-testid`.

## Ya en `@erplora/ui`, sin usar todavía

- `ion:checkmark-done-outline` — acción **Completar** de la bandeja, la misma que Citas; ya registrado en
  `packages/ui/src/shell/icons.ts`. Hoy: `ion:checkmark-circle-outline`. Al usarlo, cambiar `ICONS` en
  `frontend/pages/BookingsPage.vue` y su test.
