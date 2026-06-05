# assistant — lógica para handler Rust→WASM (Tier 2) + runtime/Cloud

Fuente legacy: `old_modules/m_assistant/{routes.py,prompts.py,tools/*.py,services/file_processor.py}`.

El CRUD plano (persistir conversaciones, mensajes y logs de acción; cancelar; borrar)
ya está en SQL declarativo Tier 0 (`commands/*.sql` + `queries/*.sql`). Lo que sigue es
la **inteligencia** del módulo: bucle agéntico, proxy LLM, tools tipadas, streaming,
confirmación de mutaciones, cuotas y procesado de ficheros. Nada de esto cabe en SQL.

> Regla hub-next: el WASM **nunca toca la BD** y **hub-next NUNCA habla con LLMs directamente**
> (§9.3). El handler recibe el payload + datos que el runtime ya leyó, decide *intenciones*
> (qué query/command público invocar, qué mensaje persistir) y el runtime las valida y ejecuta.
> Embeddings y generación se enrutan SIEMPRE por el proxy del Cloud Portal (que metra coste vía
> `AssistantUsage`). **No hay text-to-SQL**: la IA sólo puede invocar `ai_tools` tipadas
> mapeadas a un command/query + permiso.

---

## 0. Reparto de responsabilidades (importante)

Buena parte de esto NO es lógica de un WASM de cálculo puro; es orquestación que vive en el
**runtime/server** y en el **cloud-client**. El handler WASM `chat_send`/`confirm_action`
documentado aquí es la pieza determinista (parseo de la respuesta del LLM → intenciones).
El streaming (SSE/WS), la red al proxy de Cloud y la persistencia son del runtime.

- **Runtime/server**: WebSocket `/ws` + SSE, persistencia (vía commands de este módulo),
  resolución de tools por permiso del usuario, gating de cuota, ejecución de la tool confirmada.
- **cloud-client crate**: única vía a embeddings/generación; añade Bearer + `X-Hub-Id`; metra.
- **WASM `chat_send`/`confirm_action`**: traduce la respuesta del modelo en intenciones
  deterministas y formatea el texto de confirmación. Sin red, sin BD, sin reloj salvo capacidad host.

---

## 1. `chat_send`  (command `assistant.chat.send`)
Origen: `routes.py::_stream_agentic_loop` / `_ws_run_agentic_session` / `chat`.

Bucle agéntico completo de un turno de usuario:
1. Resolver/crear conversación (command `assistant.conversations.create` si no existe; el WC ya lo hace).
2. Persistir el mensaje del usuario (`assistant.messages.append`, role=`user`).
3. Construir el contexto: system prompt (ver §3) + historial (`assistant.messages.list`) +
   catálogo de tools permitidas para el usuario (ver §2).
4. Llamar al **proxy LLM de Cloud** (cloud-client) con `openai_response_id` como cursor.
5. Por cada `function_call` devuelto por el modelo:
   - Si la tool es de **lectura** → ejecutar query/command público correspondiente y devolver el
     resultado al modelo (`function_call_output`), continuando el bucle.
   - Si la tool es **mutante** → NO ejecutar; registrar `assistant.actions.log`
     (confirmed=0, `openai_call_id`=id de la function call) y devolver al cliente una **tarjeta
     de confirmación** (ver §4). El bucle se pausa hasta `confirm_action`/`cancel`.
6. Cuando el modelo emite texto final → persistir `assistant.messages.append` (role=`assistant`)
   y actualizar `assistant_conversation.openai_response_id` + `updated_at` (capacidad del runtime).
7. Gating de cuota antes del paso 4 (ver §6); si agotada → mensaje de error sin llamar al LLM.

Devuelve: `{conversation_id, assistant_text?, pending_confirmation?: {log_id, tool_name, description}}`.

## 2. Catálogo de tools tipadas (`ai_tools`)
Origen: `tools/{hub_tools,setup_tools,catalog_tools,product_tools}.py` + `apps.ai.registry`.

En hub-next cada tool legacy se reescribe como **`ai_tool`** declarativa: nombre + JSON Schema de
args + el command/query público al que mapea + permiso requerido. El runtime expone al modelo SOLO
las tools cuyos permisos tiene el usuario activo (`get_tools_for_user`). NO se ejecuta código backend
arbitrario: la tool sólo puede invocar contratos públicos de OTROS módulos (cross-módulo = contrato,
nunca SELECT directo a sus tablas).

Tools de **lectura** (auto-ejecutables): `get_hub_config`, `get_store_config`, `list_available_blocks`,
`get_selected_blocks`, `list_modules`, `list_roles`, `list_employees`, `list_tax_classes`,
`get_recommended_modules`, `get_compliance_modules`, `list_sector_assets`.

Tools **mutantes** (requieren confirmación, §4): `update_store_config`, `select_blocks`,
`create_role`, `create_employee`, `create_tax_class`, `set_regional_config`, `set_business_info`,
`set_tax_config`, `complete_setup_step` (modo setup — permiso `assistant.use_setup_mode`),
`draft_products_for_business` (genera catálogo inicial; ver §5).

> Las que tocan inventario/ventas/clientes/facturación deben mapearse a los commands públicos
> de esos módulos (`inventory.products.create`, etc.), no reimplementar su lógica aquí.

## 3. System prompts y contexto del hub
Origen: `prompts.py` (~20KB).

- Construcción del system prompt según `context` (`general` vs `setup`) y la configuración del hub.
- Inyección de `ai_context` de cada módulo instalado (RAG ligero: directorio de módulos siempre-on +
  `search_docs` lazy por módulo). Vector search es **cloud-only (pgvector)**; en SQLite degrada a
  fuerza bruta sobre vectores en BLOB (§9.5). Esto es responsabilidad del runtime + cloud-client,
  no del WASM.
- El WASM sólo ensambla el prompt final a partir de fragmentos que el runtime le pasa (determinista).

## 4. Confirmación de mutaciones (`confirm_action` / cancel)
Origen: `routes.py::confirm_action`, `cancel_action`, `_ws_handle_confirm/cancel`,
`_format_confirmation_text`, `_validate_generic_args`.

- **cancel** ya es declarativo: command `assistant.actions.cancel` (soft-delete del log pendiente).
- **`confirm_action`** (command `assistant.actions.confirm`, handler WASM `confirm_action`):
  1. Cargar el log pendiente (lo pasa el runtime; el WASM no lee BD).
  2. Validar args de la tool (`_validate_generic_args`) — guardas por tool.
  3. Emitir la *intención* de ejecutar el command público mapeado por la tool (el runtime lo ejecuta
     dentro de la transacción y captura `success`/`result`/`error_message`).
  4. Actualizar el log (`commands/action_confirm.sql` via runtime) y **reanudar el bucle agéntico**:
     devolver `function_call_output` al LLM con `openai_call_id` para que continúe la cadena de tools
     planeada (no parar tras una sola acción confirmada).
- `_format_confirmation_text(tool_name, tool_args)` → genera el texto humano de la tarjeta de
  confirmación. Lógica determinista de plantillas por tool → cabe en WASM.

## 5. `draft_products_for_business`  (tool generadora de catálogo)
Origen: `tools/product_tools.py`.

- Mapea `business_types` → sectores (`_lookup_business_type_sectors`, vía contrato público de Cloud/catálogo).
- Selecciona plantillas de productos por sector (tablas de defaults en el legacy) y casa cada uno con
  una imagen de blueprint (`_match_image` sobre assets de sector vía `list_sector_assets`).
- Devuelve la lista de productos propuestos; la creación real va por el command público de `inventory`
  (mutante → pasa por confirmación §4). La selección/fuzzy-match de imágenes es determinista → WASM;
  el fetch de assets es capacidad host (`http.fetch` mediado / cloud-client).

## 6. Cuotas y plan (`_is_quota_exhausted` / `_record_usage`)
Origen: `routes.py::_is_quota_exhausted`, `_record_usage`; `module.py::FREE_TIER_LIMITS`
(`messages_per_month: 30`), `PRICING` (subscription 5.00 €/mes).

- Antes de llamar al LLM, comprobar si el hub agotó su cuota mensual del tier (free = 30 msg/mes).
- El contaje y el metering viven en Cloud (`AssistantUsage`) — el runtime/cloud-client consulta y
  registra; el WASM sólo recibe un flag `quota_exhausted` y decide el mensaje. No bloqueante de CRUD.

## 7. Procesado de ficheros adjuntos (`file_processor.py`, Tier 1)
Origen: `services/file_processor.py`.

- Extracción de texto/datos de ficheros subidos (imágenes/PDF) para alimentar el chat.
- Es **capacidad del host** (Tier 1: render/parse de PDF/imagen), no un WASM puro ni SQL.
  El resultado se inyecta como contenido del mensaje del usuario. Pendiente de portar como
  host-capability del runtime. No bloqueante para el MVP del módulo.

## 8. Streaming (SSE / WebSocket) — runtime, no WASM
Origen: `routes.py::chat_stream`, `_stream_agentic_loop`, `_stream_via_ws`, `_stream_via_sse`,
`chat_ws`, `_ws_run_agentic_session`.

- El streaming token-a-token y la reconexión del WS (con persistencia del `conversation_id` entre
  reconexiones) son del transporte del runtime (`subscribe`/eventos), no del WASM ni del manifiesto
  declarativo. El WC actual refresca el historial vía `assistant.messages.list` tras cada turno;
  el streaming en vivo es una mejora del transporte, no del contrato del módulo.

---

### Notas de migración
- `is_system = True` (módulo de sistema, no desinstalable): es clasificación de marketplace y vive
  en Cloud (§2.4), no en `module.json`. No se replica aquí salvo que el loader lo marque.
- `openai_response_id` se conserva como cursor opaco del proveedor; en hub-next lo gestiona el
  cloud-client. La tabla lo persiste por conversación para reanudar el contexto del LLM.
