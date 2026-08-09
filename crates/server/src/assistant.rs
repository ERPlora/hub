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

    // Tools del CORE — capacidades del hub que no pertenecen a ningún módulo. Sin ellas el
    // asistente está ciego justo en el hub VACÍO, donde no hay tools de módulo que ofrecer.
    //
    // La primera es `hub.setup.status` (ADR-0224/0230): «¿qué falta por configurar?» tiene
    // respuesta computable, y sin esta tool el modelo la sustituía por una página de consejo
    // fiscal genérico (caso real: modelo 036, IAE, OSS… en vez de la checklist del hub). El gate
    // es el MISMO de la query core (`hub.users.view` — toda sesión lo tiene, ninguna API key), y
    // el runtime lo revalida server-side igual que con cualquier tool: esto solo la OFRECE.
    // (name, description, kind, permission, schema). El límite que fijó Ioan (2026-08-09):
    // el asistente actúa CON los permisos del usuario y las mutaciones pasan por confirm-card —
    // pero lo DESTRUCTIVO (uninstall, reset, purge, borrar) no se ofrece JAMÁS: eso lo hace el
    // usuario con sus manos. Hay un test que barre el catálogo y lo garantiza.
    let core_tools: &[(&str, &str, &str, &str, Option<&str>)] = &[
        (
            "hub.setup.status",
            "What is left to configure in THIS hub, live: the union of core setup items (business \
             identity, fiscal identity, apps, staff) and each installed module's own checklist — \
             status, blocking level, route and available actions per item. Call it whenever the \
             user asks what is missing, what to configure, or why an operation is blocked. The \
             answer is already ordered and filtered by country and permission: relay it, do not \
             re-derive or second-guess it.",
            "query",
            erplora_runtime::hub_users::VIEW_USERS_PERMISSION,
            None,
        ),
        (
            "hub.marketplace.search",
            "Search the ERPlora marketplace catalogue — modules this hub could install (id, name, \
             description, version, pricing). Call it when the user needs a capability no installed \
             module covers (e.g. \"add a product\" with no inventory module), BEFORE saying \
             something cannot be done: the answer to a missing capability is usually a module.",
            "query",
            erplora_runtime::hub_users::VIEW_USERS_PERMISSION,
            Some(r#"{"type":"object","properties":{"search":{"type":"string","description":"Free-text filter over name/description/tags. Omit to list everything."}}}"#),
        ),
        (
            "hub.modules.install",
            "Install a marketplace module into THIS hub (downloads, verifies, migrates and \
             activates it; its tools and screens appear immediately). Mutating: the user confirms \
             a card before it runs — never claim it is installed until the result comes back. Use \
             the module_id exactly as hub.marketplace.search returned it.",
            "command",
            erplora_runtime::hub_users::ADMINISTER_PERMISSION,
            Some(r#"{"type":"object","properties":{"module_id":{"type":"string","description":"Marketplace module id, e.g. \"inventory\""},"version":{"type":"string","description":"Optional. Omit to install the latest published version."}},"required":["module_id"]}"#),
        ),
    ];
    for (name, description, kind, permission, schema) in core_tools {
        if permits(permission) {
            // module_id "hub" marca tool del CORE: `filter_tools_by_modules` la preserva
            // explícitamente (el core no es un módulo y su ref_id nunca está en el índice).
            tools.push(tool_def(name, description, kind, "hub", *schema));
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

/// Builds the **system prompt** of the turn: who the assistant is, which hub it is standing in,
/// and the rules it answers by.
///
/// Why this exists at all: the Cloud is a stateless bridge (ADR-0149) and its boundary inserts
/// `instructions or ""` as the system message
/// (`saas/apps/assistant/services/history.py::prepare_client_messages`). A body without
/// `instructions` therefore does not get a *default* system prompt — it gets an **empty** one, and
/// the model answers as a generic chatbot that has never heard of ERPlora.
///
/// The module map comes from the manifest block designed for it: `agent.description`
/// (`schemas/module.schema.json` → `agent`, ARQUITECTURA.md §9.2). Only **active** modules are
/// listed — an inactive one is not a capability of this hub, and naming it would have the model
/// offer what the dispatcher refuses.
///
/// `client_system` carries the `system` turns the web app sent (today, the `hub.setup.status`
/// briefing of ADR-0230). They are folded in HERE because the Cloud drops client `system`
/// messages: `instructions` is the only channel that survives the boundary.
pub fn build_instructions(registry: &Registry, client_system: &[String], now: &str) -> String {
    let mut s = String::from(
        "You are the ERPlora assistant. ERPlora is a modular, multi-tenant ERP/POS: the user is \
         working inside their own Hub — their business's instance — which loads business modules \
         on demand from the ERPlora marketplace.\n\n\
         You are not a general-purpose chatbot. Every question is about THIS business and THIS \
         hub unless the user plainly says otherwise.\n\n",
    );

    // "Today" is the one fact a model can never supply itself — its clock froze at training
    // time — and in an ERP the date is load-bearing: today's sales, this quarter, due dates.
    // Injected per request; UTC so it is unambiguous, and the model converts for the user.
    s.push_str(&format!(
        "## Current date and time\n\nNow (UTC): **{now}**. Trust this over any date you \
         believe from training; resolve \"today\", \"yesterday\" and \"this month\" from it, in \
         the user's timezone if they state one.\n\n"
    ));

    // Active modules with the description their manifest declares for the assistant.
    let mut modules: Vec<&erplora_runtime::manifest::Manifest> = registry
        .installed
        .iter()
        .filter(|m| registry.is_active(&m.id))
        .collect();
    modules.sort_by(|a, b| a.id.cmp(&b.id)); // deterministic prompt (cacheable, testable)

    if modules.is_empty() {
        s.push_str(
            "## This hub\n\nNo business modules are installed yet. The user installs them from \
             the marketplace; until then you can only help with setup and with what the core \
             hub itself offers.\n\n",
        );
    } else {
        s.push_str(&format!(
            "## Modules installed in this hub ({})\n\nThese, and only these, are the business \
             capabilities available here:\n\n",
            modules.len()
        ));
        for m in modules {
            match &m.agent {
                Some(a) => s.push_str(&format!("- **{}** (`{}`) — {}\n", m.name, m.id, a.description)),
                None => s.push_str(&format!("- **{}** (`{}`)\n", m.name, m.id)),
            }
            // Each tab, with the route the shell actually serves. This is what turns "how do I
            // change a price?" into a real answer instead of an invented menu.
            for nav in &m.navigation {
                s.push_str(&format!(
                    "    - {} → `/m/{}/{}`\n",
                    nav.label, m.id, nav.id
                ));
            }
        }
        s.push('\n');
    }

    // ADR-0123. This is a hub-wide invariant, so it is stated ONCE here rather than in each
    // module's JSON Schema — those only say `{"type":"integer"}`, and `12` validates cleanly
    // while meaning 0.12 €. The failure is silent and it writes to the database, so the rule
    // carries a worked example: a rule without one gets re-derived, and re-derived wrong.
    s.push_str(
        "## Money is always integer CENTS\n\n\
         Every amount in this system — prices, costs, totals, payments, discounts — is an \
         **integer number of cents**. Never send a decimal.\n\n\
         Whatever way the user writes or says it, convert before calling a tool:\n\
         `12.50` · `12,50` · `12,50 €` · `12 euros 50` · `12 euros con 50 céntimos` → **1250**.\n\
         `8` · `8 €` · `8 euros` → **800**. `0,05` · `5 céntimos` → **5**.\n\n\
         Reading back, do the inverse: an amount of `1250` is presented to the user as 12,50 €. \
         If an amount is ambiguous, ask — a price written wrong by a factor of 100 is a real \
         invoice at the wrong price, and the schema will not catch it.\n\n",
    );

    // The update commands of this hub take no patch yet: most demand the whole editable object,
    // so "change the price" is really "resend the product". Any field the model supplies from
    // memory instead of from a read overwrites live data, and it does so silently — a well-formed
    // value passes the schema. Read-then-write is the rule that makes that safe, and it is stated
    // rather than assumed.
    s.push_str(
        "## Changing an existing record: READ it first\n\n\
         Most update tools here expect the whole editable record, not just the field you want to \
         change. So, before calling one:\n\n\
         1. Read the current record (the matching `…get` or `…list` query).\n\
         2. Change ONLY what the user asked for.\n\
         3. Send every other field back exactly as you read it.\n\n\
         **Never invent a field you did not read** — not a name, not a tax category, not a \
         barcode, not a description. Supplying a plausible-looking value overwrites the real one, \
         and nothing will flag it. If you could not read the record, say so and stop.\n\n",
    );

    // The standing order. Two different things pull the model away from the product it is
    // embedded in: its own memory of other ERPs, and the Cloud's server-side `web_search`
    // (ADR-0155). Both answer confidently about software the user is not running. "How do I
    // change a price?" has a real answer in the map above; the web is for facts that genuinely
    // live outside the hub.
    s.push_str(
        "## Answer from THIS hub first — always\n\n\
         Before anything else, look at what is above: the modules this hub runs, their screens, \
         and the tools you were offered. That is the product the user is looking at.\n\n\
         - **How-to questions are about THIS app.** \"How do I change a price?\" is answered by \
         naming the screen and the steps in it — e.g. the Products screen of the inventory \
         module (`/m/inventory/products`), open the product and edit it. Never answer with how \
         some other ERP does it.\n\
         - **Never answer from memory or from a generic idea of what ERP software does.** If it \
         is not in the map above and no tool covers it, say that this hub does not do it — that \
         is a useful answer; an invented menu is not.\n\
         - **Web search is the last resort, never the first**, and only for facts that live \
         outside this hub (a tax rate that changed, a legal deadline). Never use it to describe \
         how ERPlora works. If you do use it, cite the source and its date.\n\n",
    );

    // Multilingual is more than "reply in Spanish". The labels above are the ENGLISH SOURCE of
    // the i18n catalogue (ADR-0055/0199) and the shell paints them translated, so naming a tab
    // verbatim can send the user hunting for a word that is not on their screen.
    s.push_str(
        "## Language\n\n\
         Reply in the language the user writes in, whatever it is, and switch if they switch. \
         The user's own language wins over the language of this prompt.\n\n\
         ⚠️ The module and screen names above are the **English source** of a translated \
         interface: the user very likely sees them in their own language (Products → Productos). \
         So translate the screen name when you name it, and lean on the route (`/m/…`) and on \
         what the screen is *for*, which do not change with the language.\n\n",
    );

    s.push_str(
        "## How to answer\n\n\
         - For anything about live business data — stock, sales, invoices, customers, bookings, \
         staff — CALL A TOOL. Never answer from memory and never invent a figure: the tools are \
         this hub's real database.\n\
         - The tools you are offered are already filtered by the current user's permissions. If \
         no tool covers what is asked, say so plainly and name the screen where the user can do \
         it by hand.\n\
         - Tools whose name marks a write are confirmed by the user before they run; describe \
         what will change rather than claiming it is already done.\n\
         - You CAN act on this hub with the user's permissions — including installing modules \
         (each install is confirmed by the user on a card). DESTRUCTIVE actions are different by \
         design: uninstalling modules, deleting the hub or wiping data are never yours — you \
         have no tool for them on purpose. Say so plainly and point to the screen where the \
         user does it themselves.\n\
         - Tax rates and fiscal numbering that the app APPLIES come from the hub's fiscal tables, \
         never from this conversation. You may explain the rules; you may not be the source of \
         them.\n\
         - Answer in the user's language, and be concise: the assistant lives in a side drawer \
         next to someone who is working.\n",
    );

    // The client's system turns (setup briefing, ADR-0230) go last: they describe the state of
    // THIS hub right now and must override anything general said above.
    for extra in client_system.iter().filter(|e| !e.trim().is_empty()) {
        s.push('\n');
        s.push_str(extra);
        s.push('\n');
    }

    s
}

/// Extracts the `content` of every `role: system` turn in the frontend payload, in order.
///
/// The web app opens a configuration chat with a `system` briefing built from `hub.setup.status`
/// (ADR-0230). The Cloud drops client `system` messages at its boundary, so the runtime lifts
/// them out here and [`build_instructions`] folds them into the channel that survives.
pub fn client_system_messages(frontend: &Value) -> Vec<String> {
    frontend
        .get("messages")
        .and_then(Value::as_array)
        .map(|arr| {
            arr.iter()
                .filter(|m| m.get("role").and_then(Value::as_str) == Some("system"))
                .filter_map(|m| m.get("content").and_then(Value::as_str))
                .map(str::to_string)
                .collect()
        })
        .unwrap_or_default()
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
pub fn build_cloud_body(
    frontend: &Value,
    tools: Vec<Value>,
    user: Option<&str>,
    instructions: &str,
) -> Value {
    // Client `system` turns are already folded into `instructions` ([`build_instructions`]) —
    // the Cloud would drop them here anyway. Stripping them keeps the same text from also
    // spending the Cloud's 1 MB payload cap (`history.enforce_payload_cap`).
    let messages = frontend
        .get("messages")
        .and_then(Value::as_array)
        .map(|arr| {
            Value::Array(
                arr.iter()
                    .filter(|m| m.get("role").and_then(Value::as_str) != Some("system"))
                    .cloned()
                    .collect(),
            )
        })
        .unwrap_or_else(|| json!([]));
    let last_user = last_user_message(frontend);

    let mut body = json!({
        "input": last_user,
        "messages": messages,
        "tools": tools,
        "instructions": instructions,
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

    /// Build a `Manifest` from the JSON a real `module.json` carries. Deserializing (rather
    /// than a struct literal) keeps the fixture honest: it exercises the same parse the
    /// installer runs, and it does not have to be updated every time the manifest grows a
    /// field.
    fn manifest(id: &str, name: &str, agent: Option<&str>) -> erplora_runtime::manifest::Manifest {
        let mut m = json!({ "id": id, "name": name, "version": "1.0.0" });
        if let Some(desc) = agent {
            m["agent"] = json!({ "description": desc });
        }
        serde_json::from_value(m).expect("fixture manifest must parse")
    }

    /// A registry with `modules` installed; each entry is `(id, name, agent, active)`.
    fn registry_with(modules: &[(&str, &str, Option<&str>, bool)]) -> Registry {
        use erplora_runtime::registry::ModuleStatus;
        let mut reg = Registry::new();
        for (id, name, agent, active) in modules {
            reg.installed.push(manifest(id, name, *agent));
            reg.status.insert(
                (*id).to_string(),
                if *active {
                    ModuleStatus::Active
                } else {
                    ModuleStatus::Inactive
                },
            );
        }
        reg
    }

    /// The keystone: the turn reaching the Cloud must carry a system prompt that says WHAT
    /// ERPlora is and WHICH modules this hub runs. Without it the model is a generic chatbot
    /// that answers "which system do you mean?" — the Cloud inserts `instructions or ""` as
    /// the system message (`history.prepare_client_messages`), so an absent field is an EMPTY
    /// system prompt, not a default one.
    #[test]
    fn instructions_identify_erplora_and_list_active_modules() {
        let reg = registry_with(&[
            ("inventory", "Inventory", Some("Product catalog and basic stock control"), true),
            ("kitchen", "Kitchen", Some("Kitchen order display"), false),
        ]);
        let ins = build_instructions(&reg, &[], "2026-08-09T14:30:00Z (Sunday)");

        assert!(ins.contains("ERPlora"), "must name the product: {ins}");
        // The active module is named, with the `agent.description` the manifest declares for
        // exactly this purpose (schemas/module.schema.json → `agent`).
        assert!(ins.contains("inventory"), "active module id missing: {ins}");
        assert!(
            ins.contains("Product catalog and basic stock control"),
            "agent.description missing: {ins}"
        );
        // An INACTIVE module is not part of this hub's capabilities: offering it would have the
        // model promise something the dispatcher refuses.
        assert!(!ins.contains("Kitchen order display"), "inactive module leaked: {ins}");
    }

    /// The production failure this pins: asked "¿qué necesito configurar para poder empezar a
    /// vender?", the assistant produced a page of GENERIC Spanish fiscal advice (modelo 036, IAE,
    /// OSS…) — because the live answer, `hub.setup.status`, was not callable from a normal chat.
    /// The setup briefing (ADR-0230) only arrives when the drawer opens from a setup screen; a
    /// question typed anywhere else had no path to the document. The query IS the answer
    /// (setup-status.md §1: "el estado de configuración es UNA query"), so it is offered as a
    /// tool in EVERY turn, to any session — the runtime's own gate (`hub.users.view`, granted to
    /// every session and no API key) still revalidates server-side.
    #[test]
    fn assemble_tools_offers_the_core_setup_status_query() {
        let ctx = RequestContext::new("h1", "u1", ["*".to_string()]);
        // An EMPTY hub: no modules, no module tools — exactly where the checklist matters most.
        let tools = assemble_tools(&Registry::new(), &ctx);
        let setup = tools
            .iter()
            .find(|t| t["name"] == "hub.setup.status")
            .expect("hub.setup.status must be offered even with zero modules installed");
        assert_eq!(setup["kind"], "query", "a read: auto-run, no confirm-card");
        assert!(
            setup["description"].as_str().unwrap_or("").to_lowercase().contains("configur"),
            "the description must say it answers configuration questions: {setup}"
        );
    }

    /// An LLM does not know what day it is — its sense of "today" froze at training time. In an
    /// ERP that is not a cosmetic gap: "today's sales", "this quarter", an invoice date or a tax
    /// deadline all hang on the clock. So every turn's instructions carry the CURRENT date and
    /// time (UTC, RFC3339, with the weekday), injected per request — never cached, never left to
    /// the model's guess. `build_instructions` takes it as a parameter so the tests can pin it.
    #[test]
    fn instructions_carry_the_current_datetime_of_every_turn() {
        let ins = build_instructions(&Registry::new(), &[], "2026-08-09T14:30:00Z (Sunday)");
        assert!(
            ins.contains("2026-08-09T14:30:00Z (Sunday)"),
            "the exact per-turn timestamp must be in the prompt: {ins}"
        );
        let lower = ins.to_lowercase();
        assert!(
            lower.contains("current date"),
            "it must be LABELLED as the current date, not float as a loose string: {ins}"
        );
        assert!(
            lower.contains("utc"),
            "the timezone must be explicit or 'today' shifts by the user's offset: {ins}"
        );
    }


    /// The production complaint this pins (2026-08-09): asked to install a module, the assistant
    /// INVENTED a security policy («solo tú puedes hacerlo desde tu Hub») — because it had no
    /// tool, and a model with no tool rationalizes. The design truth is the opposite: the
    /// assistant is another caller WITH THE USER'S PERMISSIONS (§9.2); installing is a mutation
    /// like any other — offered as a `command`, so the drawer's confirm-card gates it.
    #[test]
    fn assemble_tools_offers_marketplace_search_and_install_to_an_admin() {
        let ctx = RequestContext::new("h1", "u1", ["*".to_string()]);
        let tools = assemble_tools(&Registry::new(), &ctx);

        let search = tools.iter().find(|t| t["name"] == "hub.marketplace.search")
            .expect("search must be offered even on an empty hub — it is HOW an empty hub stops being empty");
        assert_eq!(search["kind"], "query", "a read: auto-run");

        let install = tools.iter().find(|t| t["name"] == "hub.modules.install")
            .expect("install must be offered to an admin");
        assert_eq!(install["kind"], "command", "a mutation: the confirm-card gates it");
        assert_eq!(install["parameters"]["required"][0], "module_id");
    }

    /// Permission still rules: a cashier (no `hub.administer`) is never OFFERED install — same
    /// gate as the Apps screen. Search and setup remain: reading the catalogue mutates nothing.
    #[test]
    fn install_is_not_offered_without_the_admin_permission() {
        let ctx = RequestContext::new("h1", "u1", ["hub.users.view".to_string()]);
        let tools = assemble_tools(&Registry::new(), &ctx);
        let names: Vec<&str> = tools.iter().filter_map(|t| t["name"].as_str()).collect();
        assert!(names.contains(&"hub.setup.status"));
        assert!(names.contains(&"hub.marketplace.search"));
        assert!(!names.contains(&"hub.modules.install"), "a non-admin must not see install: {names:?}");
    }

    /// The line the user drew (2026-08-09): DESTRUCTIVE actions are the user's alone. The core
    /// catalogue must never offer uninstall/reset/purge — not gated, not confirmed: ABSENT.
    #[test]
    fn destructive_host_actions_are_never_offered() {
        let ctx = RequestContext::new("h1", "u1", ["*".to_string()]);
        let tools = assemble_tools(&Registry::new(), &ctx);
        for t in &tools {
            let name = t["name"].as_str().unwrap_or("");
            assert!(
                !name.contains("uninstall") && !name.contains("reset") && !name.contains("purge")
                    && !name.contains("delete"),
                "destructive host tool offered: {name}"
            );
        }
    }


    /// The policy line itself travels in the prompt: the model must know destructive actions are
    /// off the table BY DESIGN — so it explains honestly («eso lo haces tú desde la pantalla»)
    /// instead of inventing a security policy, which is exactly the failure this session caught.
    #[test]
    fn instructions_state_that_destructive_actions_belong_to_the_user() {
        let ins = build_instructions(&Registry::new(), &[], "2026-08-09T14:30:00Z (Sunday)");
        let lower = ins.to_lowercase();
        assert!(lower.contains("destructive"), "the destructive-actions rule must be stated: {ins}");
        assert!(lower.contains("uninstall"), "with its concrete examples: {ins}");
    }

    /// The money contract (ADR-0123) is a HUB-WIDE invariant, so it belongs in the system prompt
    /// and not in each module's schema: every amount the runtime accepts is an **integer of
    /// cents**. The JSON Schemas only say `{"type":"integer","minimum":0}` — nothing there tells
    /// the model that 12.50 € is `1250`, and `12` validates perfectly while meaning 0.12 €. The
    /// user writes the price however they speak it ("12,50", "12.50", "12 euros 50"); converting
    /// that to cents is the assistant's job, and it has to be told so.
    #[test]
    fn instructions_state_the_money_contract_in_cents() {
        let ins = build_instructions(&Registry::new(), &[], "2026-08-09T14:30:00Z (Sunday)");
        let lower = ins.to_lowercase();
        assert!(lower.contains("cent"), "the money contract must be stated: {ins}");
        // The worked example is what makes it stick — a rule without one is re-derived wrong.
        assert!(
            ins.contains("1250"),
            "state the conversion with an example (12.50 -> 1250): {ins}"
        );
        // And it must be explicit that a decimal is never sent on the wire.
        assert!(
            lower.contains("never send") || lower.contains("not a decimal") || lower.contains("no decimal"),
            "must forbid sending a decimal amount: {ins}"
        );
    }

    /// Today's update commands take no patch: 46 of them across 20 modules, and 13 demand more
    /// than three fields (`customers.update` demands 18, on a record holding the tax id and the
    /// address). So changing one field means resending the whole object, and any field the model
    /// fills in from its own head overwrites real data — silently, because a well-formed value
    /// passes the schema. Until the commands themselves take a patch, the rule that keeps this
    /// safe is read-then-write, and it has to be stated: the model must not infer it.
    #[test]
    fn instructions_require_reading_the_record_before_updating_it() {
        let ins = build_instructions(&Registry::new(), &[], "2026-08-09T14:30:00Z (Sunday)");
        let lower = ins.to_lowercase();
        assert!(
            lower.contains("read") && lower.contains("update"),
            "must tell the model to read before it updates: {ins}"
        );
        assert!(
            lower.contains("never invent") || lower.contains("do not invent"),
            "must forbid inventing the fields it did not read: {ins}"
        );
    }

    /// "How do I change a price?" is a question about THIS app, and it has a real answer: the
    /// Products screen of the inventory module. The model can only give it if it is told the
    /// screens exist and where they live, so the module map carries each module's navigation
    /// with the route the shell actually serves (`/m/<module>/<tab>`, the same shape the `setup`
    /// blocks already use). Without it the model invents a plausible menu — the exact failure
    /// that makes an assistant untrustworthy for support.
    #[test]
    fn instructions_carry_the_navigation_of_each_module() {
        use erplora_runtime::registry::ModuleStatus;
        let mut reg = Registry::new();
        let m = json!({
            "id": "inventory", "name": "Inventory", "version": "1.0.0",
            "agent": { "description": "Product catalog and stock" },
            "navigation": [
                { "id": "products", "label": "Products", "component": "erp-inventory-products" },
                { "id": "movements", "label": "Movements", "component": "erp-inventory-movements" }
            ]
        });
        reg.installed.push(serde_json::from_value(m).expect("manifest parses"));
        reg.status.insert("inventory".into(), ModuleStatus::Active);

        let ins = build_instructions(&reg, &[], "2026-08-09T14:30:00Z (Sunday)");
        assert!(ins.contains("Products"), "nav label missing: {ins}");
        assert!(
            ins.contains("/m/inventory/products"),
            "the real route the shell serves must be there: {ins}"
        );
        assert!(ins.contains("/m/inventory/movements"), "every tab, not just the first: {ins}");
    }

    /// The standing order: answer from THIS hub. The Cloud may also offer a server-side
    /// `web_search` tool (ADR-0155), and the model's own memory always "knows" how some other ERP
    /// works — both produce a confident answer about software the user is not running. For a
    /// question about the product, what we have wins; the web is for facts that genuinely live
    /// outside (a tax rate changing, a legal deadline).
    #[test]
    fn instructions_put_our_own_capabilities_before_memory_and_the_web() {
        let ins = build_instructions(&Registry::new(), &[], "2026-08-09T14:30:00Z (Sunday)");
        let lower = ins.to_lowercase();
        assert!(
            lower.contains("web search") || lower.contains("web_search"),
            "must rank the web below what this hub knows: {ins}"
        );
        assert!(
            lower.contains("from memory") || lower.contains("generic"),
            "must forbid answering generically about the product: {ins}"
        );
    }

    /// The assistant is multilingual, and that is more than "reply in Spanish". The screen names
    /// it is handed are the **English source** of the i18n catalogue (ADR-0055/0199); the shell
    /// paints them translated. Telling a Spanish user to open "Products" when the tab reads
    /// "Productos" sends them looking for something that is not on screen — the same trap
    /// `setup-status.md` §6ter calls out for setup items. So the prompt has to say both: match
    /// the user's language, and treat the labels as source, not as what is painted.
    #[test]
    fn instructions_are_multilingual_and_warn_that_labels_are_english_source() {
        let ins = build_instructions(&Registry::new(), &[], "2026-08-09T14:30:00Z (Sunday)");
        let lower = ins.to_lowercase();
        assert!(
            lower.contains("language"),
            "must state the multilingual rule explicitly: {ins}"
        );
        assert!(
            lower.contains("english") && (lower.contains("translat") || lower.contains("source")),
            "must warn that screen names are the English source of a translated UI: {ins}"
        );
    }

    /// An empty hub still gets an identity. This is the case a new customer meets first, and
    /// "no modules installed" is a fact worth stating — not a reason to say nothing.
    #[test]
    fn instructions_without_modules_still_identify_erplora() {
        let ins = build_instructions(&Registry::new(), &[], "2026-08-09T14:30:00Z (Sunday)");
        assert!(ins.contains("ERPlora"), "must name the product even with no modules: {ins}");
        assert!(!ins.trim().is_empty());
    }

    /// hub#373 / ADR-0230 regression: the web app builds a setup briefing and sends it as a
    /// client `system` message — and the Cloud **drops every client `system` message** at the
    /// boundary (`prepare_client_messages`), replacing them with `instructions`. So the whole
    /// briefing died on arrival. The runtime folds it into `instructions`, which is the channel
    /// the Cloud actually reads.
    #[test]
    fn instructions_fold_in_the_client_system_briefing() {
        let briefing = "SETUP BRIEFING: the fiscal identity is pending.";
        let ins = build_instructions(&Registry::new(), &[briefing.to_string()], "2026-08-09T14:30:00Z (Sunday)");
        assert!(
            ins.contains(briefing),
            "the client briefing must survive into instructions: {ins}"
        );
    }

    /// The extraction half of the same fix: client `system` turns are lifted out of `messages`.
    #[test]
    fn client_system_messages_are_extracted() {
        let fe = json!({"messages":[
            {"role":"system","content":"briefing one"},
            {"role":"user","content":"hola"},
            {"role":"system","content":"briefing two"}
        ]});
        assert_eq!(
            client_system_messages(&fe),
            vec!["briefing one".to_string(), "briefing two".to_string()]
        );
    }

    /// End to end over the body: `instructions` travels, and the `system` turns it absorbed are
    /// gone from `messages` so the same text does not also eat the Cloud's 1 MB payload cap.
    #[test]
    fn build_body_sends_instructions_and_strips_client_system() {
        let fe = json!({"messages":[
            {"role":"system","content":"SETUP BRIEFING"},
            {"role":"user","content":"¿qué falta por configurar?"}
        ]});
        let ins = build_instructions(&Registry::new(), &client_system_messages(&fe), "2026-08-09T14:30:00Z (Sunday)");
        let body = build_cloud_body(&fe, vec![], None, &ins);

        assert!(
            body["instructions"].as_str().unwrap_or("").contains("ERPlora"),
            "instructions must reach the Cloud: {body}"
        );
        assert!(
            body["instructions"].as_str().unwrap_or("").contains("SETUP BRIEFING"),
            "the briefing must reach the Cloud: {body}"
        );
        let roles: Vec<&str> = body["messages"]
            .as_array()
            .unwrap()
            .iter()
            .filter_map(|m| m.get("role").and_then(Value::as_str))
            .collect();
        assert_eq!(roles, vec!["user"], "client `system` turns must be stripped: {body}");
    }

    #[test]
    fn build_body_extracts_last_user_and_tools() {
        let fe = json!({"messages":[
            {"role":"user","content":"hola"},
            {"role":"assistant","content":"hi"},
            {"role":"user","content":"crea una venta"}
        ]});
        let tools = vec![json!({"name":"pos.sale.create"})];
        let body = build_cloud_body(&fe, tools, None, "");
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
        let body = build_cloud_body(&fe, vec![], None, "");
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
                expect_rows: None,
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
        // Antes esto afirmaba `is_empty()` — un proxy que valía cuando SOLO los módulos aportaban
        // tools. Hoy el catálogo lleva además las tools del CORE (`module_id: "hub"`), así que el
        // contrato se afirma directo: ninguna tool de MÓDULO interna, vengan las core que vengan.
        let module_tools: Vec<_> = tools
            .iter()
            .filter(|t| t["module_id"] != "hub")
            .collect();
        assert!(
            module_tools.is_empty(),
            "ningún command interno debe exponerse como tool: {module_tools:?}"
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
