//! Proxy del asistente: el Hub reenvía el chat al Cloud Portal, que es el único que habla con
//! el LLM (ARQUITECTURA.md §9.3). El Hub aporta el ensamblado de tools por permiso (§9.2) y el
//! pre-filtro de módulos por el router vectorial (§9.2b), pero NUNCA llama a un LLM/embeddings
//! directamente.
//!
//! Contrato de cara al frontend:
//!   POST /api/assistant/chat/stream  body {"messages":[{"role":"user","content":"…"}]}
//!     → SSE: `data: {"type":"token","text":"…"}` … `data: {"type":"done"}`
//!
//! Hacia el Cloud (verificado en `cloud/apps/assistant/api/views.py::proxy_chat_stream`):
//!   POST /api/v1/hub/device/assistant/chat/stream  body {"input": …, "tools": [...]}
//!     → SSE de eventos del orquestador, terminado por `data: [DONE]`.

use erplora_runtime::{Registry, RequestContext};
use serde_json::{json, Value};

/// Ensambla las **tools** que el asistente puede invocar: las queries/commands de módulos
/// **activos** que declaran un bloque `ai:` y para las que el usuario tiene permiso (§9.2).
///
/// El permiso/schema se heredan de la operación (no se redeclaran): la tool que ve el LLM es
/// el mismo `execute_query`/`execute_command` que la UI, con el mismo gate.
pub fn assemble_tools(registry: &Registry, ctx: &RequestContext) -> Vec<Value> {
    let permits =
        |required: &str| ctx.permissions.contains("*") || ctx.permissions.contains(required);
    let mut tools = Vec::new();

    for (name, q) in &registry.queries {
        if !registry.is_active(&q.module_id) {
            continue;
        }
        if let Some(ai) = &q.def.ai {
            if permits(&q.def.permission) {
                tools.push(tool_def(
                    ai.name.as_deref().unwrap_or(name),
                    &ai.description,
                    "query",
                    &q.module_id,
                    q.def.schema.as_deref(),
                ));
            }
        }
    }
    for (name, c) in &registry.commands {
        if !registry.is_active(&c.module_id) {
            continue;
        }
        // Defensa en profundidad (hub#131, hub#145): un command interno NUNCA se ofrece como
        // tool del asistente, aunque un manifest (por error) le hubiera puesto un bloque `ai:`
        // — la tool que ve el LLM comparte gate con `execute_command`, que ya lo rechazaría.
        if c.def.is_internal(name) {
            continue;
        }
        if let Some(ai) = &c.def.ai {
            if permits(&c.def.permission) {
                tools.push(tool_def(
                    ai.name.as_deref().unwrap_or(name),
                    &ai.description,
                    "command",
                    &c.module_id,
                    c.def.schema.as_deref(),
                ));
            }
        }
    }

    // Orden determinista (estabilidad del prompt + tests reproducibles).
    tools.sort_by(|a, b| {
        a["name"]
            .as_str()
            .unwrap_or("")
            .cmp(b["name"].as_str().unwrap_or(""))
    });
    tools
}

/// Construye la tool-spec de una operación. `module_id` lo usa el router vectorial (§9.2b) para
/// prefiltrar por módulo ([`crate::router::filter_tools_by_modules`]); el Cloud lo ignora si no lo
/// necesita (ya recibe `kind` de la misma forma).
fn tool_def(name: &str, description: &str, kind: &str, module_id: &str, schema: Option<&str>) -> Value {
    // The operation's input schema (a JSON-Schema string) becomes the tool's
    // `parameters`, so the model calls with valid arguments. The Cloud reads it
    // as `fn.parameters` (orchestrator `_tools_from_hub`). Absent or unparseable
    // → an empty object (a no-arg tool).
    let parameters = schema
        .and_then(|s| serde_json::from_str::<Value>(s).ok())
        .unwrap_or_else(|| json!({ "type": "object", "properties": {} }));
    json!({
        "name": name,
        "description": description,
        "kind": kind,
        "module_id": module_id,
        "parameters": parameters,
    })
}

/// Traduce el payload del frontend (`{"messages":[…]}`) al body que espera el Cloud
/// (`{"input": …, "tools": […]}`), inyectando las tools ensambladas.
///
/// `input` toma el contenido del último mensaje de `role: user`; el historial completo se
/// reenvía como `messages` para que el Cloud lo use si su orquestador lo soporta.
///
/// `user` es el id del usuario LOCAL activo (de la sesión del hub). Se manda como **metadata**
/// para coste/auditoría — NO para permisos (el gate es local + el coste se mide por hub). Permite
/// que un cajero solo-local (sin cuenta cloud) use el asistente vía el token de máquina del hub.
pub fn build_cloud_body(frontend: &Value, tools: Vec<Value>, user: Option<&str>) -> Value {
    let messages = frontend
        .get("messages")
        .cloned()
        .unwrap_or_else(|| json!([]));
    let last_user = last_user_message(frontend);

    let mut body = json!({
        "input": last_user,
        "messages": messages,
        "tools": tools,
    });
    if let Some(u) = user.filter(|u| !u.is_empty()) {
        body["user"] = json!(u);
    }
    body
}

/// Extrae el contenido de texto del último mensaje de `role: user` del payload del frontend
/// (`{"messages":[…]}`). Es la "petición" que el router vectorial embebe (§9.2b). Cadena vacía si
/// no hay ningún mensaje de usuario.
///
/// El `content` puede ser una **cadena** (turno de solo texto) o una **lista de content-parts**
/// (cuando el turno lleva adjuntos: `text` + `image_url`/`input_file`). En el segundo caso se
/// concatena el texto de las partes `text` — los adjuntos (imagen/documento) no aportan query.
pub fn last_user_message(frontend: &Value) -> String {
    let Some(content) = frontend
        .get("messages")
        .and_then(Value::as_array)
        .and_then(|arr| {
            arr.iter()
                .rev()
                .find(|m| m.get("role").and_then(Value::as_str) == Some("user"))
        })
        .and_then(|m| m.get("content"))
    else {
        return String::new();
    };

    match content {
        Value::String(s) => s.clone(),
        Value::Array(parts) => parts
            .iter()
            .filter(|p| p.get("type").and_then(Value::as_str) == Some("text"))
            .filter_map(|p| p.get("text").and_then(Value::as_str))
            .collect::<Vec<_>>()
            .join(" "),
        _ => String::new(),
    }
}

/// Traduce **una línea** SSE del Cloud (`data: …`) al frame del frontend.
///
/// Devuelve `Some(frame)` con la línea SSE ya formateada (incluye `\n\n`), o `None` si la línea
/// no aporta contenido (comentarios, keep-alives). El terminador `[DONE]` del Cloud se traduce a
/// `{"type":"done"}`.
pub fn translate_sse_line(line: &str, kinds: &std::collections::HashMap<String, String>) -> Option<String> {
    let payload = line.strip_prefix("data:")?.trim();
    if payload.is_empty() {
        return None;
    }
    if payload == "[DONE]" {
        return Some(sse(&json!({ "type": "done" })));
    }

    // El Cloud emite eventos JSON del orquestador. Extraemos el texto incremental para el
    // frame `token` del frontend; `error`/`function_call` se reenvían; el resto se ignora.
    let ev: Value = match serde_json::from_str(payload) {
        Ok(v) => v,
        Err(_) => return Some(sse(&json!({ "type": "token", "text": payload }))),
    };

    if let Some(t) = ev
        .get("text")
        .or_else(|| ev.get("delta"))
        .or_else(|| ev.get("content"))
        .and_then(Value::as_str)
    {
        if !t.is_empty() {
            return Some(sse(&json!({ "type": "token", "text": t })));
        }
    }

    match ev.get("type").and_then(Value::as_str) {
        Some("error") => Some(sse(&ev)),
        // `function_call`: el bucle del web app ejecuta la op con la sesión del usuario
        // (§9.2). Se anota su `kind` (query/command) desde el catálogo ensamblado, para que
        // el web app sepa si es LECTURA (auto) o ESCRITURA (pide confirmación antes).
        Some("function_call") => {
            let mut out = ev;
            let name = out.get("name").and_then(Value::as_str).map(str::to_string);
            if let Some(kind) = name.and_then(|n| kinds.get(&n)) {
                if let Some(obj) = out.as_object_mut() {
                    obj.insert("kind".to_string(), json!(kind));
                }
            }
            Some(sse(&out))
        }
        _ => None,
    }
}

/// Formatea un valor JSON como un evento SSE `data: …\n\n`.
pub fn sse(value: &Value) -> String {
    format!("data: {}\n\n", value)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn build_body_extracts_last_user_and_tools() {
        let fe = json!({"messages":[
            {"role":"user","content":"hola"},
            {"role":"assistant","content":"hi"},
            {"role":"user","content":"crea una venta"}
        ]});
        let tools = vec![json!({"name":"pos.sale.create"})];
        let body = build_cloud_body(&fe, tools, None);
        assert_eq!(body["input"], "crea una venta");
        assert_eq!(body["tools"][0]["name"], "pos.sale.create");
        assert_eq!(body["messages"].as_array().unwrap().len(), 3);
    }

    #[test]
    fn last_user_message_from_content_parts_joins_text_only() {
        // A turn with an attachment: content is a list of parts (text + input_file).
        // The vector-router query must be the text, never the attachment.
        let fe = json!({"messages":[
            {"role":"user","content":[
                {"type":"text","text":"¿cuánto suma esta factura?"},
                {"type":"input_file","file_url":"https://s3/f.pdf","mime_type":"application/pdf","filename":"f.pdf"}
            ]}
        ]});
        assert_eq!(last_user_message(&fe), "¿cuánto suma esta factura?");
    }

    #[test]
    fn build_body_forwards_content_parts_verbatim() {
        // The Cloud reads the canonical `messages`; content-parts (image_url /
        // input_file) must reach it untouched so the assistant can read attachments.
        let fe = json!({"messages":[
            {"role":"user","content":[
                {"type":"text","text":"mira esto"},
                {"type":"image_url","image_url":{"url":"data:image/png;base64,AAA"}}
            ]}
        ]});
        let body = build_cloud_body(&fe, vec![], None);
        let parts = body["messages"][0]["content"].as_array().unwrap();
        assert_eq!(parts[1]["type"], "image_url");
        assert_eq!(parts[1]["image_url"]["url"], "data:image/png;base64,AAA");
        // `input` (legacy) carries the text of the parts.
        assert_eq!(body["input"], "mira esto");
    }

    #[test]
    fn translate_done_and_tokens() {
        let k = std::collections::HashMap::new();
        assert_eq!(
            translate_sse_line("data: [DONE]", &k),
            Some(sse(&json!({"type":"done"})))
        );
        assert_eq!(
            translate_sse_line("data: {\"text\":\"hi\"}", &k),
            Some(sse(&json!({"type":"token","text":"hi"})))
        );
        // delta key
        assert_eq!(
            translate_sse_line("data: {\"delta\":\"x\"}", &k),
            Some(sse(&json!({"type":"token","text":"x"})))
        );
        // comment / empty → None
        assert_eq!(translate_sse_line(": keep-alive", &k), None);
        assert_eq!(translate_sse_line("data:", &k), None);
        // non-JSON payload → token passthrough
        assert_eq!(
            translate_sse_line("data: plain", &k),
            Some(sse(&json!({"type":"token","text":"plain"})))
        );
        // error event forwarded
        assert_eq!(
            translate_sse_line("data: {\"type\":\"error\",\"error\":\"boom\"}", &k),
            Some(sse(&json!({"type":"error","error":"boom"})))
        );
    }

    #[test]
    fn translate_forwards_function_call() {
        // The model asking to call a module tool MUST reach the web app: it runs the
        // query/command with the user's session and continues the turn. Previously
        // this event was dropped (§9.2 keystone).
        let kinds = std::collections::HashMap::new();
        let line = r#"data: {"type":"function_call","name":"inventory.products.list","call_id":"c1","arguments":"{}"}"#;
        let out = translate_sse_line(line, &kinds).expect("function_call must be forwarded, not dropped");
        assert!(out.contains("function_call"));
        assert!(out.contains("inventory.products.list"));
        assert!(out.contains("c1"));
    }

    #[test]
    fn translate_annotates_function_call_kind() {
        // The web app auto-runs reads (query) but must CONFIRM writes (command); the
        // runtime tags each function_call with its kind from the assembled catalog.
        let mut kinds = std::collections::HashMap::new();
        kinds.insert("pos.sale.create".to_string(), "command".to_string());
        let line = r#"data: {"type":"function_call","name":"pos.sale.create","call_id":"c9","arguments":"{}"}"#;
        let out = translate_sse_line(line, &kinds).expect("forwarded");
        assert!(out.contains("\"kind\":\"command\""));
        // An unknown tool (not in the map) is forwarded without a kind → treated as read.
        let line2 = r#"data: {"type":"function_call","name":"who.knows","call_id":"c0","arguments":"{}"}"#;
        let out2 = translate_sse_line(line2, &kinds).expect("forwarded");
        assert!(!out2.contains("\"kind\""));
    }

    #[test]
    fn tool_def_carries_params_schema() {
        // The op's input schema becomes the tool's `parameters` so the model calls
        // with valid arguments (the Cloud reads `fn.parameters`).
        let schema = r#"{"type":"object","properties":{"since":{"type":"string"}},"required":["since"]}"#;
        let t = tool_def("sales.list", "List sales", "query", "sales", Some(schema));
        assert_eq!(t["parameters"]["properties"]["since"]["type"], "string");
        assert_eq!(t["parameters"]["required"][0], "since");
    }

    /// hub#131/#145: `assemble_tools` (la fuente del catálogo del asistente) nunca ofrece un
    /// command interno como tool — ni el prefijo `_` en el nombre ni un `internal:true` explícito
    /// se cuelan, aunque el manifest le pusiera (por error) un bloque `ai:`.
    #[test]
    fn assemble_tools_excludes_internal_commands_even_with_ai_block() {
        use erplora_runtime::manifest::{AiTool, CommandDef};
        use erplora_runtime::registry::{ModuleStatus, RegisteredCommand};

        fn ai_cmd(internal: bool) -> CommandDef {
            CommandDef {
                permission: "cash_register.write".to_string(),
                reads: Vec::new(),
                transaction: true,
                sql: vec!["UPDATE x SET y=1".to_string()],
                schema: None,
                emit: vec![],
                handler: None,
                min_affected_rows: None,
                ai: Some(AiTool {
                    description: "Revierte el efecto en caja de una venta anulada".to_string(),
                    name: None,
                }),
                expose_api: false,
                internal,
            }
        }

        let mut reg = Registry::new();
        reg.status.insert("cash_register".to_string(), ModuleStatus::Active);
        // Interno por CONVENCIÓN (prefijo `_`), sin declarar `internal:true`.
        reg.commands.insert(
            "cash_register._reverse_sale".to_string(),
            RegisteredCommand {
                module_id: "cash_register".to_string(),
                def: ai_cmd(false),
                sql: vec!["UPDATE x SET y=1".to_string()],
                wasm: None,
                schema: None,
            },
        );
        // Interno por FLAG explícito, sin prefijo `_`.
        reg.commands.insert(
            "cash_register.reindex_ledger".to_string(),
            RegisteredCommand {
                module_id: "cash_register".to_string(),
                def: ai_cmd(true),
                sql: vec!["UPDATE x SET y=1".to_string()],
                wasm: None,
                schema: None,
            },
        );

        let ctx = RequestContext::new("h1", "u1", ["*".to_string()]);
        let tools = assemble_tools(&reg, &ctx);
        assert!(
            tools.is_empty(),
            "ningún command interno debe exponerse como tool: {tools:?}"
        );
    }

    #[test]
    fn tool_def_defaults_params_when_no_schema() {
        let t = tool_def("x.y", "d", "query", "x", None);
        assert_eq!(t["parameters"]["type"], "object");
        assert_eq!(t["parameters"]["properties"], json!({}));
        // An unparseable schema also degrades to the empty object (never panics).
        let bad = tool_def("x.y", "d", "query", "x", Some("{not json"));
        assert_eq!(bad["parameters"]["properties"], json!({}));
    }
}
