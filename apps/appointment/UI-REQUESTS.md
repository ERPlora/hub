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
  cada aviso nuevo. Para Citas: suscribirse a `appointment.appointment.notices` (las reservas y
  cancelaciones que la clienta hizo ella misma, de la agenda que ve quien mira, lo más nuevo primero, cada
  una con `kind`, `at`, el número, la clienta, los servicios, el día y la hora listos para decir y con
  quién) y contar `appointment.appointment.count_to_confirm`; un aviso por fila nueva (por `at`), tocarlo
  abre la agenda en ese día.
- **Hoy**: la lectura viva existe y está probada; la agenda enseña **N por confirmar**. No hay campana ni
  aviso del sistema: APPOINTMENT-F28 queda `parcial` con ese motivo.
- Al llegar: el flujo pasa a `hecho` con su e2e (una reserva por la API con origen WhatsApp hace sonar la
  campana del equipo, una del mostrador no).
