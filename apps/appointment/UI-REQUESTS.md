# Peticiones de UI de la app `appointment`

Lo que las páginas de Citas necesitan de `@erplora/ui` (y de otras apps) y todavía no está. Mientras tanto
usan lo más parecido que ya existe (dicho en cada punto); se cambia en cuanto llegue.

## `Scheduler` en `@erplora/ui/components` (port de `ok-scheduler`)

- **Qué**: la agenda de recursos del producto actual (`@erplora/outfitkit/ok-scheduler`, que usaba el
  módulo viejo): una fila por recurso, bloques posicionados por hora, arrastrar para mover (pointer
  events, pulsación mantenida en táctil, asa para cambiar la duración), teclado (flechas mueven en el
  tiempo y de recurso) y `revert()` cuando el servidor rechaza.
- **Hoy**: `frontend/components/DayGrid.vue` (día) y `WeekBoard.vue` (semana), propios de Citas, con el
  mismo aspecto, arrastre por pointer events y pulsación mantenida en táctil; sin asa de duración ni
  movimiento con flechas (la duración se cambia en «Editar la cita»).
- Al llegar: sustituir los dos componentes y sus tests por el `Scheduler`, conservando los `data-testid`
  que usan los e2e (`appointment-grid-*`, `appointment-week-*`).

## `DateField` y `TimeField` en `@erplora/ui/components` (el día y la hora en el idioma del hub)

- **Qué**: el campo de fecha y el de hora del producto actual (appointments#205, #214, #223): un campo de
  texto pintado en el idioma del hub (`23/11/2026` en español, `11/23/2026` en inglés; `14:30` o
  `02:30 PM`), con un botón de calendario que abre un selector compacto de un mes (la semana empieza
  donde la empieza el idioma; flechas y Enter), en vez del `input` nativo, que pinta el idioma del
  dispositivo y no el del hub.
- **Hoy**: `ion-input type="date"` y `type="time"` (como Horarios, Personal, Ventas e Impuestos) en la
  barra de la agenda (`appointment-toolbar-calendar`), «Nueva cita» / «Mover» y «Nueva cita periódica».
  El valor que viaja es el mismo (`AAAA-MM-DD`, `HH:MM`); solo cambia cómo se pinta si el dispositivo
  está en otro idioma que el hub.
- Al llegar: cambiar esos campos conservando sus `data-testid`.

## Iconos (registrarlos en `packages/ui/src/shell/icons.ts`, `ION_ICONS`)

- `ion:play-circle-outline` — acción **Iniciar** (la del producto actual). Hoy: `ion:sync-outline`.
- `ion:checkmark-done-outline` — acción **Completar** (la del producto actual). Hoy:
  `ion:checkmark-circle-outline`.
- `ion:repeat-outline` — segmento **Periódicas**. Hoy: `ion:sync-outline`.

Al registrarlos, cambiar `frontend/components/AppointmentList.vue` (`ICONS`) y
`frontend/components/AgendaToolbar.vue` (`VIEWS`).

## Personal: no dar de baja con citas futuras sin decidir qué pasa con ellas

- **Qué** (mercado: Fresha, Square, Phorest, Mindbody, Timely, Shortcuts): al dar de baja a alguien con
  citas futuras, Personal avisa y deja reasignarlas o cancelarlas antes. Citas ofrece la cuenta que
  necesita: `appointment.appointment.list` con `staff_id` y un rango de días (o
  `appointment.agenda.lanes`).
- **Hoy**: Citas reacciona a `staff.member.terminated` pasando sus citas futuras a «Sin asignar» con un
  aviso en la agenda (APPOINTMENT-F25): nada se pierde ni se cancela en silencio.

## Campana del shell (`packages/ui/src/shell`): avisar al equipo de una cita nueva o cancelada

- **Qué** (APPOINTMENT-F28, la campana del producto actual, old-hub:HUB_SHELL-F66): una campana en la barra
  de arriba que cuenta lo que declaran los módulos y, con permiso del dispositivo, un aviso del sistema por
  cada aviso nuevo; tocarlo abre la agenda en ese día.
- **Hecho — el aviso del dispositivo** (FIX-UI-SHELL-BELL-APPOINTMENT-NOTICES): Citas declara `notices` en su
  `LiveAppConfig` (la reserva y la cancelación de la clienta sobre `appointment.appointment.notices`),
  `base.notice.list` los rellena y la shell (`device-notices.ts` de `@erplora/ui`) los da una vez por
  dispositivo con `erplora_notify` de la app instalada; el toque abre `/appointment/agenda?date=…`; en
  Android pide antes el permiso con su frase. El navegador no avisa (decisión de mercado). e2e:
  `tests/e2e/fix-ui-shell-appointment-notices.spec.ts`.
- **Hecho — la campana** (BASE-G137, hub#168): existe y cuenta los `bell` de los módulos.
- **Hecho — el contador «Citas por confirmar» de Citas en la campana** (FIX-APPOINTMENT-SETUP-HOOKS):
  `LiveAppConfig.bell` con `appointment.appointment.count_to_confirm`, que lleva a `/appointment/agenda` y se
  refresca con `TO_CONFIRM_EVENTS`. e2e: `tests/e2e/fix-appointment-setup-hooks.spec.ts`. No queda nada pendiente
  de este punto.
