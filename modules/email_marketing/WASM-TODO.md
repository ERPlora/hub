# email_marketing — lógica para handler Rust→WASM (Tier 2)

Fuente legacy: `old_modules/m_email_marketing/{models.py,services.py}`. El CRUD plano
(`create_list`, `create_campaign`) y los listados ya están en SQL declarativo Tier 0
(`commands/*.sql`, `queries/*.sql`). Lo que sigue es lógica de máquina de estados,
mantenimiento de contadores agregados, alta idempotente y envío batch que **no** cabe en
una sola sentencia SQL y debe convertirse en handler WASM
(`handler/src/lib.rs` → `dist/handler.wasm`).

> Regla hub-next: el WASM **nunca toca la BD**. Recibe el payload + datos leídos por el
> runtime, calcula y devuelve *intenciones* (filas a insertar/actualizar, transiciones de
> estado, deltas de contador) que el runtime valida y persiste en una transacción. El reloj
> (`now`) y la generación de ids son capacidades del host.

## Funciones del handler (`function` en `module.json` → `commands[*].handler`)

---

## 1. `subscribe`  (command `email_marketing.subscribers.subscribe`)
Origen: `EmailMarketingService.subscribe`.
- Payload: `{list_id, email, first_name?, last_name?}`.
- Validar `email` no vacío; el runtime ya validó que `list_id` existe y pertenece al hub.
- **Idempotencia case-insensitive por lista**: normalizar `email = email.strip().lower()`;
  buscar suscriptor existente en `(list_id, lower(email))`.
  - Si existe:
    - `was_subscribed = (status == 'subscribed')`.
    - Poner `status='subscribed'`, `subscribed_at = subscribed_at or now`, `unsubscribed_at=NULL`.
    - Si `first_name`/`last_name` vienen no-None → actualizarlos.
    - Si **no** estaba suscrito (reactivación): incrementar `list.total_subscribers += 1`.
    - `created=false`.
  - Si no existe: insertar suscriptor (`status='subscribed'`, `subscribed_at=now`,
    email guardado con `.strip()` SIN lowercasing — solo el match es case-insensitive);
    incrementar `list.total_subscribers += 1`; `created=true`.
- Devolver `{id, list_id, email, status, created, total_subscribers}`.
- Atomicidad: el upsert del suscriptor + delta del contador de la lista en una transacción.

## 2. `unsubscribe`  (command `email_marketing.subscribers.unsubscribe`)
Origen: `EmailMarketingService.unsubscribe`.
- Payload: `{subscriber_id, reason?}`.
- Guarda de estado: si `status == 'unsubscribed'` → error `already_unsubscribed`.
- Poner `status='unsubscribed'`, `unsubscribed_at = now`.
- **Decrementar** el contador de la lista padre: `list.total_subscribers = max(0, n-1)`
  (acotado a 0). Requiere leer `subscriber.list_id` y actualizar la fila de la lista.
- Devolver `{id, list_id, status, reason}`.
- `reason` no se persiste hoy en legacy (solo se devuelve); si se quiere audit-trail, ver §8.

## 3. `schedule_campaign`  (command `email_marketing.campaigns.schedule`)
Origen: `EmailMarketingService.schedule_campaign`.
- Payload: `{campaign_id, scheduled_for}` (ISO datetime).
- Guarda de estado: **solo** desde `draft` (si no → error `invalid_state`).
- Parsear/validar `scheduled_for` (ISO `YYYY-MM-DDTHH:MM[:SS]`); vacío/None → error
  `missing_date`; inválido → error `invalid_date`.
- Transición `draft → scheduled`; persistir `scheduled_for`.
- Devolver `{id, status, scheduled_for}`.

## 4. `send_campaign`  (command `email_marketing.campaigns.send`)  ← envío batch
Origen: `EmailMarketingService.send_campaign`.
- Payload: `{campaign_id}`.
- Guarda de estado: **solo** desde `scheduled` o `draft` (si no → error `invalid_state`).
- Leer suscriptores **activos** de la lista de la campaña (`status == 'subscribed'`).
- Transición `→ sending` y luego `→ sent` (`sent_at = now`).
- **Por cada suscriptor activo**: emitir intención de insertar un `EmailEvent`
  `{campaign_id, subscriber_id, event_type='sent', occurred_at=now, event_metadata=NULL}`.
- Incrementar `campaign.total_sent += len(subs)`.
- Devolver `{id, status, sent_at, recipients, total_sent}`.
- NO habla con SMTP/ESP real (eso vive en un worker/tarea programada externa); aquí solo se
  registran los eventos `sent`. Operación batch sobre N filas → WASM (una sola UPDATE no
  basta: hay que insertar N eventos y devolver el recuento).

## 5. `record_event`  (command `email_marketing.events.record`)
Origen: `EmailMarketingService.record_event` (en legacy NO era `@action` — venía de
callbacks externos del ESP). En hub-next se expone como command con permiso `manage_email`
para que el runtime/webhook lo invoque de forma controlada.
- Payload: `{campaign_id, subscriber_id, event_type, metadata?}`.
- Validar `event_type ∈ {sent, open, click, bounce, unsubscribe}` (si no → `invalid_event_type`).
- El runtime valida que campaña y suscriptor existen y pertenecen al hub.
- Insertar `EmailEvent {campaign_id, subscriber_id, event_type, occurred_at=now, event_metadata=metadata}`.
- **Efectos sobre contadores / estado según `event_type`**:
  - `open`   → `campaign.total_opens += 1`.
  - `click`  → `campaign.total_clicks += 1`.
  - `bounce` → `campaign.total_bounces += 1` **y** `subscriber.status = 'bounced'`.
  - `unsubscribe` → si `subscriber.status != 'unsubscribed'`: `status='unsubscribed'`,
    `unsubscribed_at = now`. (Nota: legacy NO decrementa `total_subscribers` de la lista en
    este camino — replicar ese comportamiento; el decremento solo ocurre en `unsubscribe` §2.)
  - `sent`   → solo inserta el evento (no toca contadores; `total_sent` lo lleva §4).
- Devolver `{id, campaign_id, subscriber_id, event_type}`.
- Atomicidad: inserción del evento + deltas de contador/estado en una transacción.

## 6. `get_campaign_metrics`  (cálculo de tasas — query derivada)
Origen: `EmailMarketingService.get_campaign_metrics`.
- Hoy se modela como `query email_marketing.events.list` (filas crudas de eventos) +
  `query email_marketing.campaigns.get` (contadores agregados). El **cálculo de tasas** no
  cabe en SQL declarativo limpio y va a WASM (o capacidad de cálculo del host):
  - `total_sent, total_opens, total_clicks, total_bounces` ← de la campaña.
  - `_rate(n) = 0.0 si total_sent <= 0 else float(Decimal(n)/Decimal(total_sent))`.
  - `open_rate = round(_rate(opens), 4)`, idem `click_rate`, `bounce_rate`.
  - Devolver `{campaign_id, status, total_sent, total_opens, total_clicks, total_bounces,
    open_rate, click_rate, bounce_rate}` (tasas como fracción en `[0,1]`).
- Si se prefiere, exponerlo como command WASM de solo-lectura `email_marketing.campaigns.metrics`
  cuando exista la capacidad; mientras tanto la UI puede computar las tasas a partir de los
  contadores ya devueltos por `campaigns.get`/`campaigns.list`.

## 7. Mantenimiento del contador `total_subscribers` (transversal)
- Es un agregado denormalizado en `email_marketing_list`. Lo modifican §1 (alta/reactivación,
  +1), §2 (baja, -1 acotado a 0). El insert plano `list_create.sql` lo inicializa a 0.
- Cualquier nueva ruta que cambie `subscriber.status` debe respetar la convención legacy:
  solo `subscribe`/`unsubscribe` (§1/§2) tocan el contador; `record_event` (§5) NO.

## 8. Audit-trail de `reason` (Tier 1, no crítico)
- En legacy `unsubscribe(reason=...)` y `record_event` no persisten un rastro textual; `reason`
  solo se devuelve. Si se quiere conservar el motivo de baja, añadir un campo o un append con
  timestamp vía capacidad de "reloj" del host. No bloqueante.
