# audit_log — lógica para handler Rust→WASM (Tier 2)

Fuente legacy: `old_modules/m_audit_log/{models.py,services.py}`. El CRUD plano (alta de
categoría) y todas las lecturas (events/timelines/búsqueda/resumen) ya están en SQL
declarativo Tier 0 (`commands/category_create.sql`, `queries/*.sql`). Lo que sigue es
lógica de numeración atómica, conteo con filtros y batch de borrado que **no** cabe en una
sola sentencia SQL y debe convertirse en handler WASM (`handler/src/lib.rs` → `dist/handler.wasm`).

> Regla hub-next: el WASM **nunca toca la BD**. Recibe el payload + datos leídos por el
> runtime, calcula y devuelve *intenciones* (filas a insertar/actualizar/borrar) que el
> runtime valida y persiste en una transacción. El "reloj" (`:now`) y el actor
> (`:current_user_id`) los aporta el host.

---

## 1. `generate_report` (command `audit_log.reports.generate`)
Origen: `AuditService.generate_report`.

Crea un `AuditReport` (tabla `audit_log_report`) que cubre `[period_start, period_end]`,
contando los eventos que casan con `filters` y guardando el recuento en la fila.

Lógica no-CRUD a implementar en WASM:
- **Validar/parsear fechas**: `period_start` y `period_end` (ISO 8601; tolerar `Z`→`+00:00`;
  `date` → medianoche UTC; naive → UTC). Requeridas → error `missing_period`. Si
  `period_start > period_end` → error `invalid_period`.
- **Conteo con filtros**: contar `audit_log_event` del hub con `is_deleted=0` y
  `occurred_at` en el rango, aplicando los filtros opcionales presentes en `filters`
  (`event_type`, `severity`, `user_ref`, `entity_type`). El runtime ejecuta el SELECT COUNT
  parametrizado que el WASM pide (capacidad de lectura mediada); el WASM no abre BD.
- **Numeración atómica `report_number`**: formato `AR-YYYYMMDD-NNNN`, donde `NNNN` es la
  secuencia por hub+día (4 dígitos). El legacy hace `SELECT count(LIKE 'AR-ymd-%') + 1`,
  que tiene ventana de carrera. En hub-next se resuelve como **capacidad de counter UPSERT
  del runtime** (atómica en SQLite y Postgres); el WASM solo formatea `AR-{day}-{n:04d}` con
  el número devuelto.

Intenciones devueltas:
- `_insert_report` con: `report_number`, `generated_at = :now`, `generated_by_ref = :current_user_id`,
  `period_start`, `period_end`, `filters` (JSON), `total_events = <conteo>`, `status = 'ready'`,
  `output_location = ''`.
- Emitir `audit_log.report.generated` con `{id, report_number, total_events, status}`.

Binds/host: `:hub_id`, `:now`, `:current_user_id` + capacidad counter + capacidad de conteo.

> Nota: el legacy marca el informe directamente como `ready` (la agregación es síncrona). El
> estado `generating`/`failed` queda para una futura generación asíncrona/de salida a S3
> (`output_location`); por ahora no se usa en el camino feliz.

---

## 2. `cleanup_old_events` (command `audit_log.events.cleanup`)
Origen: `AuditService.cleanup_old_events`.

Borrado **físico** (hard-delete, NO soft) de eventos más antiguos que `older_than_days`.
Es la única operación del módulo que borra de verdad: el log se purga por política de
retención, y el contrato de soft-delete no aplica al propio audit-trail una vez expira.

Lógica no-CRUD a implementar en WASM:
- Validar `older_than_days >= 0` (si no → error `invalid_age`).
- Calcular `cutoff = :now - older_than_days días` (aritmética de fechas → host clock).
- Seleccionar (vía capacidad de lectura mediada del runtime) los `audit_log_event` del hub
  con `occurred_at < cutoff` para poder **devolver el recuento** sin depender de `RETURNING`.
- `category` es **advisory** en el legacy (los eventos aún no se enlazan a una categoría);
  se acepta el parámetro por compatibilidad futura pero hoy no filtra.

Intenciones devueltas:
- `_hard_delete_events` con la lista de ids (o el predicado `occurred_at < cutoff`) que el
  runtime ejecuta como `DELETE FROM audit_log_event WHERE id IN (...) AND hub_id=:hub_id`.
- Resultado: `{deleted: N, cutoff: <iso>, category}`.
- Emitir `audit_log.events.cleaned` con `{deleted, cutoff}`.

Binds/host: `:hub_id`, `:now` + capacidad de lectura + capacidad de hard-delete.

> Por qué WASM y no una sola `DELETE`: hace falta (a) aritmética de fechas con el reloj del
> host, (b) devolver el número de filas afectadas de forma portable, y (c) emitir un evento
> de lote. No es un `DELETE` declarativo plano.

---

## 3. `log_event` — helper interno, NO es comando público
Origen: `AuditService.log_event` (en el legacy NO es `@action`).

Es el helper que otros módulos/middleware llaman para registrar un evento. En hub-next esto
**no** se expone como `command` con permiso de usuario: la escritura del audit-trail es una
**capacidad del runtime** invocada internamente cuando un command de otro módulo muta datos
(p.ej. el runtime, tras ejecutar `inventory.products.create`, registra un `entity_created`).

Lógica no-CRUD asociada (a alojar en el runtime / host, no en este módulo de usuario):
- **Diff `changes`**: a partir de `before_state`/`after_state` (dicts), producir
  `{campo: {before, after}}` para cada clave que difiera (incluye altas y bajas). Si ambos
  lados vacíos → `changes = NULL` (ver `_compute_changes`).
- `occurred_at` = `:now` salvo replay de importaciones.
- Inserta en `audit_log_event` con `hub_id`, denormalizando el actor
  (`user_ref`/`user_email_snapshot`/`user_role_snapshot`) e `ip_address`/`user_agent`.

> Decisión de diseño: dado que `log_event` es cross-módulo y de sistema, su tabla
> (`audit_log_event`) la OWNea este módulo, pero la **escritura** la hace el runtime como
> capacidad de auditoría, no un command de usuario. Si se necesitara exponer un alta manual,
> añadir un `command` con permiso `audit_log.admin_audit` + su schema; por ahora no se
> declara para no crear una superficie de escritura arbitraria al log.
