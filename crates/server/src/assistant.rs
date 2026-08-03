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
                ));
            }
        }
    }
    for (name, c) in &registry.commands {
        if !registry.is_active(&c.module_id) {
            continue;
        }
        if let Some(ai) = &c.def.ai {
            if permits(&c.def.permission) {
                tools.push(tool_def(
                    ai.name.as_deref().unwrap_or(name),
                    &ai.description,
                    "command",
                    &c.module_id,
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
fn tool_def(name: &str, description: &str, kind: &str, module_id: &str) -> Value {
    json!({
        "name": name,
        "description": description,
        "kind": kind,
        "module_id": module_id,
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
pub fn translate_sse_line(line: &str) -> Option<String> {
    let payload = line.strip_prefix("data:")?.trim();
    if payload.is_empty() {
        return None;
    }
    if payload == "[DONE]" {
        return Some(sse(&json!({ "type": "done" })));
    }

    // El Cloud emite eventos JSON del orquestador. Extraemos el texto incremental para el
    // frame `token` del frontend; los eventos sin texto se reenvían tal cual bajo `passthrough`.
    let ev: Value = match serde_json::from_str(payload) {
        Ok(v) => v,
        Err(_) => return Some(sse(&json!({ "type": "token", "text": payload }))),
    };

    let text = ev
        .get("text")
        .or_else(|| ev.get("delta"))
        .or_else(|| ev.get("content"))
        .and_then(Value::as_str);

    match text {
        Some(t) if !t.is_empty() => Some(sse(&json!({ "type": "token", "text": t }))),
        _ => {
            // error u otros eventos del orquestador: reenvía para que el frontend decida.
            if ev.get("type").and_then(Value::as_str) == Some("error") {
                Some(sse(&ev))
            } else {
                None
            }
        }
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
        assert_eq!(
            translate_sse_line("data: [DONE]"),
            Some(sse(&json!({"type":"done"})))
        );
        assert_eq!(
            translate_sse_line("data: {\"text\":\"hi\"}"),
            Some(sse(&json!({"type":"token","text":"hi"})))
        );
        // delta key
        assert_eq!(
            translate_sse_line("data: {\"delta\":\"x\"}"),
            Some(sse(&json!({"type":"token","text":"x"})))
        );
        // comment / empty → None
        assert_eq!(translate_sse_line(": keep-alive"), None);
        assert_eq!(translate_sse_line("data:"), None);
        // non-JSON payload → token passthrough
        assert_eq!(
            translate_sse_line("data: plain"),
            Some(sse(&json!({"type":"token","text":"plain"})))
        );
        // error event forwarded
        assert_eq!(
            translate_sse_line("data: {\"type\":\"error\",\"error\":\"boom\"}"),
            Some(sse(&json!({"type":"error","error":"boom"})))
        );
    }
}
