# tickets — lógica para handler Rust→WASM (Tier 2)

Fuente legacy: `old_modules/m_tickets/{models.py,services.py}`. El único CRUD plano que
cabe en una sola sentencia es el alta de SLA (`commands/sla_create.sql`, Tier 0) y las
lecturas (`queries/*.sql`, Tier 0). Todo lo demás — numeración atómica, máquina de
estados, sellado de timestamps de ciclo de vida/SLA, comentarios de rastro y cálculo de
incumplimiento de SLA — **no** cabe en SQL declarativo y va a un handler WASM
(`handler/src/lib.rs` → `dist/handler.wasm`).

> Regla hub-next: el WASM **nunca toca la BD**. Recibe el payload + las filas que el
> runtime lee (ticket actual, sla, contador de nº), calcula y devuelve *intenciones*
> (filas a insertar/actualizar) que el runtime valida y persiste en una transacción.
> Los timestamps los provee el runtime como capacidad de "reloj" del host (UTC naive).

## Constantes (portar de models.py)

```
TICKET_STATUSES   = open | in_progress | waiting_customer | resolved | closed | cancelled
TICKET_PRIORITIES = low | medium | high | urgent
TICKET_CATEGORIES = general | billing | technical | feature_request

VALID_TRANSITIONS = {
  open:             {in_progress, waiting_customer, resolved, cancelled},
  in_progress:      {open, waiting_customer, resolved, cancelled},
  waiting_customer: {open, in_progress, resolved, cancelled},
  resolved:         {closed, open},
  closed:           {open},
  cancelled:        {open},
}
```

## 1. `create_ticket`  (command `tickets.tickets.create`)
Origen: `TicketService.create_ticket` + `_next_ticket_number`.
- Validar `subject` y `customer_name` no vacíos (ya lo cubre el JSON Schema; revalidar).
- `priority`/`category` dentro de los enums (cubierto por schema; revalidar).
- Parsear `created_by_ref` como UUID si viene (vacío → NULL).
- Generar `ticket_number` atómico → ver pieza 8 (contador por hub+día).
- Sellar `opened_at = now`, `status = 'open'`.
- Emitir intención de INSERT en `tickets_ticket` con todos los campos.
- Devolver `{id, ticket_number, status, priority}` y emitir `tickets.ticket.created`.

## 2. `assign_ticket`  (command `tickets.tickets.assign`)
Origen: `TicketService.assign_ticket`.
- Leer el ticket (runtime); error `not_found` si no existe.
- Parsear `assigned_to_ref` (UUID requerido).
- Set `assigned_to_ref`. **Convención:** si `status == 'open'` → pasar a `in_progress`.
- Emitir intención UPDATE (assigned_to_ref, status, updated_by/updated_at).
- Devolver `{id, ticket_number, assigned_to_ref, status}`; emitir `tickets.ticket.assigned`.

## 3. `update_status`  (command `tickets.tickets.update_status`)
Origen: `TicketService.update_status` + `VALID_TRANSITIONS`.
- `new_status` dentro del enum (schema).
- Leer ticket; si `status == new_status` → error `no_change`.
- Si `new_status` no está en `VALID_TRANSITIONS[status]` → error `invalid_transition`.
- Sellado de timestamps:
  - `resolved` y `resolved_at` vacío → `resolved_at = now`.
  - `closed` y `closed_at` vacío → `closed_at = now`.
  - `open` (reapertura) → `closed_at = NULL` (resolved_at se conserva para histórico).
- Emitir UPDATE; devolver `{id, ticket_number, status}`; emitir `tickets.ticket.status_changed`.

## 4. `add_comment`  (command `tickets.comments.add`)
Origen: `TicketService.add_comment`.
- `comment_text` no vacío y `author_ref` UUID válido (schema + revalidar).
- Leer ticket (`not_found` si no existe).
- Emitir INSERT en `tickets_comment` (ticket_id, author_ref, comment_text, is_internal).
- **SLA:** si `is_internal == false` Y `ticket.first_response_at` es NULL →
  emitir UPDATE del ticket con `first_response_at = now` (marca la primera respuesta pública).
- Devolver `{id, ticket_id, is_internal, first_response_at}`; emitir `tickets.comment.added`.

## 5. `resolve_ticket`  (command `tickets.tickets.resolve`)
Origen: `TicketService.resolve_ticket`.
- Leer ticket. Errores: ya `resolved`/`closed` → `invalid_state`; `cancelled` → `invalid_state`;
  si `'resolved'` no está en `VALID_TRANSITIONS[status]` → `invalid_transition`.
- Set `status = 'resolved'`, `resolved_at = now`.
- Si `resolution_note` no vacío → INSERT comentario interno `[RESOLUTION] {note}` (author_ref=NULL).
- Emitir UPDATE + (opcional) INSERT comentario; devolver `{id, ticket_number, status, resolved_at}`;
  emitir `tickets.ticket.resolved`.

## 6. `close_ticket`  (command `tickets.tickets.close`)
Origen: `TicketService.close_ticket`.
- Leer ticket. Errores: ya `closed` → `already_closed`; `cancelled` → `invalid_state`;
  si `'closed'` no está en `VALID_TRANSITIONS[status]` → `invalid_transition`.
- `satisfaction_rating` (si viene): entero 1..5 (schema lo cubre; revalidar) → `invalid_rating`.
- Set `status = 'closed'`, `closed_at = now`, y `satisfaction_rating` si viene.
- Emitir UPDATE; devolver `{id, ticket_number, status, closed_at, satisfaction_rating}`;
  emitir `tickets.ticket.closed`.

## 7. `reopen_ticket`  (command `tickets.tickets.reopen`)
Origen: `TicketService.reopen_ticket`.
- `reason` no vacío (schema).
- Leer ticket; **solo** si `status == 'closed'` (si no → `invalid_state`).
- Set `status = 'open'`, `closed_at = NULL`.
- INSERT comentario interno `[REOPENED] {reason}` (author_ref=NULL).
- Emitir UPDATE + INSERT; devolver `{id, ticket_number, status}`; emitir `tickets.ticket.reopened`.

## 8. Contador atómico de nº de ticket (`_next_ticket_number`)
Origen: `_next_ticket_number`. Formato `TCK-YYYYMMDD-NNNN` (NNNN = secuencia por hub+día).
- Legacy usa `COUNT(*)` de tickets cuyo `ticket_number LIKE 'TCK-YYYYMMDD-%'` + 1; tiene
  ventana de carrera. En hub-next resolver como **capacidad del runtime** (counter UPSERT
  atómico por (hub_id, día), sin ventana SELECT→UPDATE, válido en SQLite y Postgres).
- El WASM solo formatea `TCK-{YYYYMMDD}-{n:04d}` con el número devuelto por el runtime.
- El índice único `ix_tickets_ticket_hub_number (hub_id, ticket_number)` es la red de seguridad.

## 9. `check_sla_breach`  (command `tickets.slas.check_breach`, lectura+cálculo)
Origen: `TicketService.check_sla_breach`. Lectura pura con cálculo de fechas → no es una
query SQL simple; va como handler WASM (el runtime le pasa el ticket + el SLA resuelto).
- **Resolución del SLA:** `ticket.sla_id` gana; si NULL, el primer `tickets_sla` activo cuyo
  `priority == ticket.priority` (runtime hace ambas lecturas y se las pasa al WASM).
- Si no hay SLA o `opened_at` es NULL → `{response_breached:false, resolution_breached:false, sla_id}`.
- Normalizar todos los datetimes a UTC naive (consistencia SQLite/Postgres).
- `response_deadline   = opened_at + response_time_hours`.
- `resolution_deadline = opened_at + resolution_time_hours`.
- **response_breached:** si hay `first_response_at` → `first_response_at > response_deadline`;
  si no → `now > response_deadline`.
- **resolution_breached:** si hay `resolved_at` → `resolved_at > resolution_deadline`;
  elif `status == 'closed'` y `closed_at` → `closed_at > resolution_deadline`;
  else → `now > resolution_deadline`.
- Devolver `{ok, ticket_id, ticket_number, sla_id, response_breached, resolution_breached,
  response_deadline, resolution_deadline}`.
