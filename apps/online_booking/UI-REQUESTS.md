# Peticiones de UI de la app `online_booking`

Lo que las páginas de Reservas online necesitan de `@erplora/ui` (y de la plataforma) y todavía no está.
Mientras tanto usan lo más parecido que ya existe (dicho en cada punto); se cambia en cuanto llegue.

**Al cerrar la app (2026-10-21)**, contra `ERPlora/ui` `origin/main` `89eaf98` y `ERPlora/hub` `origin/main`
`cd9f875`: no ha llegado ninguna de las tres. Ninguna rompe un flujo de esta app (todas tienen su sustituto,
dicho abajo), así que quedan en «Fuera por ahora» (`## 6` de `MIGRATION.md`): la página pública ya está allí
(`ONLINE_BOOKING-??`, «Puerta pública `/p/<slug>/book`»), y se proponen `online_booking:ui-date-field` y
`online_booking:ui-icons` (las dos las pide también Citas). Quien entregue una la borra de aquí y cambia su
sustituto en la misma PR.

## La página pública de reservas sin sesión (`base`, puerta pública `/p/`)

- **Qué**: la página por la que la clienta reserva sola (`/p/<slug>/book`) y la de su enlace personal
  (`/p/<slug>/book/<token>`), en plantillas de Django en el dominio de la web pública, con el campo trampa,
  la espera mínima de envío y el aviso de privacidad. Su contrato (operaciones, contexto, visitante, errores)
  está en el `WORKBOOK.md`, «Contrato con la página pública». Es de `base` (PLAN-HUB, bloque 7 «puerta
  pública `/p/`»), y `MIGRATION.md` §6 la tiene fuera por ahora.
- **Hoy**: `frontend/pages/PreviewPage.vue` (`/online_booking/preview`, solo en desarrollo, para el
  propietario y el administrador) hace el mismo recorrido con las mismas operaciones públicas, juzgadas
  siempre como la clienta.
- Al llegar: el e2e `tests/e2e/online-booking-flow.spec.ts` añade el recorrido sin sesión por la página de
  `base` (F01, F10, F11) y la vista previa puede retirarse.

## `DateField` en `@erplora/ui/components` (el día en el idioma del hub)

- **Qué**: el mismo campo de fecha que pide Citas (`apps/appointment/UI-REQUESTS.md`): pintado en el idioma
  del hub con su selector de un mes, en vez del `input` nativo, que pinta el idioma del dispositivo.
- **Hoy**: `ion-input type="date"` en el día de la vista previa (`ob-preview-day`) y el filtro «Fecha» de la
  bandeja (el de la `DataTable`). El valor que viaja es el mismo (`AAAA-MM-DD`).
- Al llegar: cambiar esos campos conservando sus `data-testid`.

## Iconos (registrarlos en `packages/ui/src/shell/icons.ts`, `ION_ICONS`)

- `ion:checkmark-done-outline` — acción **Completar** de la bandeja, la misma que pide Citas. Hoy:
  `ion:checkmark-circle-outline`. Al registrarlo, cambiar `ICONS` en `frontend/pages/BookingsPage.vue`.
