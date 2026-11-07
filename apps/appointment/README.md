# Citas (`appointment`)

La **agenda de un negocio que trabaja con cita previa** (peluquería, estética, barbería): cada cita une una clienta
de Clientes, uno o varios servicios de Servicios y un profesional de Personal a una hora que cabe en el horario del
negocio (Horarios), en el turno y las ausencias del profesional y sin pisar otra cita suya. La agenda se ve por lista
o por profesional, de día o de semana; las citas se arrastran, se confirman, se empiezan, se completan, se cancelan y
se cobran en el TPV sin volver a teclearlas, y las periódicas reservan solas su ventana. La clienta reserva, mueve y
cancela por WhatsApp o por la reserva online con las reglas del negocio.

- **Estado**: completa (2026-11-03): los 28 flujos `APPOINTMENT-F01` … `F28` están `hecho`.
- **Especificación**: [`WORKBOOK.md`](WORKBOOK.md) (en inglés, [`WORKBOOK.en.md`](WORKBOOK.en.md), hasta
  «Para quien lo mantiene»). Lo que se cambie de la app se cambia antes allí.
- **Peticiones a `@erplora/ui` y a Personal** que siguen abiertas: [`UI-REQUESTS.md`](UI-REQUESTS.md).

## Qué hace hoy

- **Agenda** (F01, F03–F05, F07–F11, F27): «Lista», «Por profesional» de día (una fila por profesional, lo cerrado
  y lo bloqueado sombreado) y de semana, y «Periódicas»; reservar con las horas libres, la clienta nueva creada sin
  salir, varios servicios con el precio y la duración propios del profesional, congelados; confirmar, iniciar,
  completar, no presentada (solo pasada la hora), cancelar con motivo, historial y borrar (archiva); arrastrar para
  mover a otra hora, otro día u otro profesional; el aviso de solape con «Reservar igual».
- **Horas libres** (F02): el horario del negocio ∩ el turno y las ausencias del profesional ∩ los bloqueos y las
  citas, en el reloj del negocio; el mostrador también ve las de dentro de la antelación mínima, la clienta no.
- **La clienta** (F06, F18): reserva, mueve y cancela por una automatización (WhatsApp, reserva online) **como la
  clienta**, solo sobre sus citas y con la política de cancelación; nace confirmada o pendiente según el ajuste y el
  servicio.
- **Periódicas** (F12–F15): series cada día, semana, dos semanas o mes, reservadas por vueltas hasta la antelación
  máxima; editar «de esta cita en adelante» parte la serie; pausar, reactivar y borrar.
- **Bloqueos** (F16): por el asistente o la API; la rejilla los pinta.
- **Cobro en el TPV** (F17): una sola cuenta por cita, con una línea de servicio por servicio al precio reservado (un
  bono puede pagarla); cobrarla la completa y anular la venta la deja sin cobrar.
- **Ajustes** (F19): antelaciones, solapes, cancelación de la clienta, ventana del calendario, intervalo y
  confirmación automática.
- **Con Clientes** (F20, F23, F24): el bloque «Historial de visitas» de la ficha; unir dos fichas mueve citas y
  series; borrar los datos de una ficha los vacía de citas, series e historial.
- **Varias de golpe y contacto** (F21, F22): hasta 50 citas, todas o ninguna; notas, teléfono (en formato
  internacional) y email.
- **Con Personal y Servicios** (F25, F26): la baja de un profesional pasa sus citas futuras a «Sin asignar» y pausa
  sus series; archivar un servicio no cambia nada de lo reservado.
- **Avisos** (F03, F28): la campana cuenta «Citas por confirmar»; la aplicación instalada avisa con un aviso del
  sistema de la cita nueva o cancelada por la clienta y lleva a la Agenda de ese día.

## Ficha

| Qué | Valor |
|---|---|
| `LiveAppConfig` | `kind = "app"`, icono `ion:calendar-outline`, categoría `people`, gratuita (`premium = False`) |
| Verticales | `hair_salon` |
| `requires` | `["customer", "service", "staff", "schedule"]` |
| Usa de otras apps | la ficha de Clientes (`find_customer`, `CustomerSearch` con el alta rápida), los servicios y quién los hace de Servicios (`find_service`), el profesional, su turno y sus ausencias de Personal (`resolve_member`, `staff.availability.for_member`), el horario de Horarios (`schedule.hours.for_range`) y, sin ser requisito, la cuenta de Venta (`sale.order.open`, `sale.order.get`) |
| Quién la usa | Reservas online (la requiere y reserva por sus operaciones), Venta (comprueba el precio reservado contra `appointment.appointment.get`), Clientes (el bloque `frontend/customer-card/VisitHistory.vue`), la Bandeja de WhatsApp (la automatización de fábrica que avisa a la clienta cuando se confirma su cita), Automatizaciones, la campana y los avisos del dispositivo de la shell, y el asistente |
| Pantallas | `/appointment/agenda` (Lista, Por profesional · Día y Semana, Periódicas) y `/appointment/settings` |
| Operaciones | 14 consultas (`queries.py`) y 27 acciones (`services.py`), todas con `ai=`; 35 rutas en `/api/appointment/…` (las seis reacciones de la plataforma no tienen ruta) |
| Eventos | 21 (`events.py`): `appointment.appointment.{created,confirmed,started,completed,marked_no_show,cancelled,deleted,rescheduled,updated,charged,uncharged,check_opened,check_closed,unassigned,reassigned}`, `appointment.blocked_time.{created,deleted}`, `appointment.recurring.{created,updated,deleted}` y `appointment.settings.updated`; reacciona a `customer.customer.merged`, `customer.customer.erased`, `staff.member.terminated`, `sale.sale.created_from_appointment`, `sale.sale.voided` y `sale.order.voided` |
| Permisos | 10 (`view_`, `add_` y `change_` de `appointment` y de `own_appointment`, `delete_appointment`, `view_schedule`, `manage_schedule` y `manage_settings`); el empleado, solo lo suyo |
| Automatización de fábrica | «Cubrir el hueco cuando un cliente cancela» (`recipes.py`, FLOW-F33) |
| Tareas programadas | ninguna (las series se reservan al crearlas, al editarlas y con «Reservar citas») |
| Migraciones | `0001_initial` y `0002_appointment_order_id` |
| Admin | Django admin en `hubs.erplora.com`: citas, series, bloqueos, ajustes y contadores, para soporte; borrar una cita o una serie bloquea antes sus filas (`LockedDeletion`); lo que guarda no pasa por las operaciones ni deja aviso |

Las decisiones de diseño (disponibilidad = Horarios ∩ Personal ∩ citas, solapes con bloqueo, numeración, reloj del
negocio, recurrencias, avisos y campana…) están en «Para quien lo mantiene» del WORKBOOK; las de la migración, en la
ronda de cierre de Citas de `PLAN-HUB.md` (raíz de erplora-next).

## Tests

```bash
cd hub   # o tu worktree
TEST_DB_NAME=test_hub_<tema> uv run pytest -q apps/appointment
pnpm test apps/appointment
CI=1 pnpm e2e tests/e2e/appointment-agenda.spec.ts
CI=1 pnpm e2e tests/e2e/appointment-flows.spec.ts
CI=1 pnpm e2e tests/e2e/appointment-charge.spec.ts
```

- `test_integration_customer.py`, `test_integration_service.py`, `test_integration_staff.py`,
  `test_integration_schedule.py`, `test_integration_sale.py` y `test_integration_home.py` van contra las apps
  reales; `test_relay.py`, por el tick real del relay del outbox; `test_concurrency.py`, con hilos (dos reservas del
  mismo hueco, el borrado del admin con una escritura en curso).
- Los avisos del dispositivo y la campana los prueban además `tests/e2e/fix-ui-shell-appointment-notices.spec.ts` y
  `tests/e2e/fix-appointment-setup-hooks.spec.ts`; la reserva de la clienta, `tests/e2e/online-booking-flow.spec.ts`.

## Qué queda fuera

- **hub#527** — En un negocio de otro país, un teléfono escrito sin prefijo se guarda y se busca como español.
- **hub#632** — Los importes de cuatro cifras salen sin separador de millares.
- **hub#631**, **hub#633** y **hub#635** — una traducción «fuzzy» en inglés, siete textos en español con las
  palabras de otra app y la tarjeta de confirmación del asistente, que no dice qué registro toca.
- Lo que no hace a propósito (recordatorios, pantalla de bloqueos, reserva pública, depósitos, lista de espera,
  calendario externo…): «Lo que queda fuera» y «Lo que NO hace, a propósito» del WORKBOOK.
- Las peticiones de [`UI-REQUESTS.md`](UI-REQUESTS.md).
