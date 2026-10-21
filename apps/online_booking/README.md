# Reservas online (`online_booking`)

La puerta por la que una clienta pide cita sola, sin llamar, y la bandeja donde el negocio la confirma. La
reserva **es una cita de Citas** con el origen «Reserva online» (`source = "online"`): esta app no guarda
reservas ni estados propios, solo la configuración de la página, el enlace personal de la clienta y la huella
del dispositivo para los límites.

- **Estado**: completa (2026-10-21): los 12 flujos, `ONLINE_BOOKING-F01` … `F12`, están `hecho`. La página
  pública sin sesión (`/p/<slug>/book`) es de `base` y aún no existe: aquí están sus operaciones, su contrato y
  una vista previa de desarrollo.
- **Especificación**: [`WORKBOOK.md`](WORKBOOK.md) (en inglés, [`WORKBOOK.en.md`](WORKBOOK.en.md), hasta
  «Para quien lo mantiene»). Lo que se cambie de la app se cambia antes allí.
- **Peticiones a `@erplora/ui` y a la plataforma** que siguen abiertas: [`UI-REQUESTS.md`](UI-REQUESTS.md).

## Qué hace hoy

- **Reservar desde fuera** (F01): servicios reservables online (hasta 5), profesional o «sin preferencia» (el
  primero libre por orden de nombre), horas libres que juzga Citas, nombre y móvil obligatorios, email si el
  negocio lo pide y nota si lo permite. La cita nace Confirmada o Pendiente según las reglas de Citas; la ficha
  de Clientes se enlaza por el móvil (E.164) o se crea, nunca se cambia. Límites: 5 por dispositivo y hora, 100
  por negocio y hora y las reservas próximas por móvil de los Ajustes (3 de fábrica).
- **La bandeja** (F02–F06, F08): las citas con origen «Reserva online», con búsqueda, filtros por columna y
  orden; confirmar, completar, no presentada, cancelar con motivo y borrar, que son las operaciones de Citas
  con el permiso de quien actúa (el de esta app **y** el de Citas). El empleado ve solo las de su agenda.
- **Ajustes** (F07): textos, color y logo de la página, email obligatorio, reservas próximas por móvil,
  elegir profesional y notas; las reglas de reserva son las de Citas (compartidas con WhatsApp) y se guardan
  con ellas, todo o nada; el interruptor de cada servicio se guarda en Servicios.
- **El enlace de la clienta** (F10, F11): ve su reserva y la cancela dentro de la política de Citas, también
  con la página apagada; nunca dice el nombre de la ficha.
- **Lo que hace Clientes** (F09, F12): al fusionar dos fichas, Citas mueve las citas y la bandeja lo refleja;
  al borrar los datos de una clienta (RGPD), esta app revoca sus enlaces y olvida la huella del dispositivo.

## Ficha

| Qué | Valor |
|---|---|
| `LiveAppConfig` | `kind = "app"`, icono `ion:globe-outline`, categoría `people`, gratuita (`premium = False`), en la Tienda (`listed`) |
| Verticales | `hair_salon` (entra en su plantilla) |
| `requires` | `["appointment", "customer", "service", "staff"]` (y, por Citas, `schedule`) |
| Usa de otras apps | Citas: `appointment.appointment.create`, `.confirm`, `.complete`, `.mark_no_show`, `.cancel`, `.delete`, `.update` (el email tecleado), `appointment.settings.update`, `appointment.availability.slots`, y sus lecturas (`bookable_members`, `current_settings`, el reloj del negocio). Clientes: `customer.customer.create`, el teléfono en E.164 y la búsqueda. Servicios y Personal: lectura del catálogo y de los profesionales. Todo con un contexto delegado con solo esos permisos |
| Pantallas | `/online_booking/bookings`, `/online_booking/settings` y, solo en el servidor de desarrollo, `/online_booking/preview` |
| Operaciones | 7 consultas (`queries.py`) y 8 acciones (`services.py`), todas con `ai=`; no-show, cancelar, borrar y cancelar con el enlace, `risk = "high"`. Rutas en `/api/online_booking/…` para todas salvo `online_booking.customer.erase` (la reacción al RGPD, solo del sistema) |
| Operaciones públicas | `online_booking.public.page`, `.services`, `.slots`, `.booking`, `.book`, `.cancel`, con el permiso `online_booking.public` (contrato en el WORKBOOK, «Contrato con la página pública») |
| Consultas vivas | `online_booking.booking.list` y `.get` (avisos de Citas, fusión y borrado de Clientes, reserva nueva) y `online_booking.settings.get` (los ajustes de la app y las reglas de Citas) |
| Eventos | 2: `online_booking.booking.created` y `online_booking.settings.updated`; solo los escucha Automatizaciones (`flow`, que se apunta a todos, FLOW-F21, todavía `parcial`). Reacciona a `customer.customer.erased` (`online_booking.customer.erase`), que entrega el relay del worker |
| Modelos | `Settings` (una fila; sin ella, los de fábrica) y `Booking` (una por cita reservada desde la página: la cita, el hash SHA-256 del enlace y la huella HMAC del visitante). UUIDv7, sin `hub_id` |
| Tarea programada | ninguna |
| Migraciones | `0001_initial` |
| Admin | Django admin con CRUD de `Settings` y `Booking` en `hubs.erplora.com` (PLAN §17–§18) |

Las decisiones de diseño (la reserva es la cita, el contexto delegado, la ficha por teléfono, «sin
preferencia», la concurrencia, los límites y el reloj) están en «Para quien lo mantiene» del WORKBOOK; las de
la migración, en la ronda 2026-10-21 (CLOSE-ONLINE_BOOKING) de `PLAN-HUB.md` (raíz de erplora-next).

## Tests

```bash
cd hub   # o tu worktree
TEST_DB_NAME=test_hub_<tema> uv run pytest -q apps/online_booking
pnpm test apps/online_booking
pnpm e2e tests/e2e/online-booking-flow.spec.ts
```

- `tests/test_integration_diary.py` y `test_integration_customer.py` van contra Citas, Clientes, Servicios y
  Personal reales, sin dobles; `tests/test_concurrency.py`, con hilos contra Postgres (dos clientas a la vez,
  la misma hora: entra una); `tests/test_relay.py`, con el bucle real del relay del worker (F09 y F12).
- `online-booking-flow.spec.ts` recorre los diez flujos con pantalla en 390, 834 y 1440, por la vista previa.

## Qué queda fuera

- **La página pública sin sesión** (`/p/<slug>/book` y `/p/<slug>/book/<token>`): es de `base` (PLAN-HUB, bloque
  7); hasta entonces nadie reserva desde fuera y la vista previa hace el recorrido. Dónde vive (el host del hub
  o el dominio aparte de la web pública) sigue sin decidir.
- Verificar el móvil con un código, bloquear a una clienta, elección de profesional obligatoria, mover la
  reserva desde el enlace, avisos a la clienta, depósito, lista de espera, calendario externo y márgenes entre
  citas: «Lo que queda fuera» del WORKBOOK.
- El campo de fecha en el idioma del hub y el icono de «Completar»: [`UI-REQUESTS.md`](UI-REQUESTS.md).
