# messaging — lógica para handler Rust→WASM (Tier 2) + capacidades de host (Tier 1)

Fuente legacy: `old_modules/m_messaging/{models.py,services/module_services.py,events.py,
routes.py,channels/,drivers/,webhooks/}`. El CRUD plano (plantillas, automatizaciones,
campañas en borrador, cancelación) ya está en SQL declarativo Tier 0 (`commands/*.sql`).
Lo que sigue es lógica de dispatch a proveedores externos, batch, validación y evaluación
de triggers que **no** cabe en una sola sentencia SQL y debe ir a un handler WASM
(`handler/src/lib.rs` → `dist/handler.wasm`) o a capacidades del host.

> Regla hub-next: el WASM **nunca toca la BD** ni habla con LLMs/red directamente.
> Recibe el payload + datos leídos por el runtime, calcula y devuelve *intenciones*
> (filas a insertar/actualizar, llamadas `http.fetch` mediadas por el host) que el runtime
> valida y persiste en una transacción. La salida a WhatsApp/Twilio/MessageBird/SMTP es
> una capacidad Tier 1 (`http.fetch` / `smtp.send`) mediada por el host, nunca egress libre
> del WASM.

## 1. `send_message`  (command `messaging.messages.send`, handler WASM `send_message`)
Origen: `MessageService` + `channels/` + `drivers/` (whatsapp/sms/email) + `Message.mark_*`.
- Validar `channel ∈ {whatsapp, sms, email}` y `recipient_contact` no vacío.
  - email → validar formato de email; sms/whatsapp → validar teléfono E.164.
- Si `template_id` presente: el runtime lee la plantilla (`messaging.templates.list`/get) y
  el WASM **renderiza** `body`/`subject` sustituyendo `{{var}}` con el contexto del payload
  (`MessageTemplate.render_body/render_subject`).
- Crear fila en `messaging_message` con `status='queued'` (intención de INSERT con
  `:new_id/:hub_id/:current_user_id/:now`).
- Despacho por canal (capacidad Tier 1, mediada por el host — el WASM compone la request,
  el host la ejecuta contra el proveedor configurado en `messaging_settings`):
  - **whatsapp**: WhatsApp Cloud API (`whatsapp_api_token`, `whatsapp_phone_id`).
  - **sms**: `sms_provider` (twilio | messagebird) con `sms_api_key`/`sms_sender_name`.
  - **email**: SMTP (`email_smtp_host/port/username/password/use_tls`, `email_from_*`).
  - Cada canal debe estar `*_enabled` en settings; si no → `status='failed'`,
    `error_message='channel disabled'`.
- Según respuesta del proveedor: actualizar la fila → `mark_sent` (`status='sent'`,
  `sent_at=now`, `external_id=<id proveedor>`) o `mark_failed` (`status='failed'`,
  `error_message=<error>`). Devolver `{message_id, status, external_id, error?}`.
- Emite `messaging.message.sent` al terminar OK.

## 2. `send_campaign`  (command `messaging.campaigns.send`, handler WASM `send_campaign`)
Origen: envío masivo de `Campaign` (`Campaign.start/complete`, contadores).
- Guarda de estado: solo desde `draft` o `scheduled` (si no → error `invalid_status`).
- Transicionar a `sending` (`started_at=now`).
- **Resolver destinatarios** a partir de `target_filter` (JSON). El segmento de clientes vive
  en el módulo `customers` → cross-módulo vía **query pública** (`customers.customers.list`
  con filtros), NUNCA SELECT directo a `customers_customer`. El runtime ejecuta la query y
  pasa la lista al WASM.
- Batch: por cada destinatario, reutilizar la lógica de la pieza 1 (`send_message`) →
  intención de INSERT en `messaging_message` + dispatch Tier 1. Renderizar la plantilla de
  la campaña por destinatario con su contexto.
- Acumular contadores: `total_recipients`, `sent_count`, `delivered_count`, `failed_count`
  y persistirlos en `messaging_campaign`; al acabar `status='completed'`, `completed_at=now`.
- Operación batch sobre N filas con métricas agregadas → no cabe en una UPDATE.
- Emite `messaging.campaign.completed` con `{id, total_recipients, sent_count, failed_count}`.

## 3. Validación de variables de plantilla  (command `messaging.templates.create/update`)
Origen: `_check_template_variables` + `_KNOWN_TEMPLATE_VARIABLES` en `module_services.py`.
- El alta/edición de plantilla ya inserta vía SQL Tier 0, pero el legacy devuelve un
  **warning no bloqueante** listando variables `{{...}}` usadas que no están en el conjunto
  conocido (`customer_name`, `business_name`, `appointment_date`, `appointment_time`,
  `service_name`, `staff_name`, `total_amount`, `booking_reference`, `order_reference`,
  `reservation_date`, `reservation_time`, `party_size`, `customer_phone`, `customer_email`,
  `hub_name`, `hub_phone`, `hub_address`).
- Si se quiere conservar ese warning, moverlo a un pre-hook WASM que parsee `body`/`subject`
  con la regex `\{\{(\w+)\}\}`, calcule el conjunto desconocido y devuelva
  `{warning: "Template uses undefined variables: ..."}` junto al resultado del INSERT.
  No bloqueante (la fila se crea igual). También cubre `bulk_create_templates` (alta masiva
  con acumulación de `created`/`warnings`/`errors`).

## 4. Evaluación de triggers de automatización  (event listeners + cola de ejecuciones)
Origen: `events.py` (`_on_customer_created`, `_on_sale_completed`, `_on_leave_request_approved`)
+ `MessageAutomation` + `AutomationExecution`.
- El módulo escucha eventos cross-módulo declarados en `module.json` (`customers.created`,
  `sales.completed`). Al recibir uno, el handler WASM debe:
  - Buscar automatizaciones activas cuyo `trigger` corresponda al evento (welcome ← customer
    created; post_sale ← sale completed; etc.) — el runtime lee `messaging.automations.list`.
  - Evaluar `conditions` (JSON) contra el contexto del evento (segmento, importe mínimo…).
  - Crear una fila `messaging_automation_execution` (`status='pending'`,
    `scheduled_for = now + delay_hours`) — intención de INSERT.
  - Cuando llegue la hora (scheduled task / runtime scheduler), ejecutar el envío reutilizando
    la pieza 1, actualizar la execution (`status='sent'|'failed'`, `executed_at`, `message_id`),
    incrementar `messaging_automation.total_sent` y fijar `last_triggered_at`.
- Lógica de matching trigger↔evento + evaluación de condiciones + cola diferida → WASM/runtime
  (no es una sentencia SQL). Triggers basados en tiempo (birthday, anniversary, inactivity,
  booking_reminder) son tareas programadas que barren clientes y encolan ejecuciones.

## 5. Webhooks de estado de entrega  (Tier 1, ingress del proveedor)
Origen: `webhooks/` + `WebhookRequest` (schemas.py) + `Message.mark_delivered/mark_read`.
- Los proveedores (WhatsApp/Twilio) hacen callback con `{external_id, status, error}`.
- El host expone el endpoint (M2M con `X-Webhook-Secret`), localiza el `messaging_message`
  por `external_id` y aplica la transición: `delivered` → `delivered_at=now`;
  `read` → `read_at=now`; `failed` → `error_message`. Es un UPDATE simple por fila pero
  disparado por ingress externo, no por un command de usuario → lo orquesta el host, no el WC.

## 6. Configuración de mensajería  (settings — pendiente)
Origen: `MessagingSettings` + `MessagingSettingsUpdate`.
- La query `messaging.settings.get` ya está (lectura, sin campos secretos: NO se exponen
  `whatsapp_api_token`, `sms_api_key`, `email_smtp_password`).
- El upsert de settings (un INSERT-or-UPDATE por hub, con escritura de credenciales que el
  host debe cifrar/guardar en secret store, no en claro en la fila) queda pendiente como
  command. No se añadió UI de settings (no hay componente) para no dejar nav muerta; cuando
  se implemente, añadir `commands/settings_upsert.sql` + `schemas/settings_upsert.json` +
  `erp-messaging-settings.tsx` + su entrada de navegación.
