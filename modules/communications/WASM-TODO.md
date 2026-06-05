# communications — lógica para handler Rust→WASM (Tier 2) + capacidades del host (Tier 1)

Fuente legacy: `old_modules/m_communications/{models.py,services.py,schemas.py,email_router.py,
footer.py,crypto.py,sync.py,scheduler.py,threading_service.py}`. El CRUD plano de las entidades
ownables (cuentas, grupos, reglas de enrutado, plantillas, transición de estado de hilo, cancelar
programado) ya está en SQL declarativo Tier 0 (`commands/*.sql`). Lo que sigue es lógica que **no**
cabe en una sola sentencia SQL: validación, I/O de red (IMAP/SMTP), cifrado, IA, batch y fechas.

> Regla hub-next: el WASM **nunca toca la BD**. Recibe el payload + filas que el runtime ya leyó
> (vía las queries públicas), valida/calcula y devuelve *intenciones* (filas a insertar/actualizar,
> sub-comandos `communications.*` a ejecutar, eventos a emitir) que el runtime valida y persiste en
> una transacción. El acceso a red (IMAP/SMTP) y el cifrado son **capabilities del host** (Tier 1)
> mediadas; el WASM las invoca, no abre sockets por su cuenta.

---

## 1. `compose_send`  (command `communications.compose.send`)
Origen: `ComposeService.compose_email` + `email_router.py` + `footer.py`.
- Validar destinatarios `to`/`cc`/`bcc` con regex de email (`_validate_emails`): si hay inválidos → error `invalid_email`.
- Resolver cuenta: si `account_id` vacío → primera cuenta `account_type='hub'` AND `is_active=1`
  (vía `communications.accounts.list`). Sin cuenta → error `no_active_account`.
- Si `improve=true`: NO enviar; devolver `{ready_to_send:false, improve_requested:true}` para que el
  asistente reescriba el cuerpo (la generación va por el **proxy IA de Cloud**, nunca LLM directo §9.3).
- Componer el cuerpo final aplicando el **footer** (pieza 7) si `footer_enabled`.
- Enviar por SMTP usando las credenciales **descifradas** de la cuenta (capability host `smtp.send`;
  descifrado vía pieza 8). Tras el envío:
  - upsert del hilo (`communications_thread`) por `contact_identifier`+`account_id` (crear si no existe),
  - insertar `communications_message` (direction=`outbound`, status=`sent`, headers RFC `message_id_header`),
  - incrementar `message_count`, set `last_message_at=now`, `folder='sent'`.
- Emite `communications.message.sent`. Devuelve `{thread_id, message_id, sent:true}`.

## 2. `reply_to_thread`  (command `communications.threads.reply`)
Origen: `ComposeService.reply_to_email` + `forward_email` + `threading_service.py`.
- Leer el hilo (`communications.threads.get`); inexistente → error `thread_not_found`.
- Validar `contact_identifier` como email; inválido → error `invalid_contact`.
- Asunto: prefijo `Re: ` si no lo lleva ya (forward: `Fwd: `).
- Encadenar cabeceras RFC: `in_reply_to` = `message_id_header` del último mensaje; `references` =
  acumulado (threading_service). Aplicar footer (pieza 7) y enviar por SMTP (pieza 1).
- Insertar `communications_message` outbound + actualizar contadores del hilo. Emite `communications.message.sent`.

## 3. `schedule_email`  (command `communications.compose.schedule`)
Origen: `ScheduledService.schedule_email` + `scheduler.py`.
- Validar emails (pieza 1) y resolver cuenta (pieza 1).
- Parsear `scheduled_at` ISO-8601. Guarda de fecha: **debe ser futuro** (`scheduled_at > now`) → si no, error `must_be_future`.
- Insertar `communications_scheduled_message` (status=`pending`). Devuelve `{id, scheduled_at, status:'pending'}`.
- Necesita aritmética de fechas/zonas → no es un INSERT plano (validación previa). El **disparo** real
  (cuando llega la hora) lo hace una tarea programada del runtime (pieza 6).

## 4. `assign_thread`  (command `communications.threads.assign`)
Origen: `AssignmentService.assign_thread`.
- Leer el hilo; inexistente → error `thread_not_found`.
- Capturar `from_group_id`/`from_user_id` actuales ANTES de mutar (para el log de auditoría).
- Aplicar `assigned_to_id`/`group_id` nuevos al hilo (solo los provistos).
- Insertar fila de auditoría en `communications_thread_assignment` (`assignment_type='manual_assign'`,
  `to_*` = nuevo o el antiguo si no cambia). Es atómico: mutación del hilo + inserción del log en una
  transacción → 2 sentencias dependientes ⇒ handler, no SQL único.
- Emite `communications.thread.assigned`.

## 5. `sync_account`  (command `communications.email.sync`)
Origen: `sync.py` + `email_router.py`.
- I/O de red IMAP (capability host `imap.fetch`) con credenciales **descifradas** (pieza 8). Set
  `sync_status='syncing'`; al terminar `idle`/`error` + `sync_error`.
- Por cada email nuevo (acotado por `email_max_sync_days` de settings): resolver/crear hilo por
  `message_id_header`/`in_reply_to`/`references` (threading_service.py), insertar `communications_message`
  inbound + sus `communications_message_attachment` (almacenados vía capability `storage.put` → `storage_key`).
- Aplicar **reglas de enrutado** (pieza 9) al hilo nuevo. Incrementar `unread_count`/`message_count`.
- Batch sobre N mensajes con I/O de red ⇒ claramente WASM + capabilities, no SQL.

## 6. Disparo de programados (`scheduler.py`, tarea programada del runtime)
Origen: `scheduler.py`.
- Seleccionar `communications_scheduled_message` con `status='pending'` AND `scheduled_at <= now`.
- Por cada uno: enviar (pieza 1) → set `status='sent'`, `sent_at=now`; en fallo `status='failed'` + `error_message`.
- También la guarda de `scheduled_cancel`: el SQL Tier 0 (`scheduled_cancel.sql`) ya cancela si sigue
  `pending`, pero el legacy rechaza cancelar si falta <1 min para el envío → ese guard de fecha,
  si se quiere conservar, va en un handler previo (`cancel_scheduled_checked`) con aritmética de tiempo.

## 7. Render del footer / firma (`footer.py`, Tier 1)
Origen: `footer.py` + campos `footer_*` de `communications_settings`.
- Compone el bloque HTML de firma (logo, nombre empresa, dirección, teléfono, web, enlaces sociales JSON)
  y lo concatena al `body_html`/`body_text` del email saliente (piezas 1 y 2).
- Render de plantilla/HTML → capability host (Tier 1). No toca BD: lee settings ya cargados por el runtime.

## 8. Cifrado/descifrado de credenciales (`crypto.py`, capability del host)
Origen: `crypto.py`.
- Las columnas `imap_password_encrypted`/`smtp_password_encrypted`/`access_token_encrypted` se guardan
  **ya cifradas**. El alta/rotación de credenciales debe pasar el secreto en claro por una capability
  host `crypto.encrypt` ANTES de llegar al INSERT/UPDATE (los commands SQL reciben el valor cifrado).
- El envío/sync (piezas 1,2,5) descifra con `crypto.decrypt` justo antes del I/O de red. El WASM nunca
  ve la clave maestra; solo invoca la capability. Las queries (`accounts_list.sql`) NUNCA devuelven estas columnas.

## 9. Evaluación de reglas de enrutado (`email_router.py`)
Origen: `RoutingRule` + `email_router.py`.
- Al llegar un hilo nuevo (pieza 5): evaluar `communications_routing_rule` activas por `priority` ASC
  (menor gana, primer match). `conditions` es JSON libre (p.ej. `{country_code, from_domain, subject_contains}`).
- En el primer match: set `group_id` del hilo, aplicar `auto_assign_to_id`, `auto_label` (merge en `labels`),
  `auto_priority`; insertar auditoría `communications_thread_assignment` (`assignment_type='auto_route'`).
- Si `gpt_routing_enabled` en settings: además consultar al **proxy IA de Cloud** con `gpt_routing_prompt`
  para clasificar (nunca LLM directo §9.3). Lógica de matching declarativo + IA opcional ⇒ WASM.

## 10. Singleton de ajustes (`upsert_settings`, command `communications.settings.upsert`)
Origen: `CommunicationsSettings` (SingletonMixin) + `SettingsUpdate` schema.
- `communications_settings` es **singleton por hub** (índice único en `hub_id`). El upsert (insert-or-update
  según exista fila) no es un INSERT/UPDATE plano portable a SQLite+Postgres con la misma sentencia, y debe
  validar rangos (`email_sync_interval_seconds` 10..3600, `email_max_sync_days` 1..365, `auto_close_hours>=0`).
- Resolver: el handler lee `communications.settings.get`; si no hay fila → INSERT con defaults+payload; si hay →
  UPDATE de los campos provistos (patch parcial, como `SettingsUpdate`). Devuelve la fila resultante.

---

## Notas de modelado / contrato
- Entidades ownables migradas a tabla propia: account, group, group_member, account_group, thread,
  message, message_attachment, routing_rule, thread_assignment, scheduled_message, email_template, settings.
- M2M (`communications_group_member`, `communications_account_group`) tienen CRUD pendiente de exponer
  (no había @action legacy directa; se gestionaban vía `group_ids` en el alta de cuenta). Cuando se necesite,
  añadir commands `*_member_add`/`*_link` Tier 0 análogos a los demás INSERT.
- Campos JSON (`labels`, `conditions`, `auto_label`, `variables`, `*_addresses`, `metadata`,
  `footer_social_links`) viajan como TEXT JSON; el WASM/SDK los serializa/deserializa.
- Cross-módulo: `customer_id`/`source_module`/`source_id` en `communications_thread` enlazan a otros
  módulos por **referencia opaca**; comunicaciones NO lee tablas de `customers`/etc. — si necesita el
  nombre del cliente, lo pide vía query pública del módulo dueño o lo recibe en el payload del evento.
