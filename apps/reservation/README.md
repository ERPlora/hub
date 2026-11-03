# Reservas (`reservation`)

El **libro de reservas del restaurante o del bar**: franjas horarias con su máximo de reservas y, si se quiere,
de comensales, dentro del horario del negocio; días u horas bloqueados; cada reserva con su cliente, su mesa y su
origen, de Pendiente a Completada; y una lista de espera para quien no cabe. Confirmar aparta la mesa en Mesas y
sentar abre su cuenta en Ventas. Las reservas que el cliente hace o cambia por WhatsApp entran con sus reglas.

- **Estado**: completa (2026-10-31): 22 de los 23 flujos `RESERVATION-F01` … `F23` están `hecho`. RESERVATION-F17 y
  F18 (reservar, cambiar y anular por WhatsApp) se cerraron al cerrar la app: la conversación es la respuesta
  «Reservar mesa» de la Bandeja de WhatsApp. RESERVATION-F13 (liberar solas las pendientes) está `descartado` con
  hub#551: libera, pero avisa al momento solo en el negocio de la plataforma hasta el recorrido del worker por
  negocio.
- **Especificación**: [`WORKBOOK.md`](WORKBOOK.md) (en inglés, [`WORKBOOK.en.md`](WORKBOOK.en.md), hasta
  «Para quien lo mantiene»). Lo que se cambie de la app se cambia antes allí.
- **Peticiones a `@erplora/ui` y a Mesas** que siguen abiertas: [`UI-REQUESTS.md`](UI-REQUESTS.md).

## Qué hace hoy

- **Disponibilidad** (F01–F05): franjas por día de la semana sin solapes, con máximo de reservas y de comensales;
  bloquear un día entero o unas horas; las reglas del libro (comensales, antelación, días máximos, duración,
  teléfono y correo obligatorios, minutos para liberar); confirmar solas las reservas nuevas; y la ocupación de un
  día, con «Lleno» y «Fuera de horario».
- **Reservas** (F06–F12, F20, F23): tomarla a mano con la puerta en la transacción (horario del negocio, franja,
  bloqueo, mesa libre; el personal puede llenar una franja llena a sabiendas), confirmar (retiene la mesa),
  modificar, cancelar con motivo, no presentado, sentar (sienta la mesa y abre su cuenta), completar, borrar y
  elegir una mesa libre a esa hora.
- **Lista de espera** (F14–F16): apuntar, marcar contactado, quitar y convertir en reserva con un toque.
- **WhatsApp** (F17–F19): la reserva que pide el cliente, su cambio y su anulación, con sus reglas y solo sobre su
  propia reserva, tras el «Aprobar» del dueño en Automatizaciones; y el aviso por WhatsApp cuando se confirma.
- **Con Clientes** (F21, F22): unir dos fichas mueve sus reservas; borrar los datos de una ficha los borra de sus
  reservas y entradas, y de los avisos que dejaron.
- **Liberar las pendientes** (F13, `descartado`, hub#551): la tarea del worker las cancela cada cuarto de hora.

## Ficha

| Qué | Valor |
|---|---|
| `LiveAppConfig` | `kind = "app"`, icono `ion:calendar-outline`, categoría `restaurant`, gratuita (`premium = False`) |
| Verticales | `restaurant` |
| `requires` | `["table", "customer", "schedule"]` (Mesas trae Ventas) |
| Usa de otras apps | la retención y la sesión de mesa de Mesas, la ficha de Clientes (buscar o crear por teléfono), el horario de Horarios |
| Quién la usa | la Bandeja de WhatsApp (receta `reservation_from_whatsapp`, «Reservar mesa», y `reservation_confirmed`), Automatizaciones, Mesas (lo que retiene y suelta), el asistente |
| Pantallas | `/reservation/reservations`, `/reservation/waitlist`, `/reservation/availability` y `/reservation/settings` |
| Operaciones | 11 consultas (`queries.py`) y 20 acciones (`services.py`), todas con `ai=`; 29 rutas en `/api/reservation/…` |
| Eventos | 16 (`events.py`): `reservation.reservation.{created,updated,status_changed,deleted,unconfirmed_released}`, `reservation.waitlist.{created,updated,deleted,converted}`, `reservation.time_slot.{created,deleted}`, `reservation.blocked_date.{created,deleted}`, `reservation.settings.updated` y `reservation.customer.{reassigned,erased}`; reacciona a `customer.customer.merged` y `customer.customer.erased` |
| Tarea programada | `release_unconfirmed_reservations` cada 15 minutos (`collapse`), en el ámbito fijo del worker de la fase 1 |
| Migraciones | `0001_initial` y `0002_guest_phone_e164` |
| Admin | Django admin en `hubs.erplora.com`, CRUD completo para soporte; ids y fechas, solo lectura; lo que guarda no pasa por las operaciones ni deja aviso |

Las decisiones de diseño (la puerta en la transacción, las reglas del cliente que reserva solo, una mesa por hora,
quién juzga un cambio…) están en «Para quien lo mantiene» del WORKBOOK; las de la migración, en la ronda de cierre
de Reservas de `PLAN-HUB.md` (raíz de erplora-next).

## Tests

```bash
cd hub   # o tu worktree
TEST_DB_NAME=test_hub_<tema> uv run pytest -q apps/reservation
pnpm test apps/reservation
CI=1 pnpm e2e tests/e2e/reservation-book.spec.ts
CI=1 pnpm e2e tests/e2e/reservation-whatsapp.spec.ts   # pila con SaaS, proveedor del asistente y Graph de Meta (tests/e2e/README.md)
```

- `test_integration_table.py`, `test_integration_customer.py`, `test_integration_schedule.py` y
  `test_integration_assistant.py` van contra las apps reales; `test_relay.py` y `test_scheduled_release.py`, por el
  tick real del relay y del scheduler; `test_concurrency.py`, con hilos (el último sitio de una franja).
- La parte de WhatsApp la prueban además `apps/whatsapp_inbox/tests/test_recipes.py`,
  `test_relay_auto_replies.py` y `test_relay_notify.py`, y las e2e `fix-whatsapp-inbox-recipes-assistant.spec.ts`,
  `fix-whatsapp-inbox-table-cancel.spec.ts` y `flow-send-message.spec.ts`.

## Qué queda fuera

- **hub#551** — Cuando una reserva pendiente se libera sola, la pantalla de Reservas tarda hasta cinco minutos en
  verlo (F13).
- **hub#547** — Una traducción al español marcada «fuzzy» sale en inglés y su test de traducciones no la ve.
- **hub#548** — Dos textos en español salen con las palabras de otra app («origen» en vez de «reservada por»).
- **hub#549** — La tarjeta de confirmación del asistente llama «Registro» a la reserva, la franja o la entrada que
  va a borrar.
- **hub#550** — La tarjeta de confirmación del asistente dice la mesa solo por su número, sin su zona.
- Lo que no hace a propósito (depósitos, recordatorios, plano, calendarios externos…) y lo que espera a otras apps
  (asignación automática, mesas unidas, cola de la puerta con SMS): «Lo que NO hace, a propósito» y «Lo que queda
  fuera» del WORKBOOK.
- Las peticiones de [`UI-REQUESTS.md`](UI-REQUESTS.md).
