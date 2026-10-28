# Personal (`staff`)

Quién trabaja y atiende en el negocio: la ficha de cada profesional (rol de catálogo, contacto, tarifa por
hora, comisión, si admite citas y la cuenta del negocio de la que cuelga), su horario semanal con descansos,
sus ausencias (las pide el empleado y las aprueba un responsable) y lo que ha ganado cada uno en
**Comisiones**. No es el acceso: las cuentas, sus papeles de permisos y el PIN son de la plataforma.

- **Estado**: completa (2026-10-22): los 21 flujos `STAFF-F01` … `F09` y `F13` … `F24` y los cinco paneles
  del Inicio viejo `STAFF-G01` … `G05` están `hecho`. `STAFF-F10` … `F12` (los servicios de cada
  profesional) son `SERVICE-F31` … `F33` de Servicios.
- **Especificación**: [`WORKBOOK.md`](WORKBOOK.md) (en inglés, [`WORKBOOK.en.md`](WORKBOOK.en.md), hasta
  «Para quien lo mantiene»). Lo que se cambie de la app se cambia antes allí.
- **Peticiones a `@erplora/ui`** que siguen abiertas: [`UI-REQUESTS.md`](UI-REQUESTS.md).

## Qué hace hoy

- **Fichas** (F01–F09): alta, edición (solo lo enviado), alta en lote de hasta 100 por el asistente y la API,
  vínculo con una cuenta del negocio (una cuenta, una ficha viva, también a la vez), desactivar (nunca con
  ausencias vivas) y dar de baja (definitiva, con fecha y motivo, libera la cuenta). La propia ficha y las
  propias ausencias se ven con la cuenta vinculada; el directorio, sin tarifa ni comisión, lo leen las otras apps.
- **Horarios** (F13–F16): semanas con un tramo y un descanso por día, sin cruzar la medianoche; manda el
  horario con fechas sobre el «Por defecto»; la disponibilidad por días son los tramos menos las ausencias
  aprobadas. Un horario nuevo propone la jornada de Ajustes.
- **Ausencias** (F17–F20, F24): pendiente → aprobada o rechazada, pendiente o aprobada → cancelada; dos de
  horas el mismo día no chocan si no se pisan; «Ausencias de hoy» en el día del negocio.
- **Comisiones, ajustes y cifras** (F21–F23): lo vendido por cada profesional en un periodo (de Ventas, con
  lo devuelto restado) × su comisión, redondeado una vez por persona; la jornada por defecto; las cifras de
  la plantilla encima de cada lista y, en el Inicio, los cinco paneles del módulo viejo (Plantilla activa,
  Ausentes hoy y Ausencias de hoy de serie; Ausencias pendientes y Empleados por rol para añadir).

## Ficha

| Qué | Valor |
|---|---|
| `LiveAppConfig` | `kind = "app"`, icono `ion:id-card-outline`, categoría `people`, gratuita (`premium = False`) |
| Verticales | `hair_salon` (entra en su plantilla) |
| `requires` | `[]` |
| Usa de otras apps | Ventas, opcional y por nombre (`sale.sale.by_staff` con `live.operations.get`, y sus avisos `sale.sale.completed`, `voided` y `refunded`); sin Ventas, Comisiones lo dice. De la plataforma, las cuentas con acceso (`base.Membership`) y la zona horaria (`timezone.localdate()`, en la fase 1 `settings.TIME_ZONE`) |
| La usan | Citas, Servicios, Control horario, Tareas y Reservas online (la requieren: importan `Member`, `resolve_member` y, según la app, `member_availability`, `own_member` o los nombres de `events.py`); reaccionan a `staff.member.terminated` Citas (`appointment.staff.release`), Servicios (`service.assignment.release_member`), Control horario (`attendance.record.close_for_terminated`) y Tareas (`task.task.release_member`). Ventas lee el directorio en el TPV y Automatizaciones tiene una plantilla sobre `staff.member.created` |
| Pantallas | `/staff/members`, `/staff/roles`, `/staff/time-off`, `/staff/schedules`, `/staff/commissions` (quien ve la compensación) y `/staff/settings` (quien guarda los ajustes) |
| Operaciones | 17 consultas (`queries.py`, todas en vivo menos `staff.account.list`) y 17 acciones (`services.py`), todas con `ai=`; 34 rutas en `/api/staff/…`; 11 abiertas a las API keys (`expose_api`) |
| Eventos | 14, `staff.<entidad>.<hecho>` (`events.py`), solo con identificadores; no reacciona a ninguno |
| Permisos | 10 (`staff.view` … `staff.request_time_off`), repartidos entre propietario, administrador, responsable y empleado en `role_permissions` |
| Tareas programadas | ninguna |
| Migraciones | `0001_initial` |
| Admin | Django admin con CRUD en `hubs.erplora.com` (PLAN §17–§18); el borrado de una ficha bloquea antes las fichas (`lock_members`, hub#66) |

Las decisiones de diseño (una cuenta y una ficha viva, el único «Por defecto», los bloqueos por persona, el
dinero en la unidad más pequeña de la moneda del negocio, los avisos sin datos personales, los ajustes retirados) están en «Para quien lo mantiene»
del WORKBOOK; las de la migración, en la ronda 2026-10-22 (CLOSE-STAFF) de `PLAN-HUB.md` (raíz de erplora-next).

## Tests

```bash
cd hub   # o tu worktree
TEST_DB_NAME=test_hub_<tema> uv run pytest -q apps/staff
pnpm test apps/staff
pnpm e2e tests/e2e/staff-flows.spec.ts tests/e2e/staff-members.spec.ts tests/e2e/staff-commissions.spec.ts
```

- Las carreras, con hilos y bloqueos reales: en `test_services.py`, dos vínculos de una cuenta y dos
  ausencias o dos aprobaciones que se solapan, a la vez; en `test_concurrency.py`, el borrado del admin
  contra cada escritura sobre la persona (hub#66). `test_integration_sale.py`: Comisiones contra Ventas
  real (cobros, devoluciones, sin Ventas).
- Lo que leen las otras apps se prueba contra Personal real en su `tests/test_integration_staff.py` (Citas,
  Servicios, Control horario, Tareas) y, por el relay del outbox, en su `tests/test_relay.py` (Citas,
  Servicios, Tareas).
- Las siete `tests/e2e/staff-*.spec.ts` pasan cada una sola en una BD recién creada (hub#176);
  `staff-flows.spec.ts` recorre los flujos con pantalla en 390, 834 y 1440.

## Qué queda fuera

- Borrar las ocho columnas de los ajustes retirados y su CHECK (el paso contract de hub#177), una vez
  desplegado.
- Lo que Comisiones aún no cuenta, de otras apps: una venta con «Atiende yo» y la sesión de un bono.
- La tarjeta de cifra y los campos de fecha y hora en el orden del idioma del Hub de
  [`UI-REQUESTS.md`](UI-REQUESTS.md).
