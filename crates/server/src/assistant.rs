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

    // Qué permiso le basta a cada módulo para LEER, tomado de sus propias queries (hub#1594).
    // Es la mitad que hace segura la clasificación de abajo: la declara el módulo repartiendo sus
    // permisos, no la adivina el core mirando nombres.
    let mut read_permissions: std::collections::HashMap<&str, std::collections::HashSet<&str>> =
        std::collections::HashMap::new();
    for q in registry.queries.values() {
        read_permissions
            .entry(q.module_id.as_str())
            .or_default()
            .insert(q.def.permission.as_str());
    }

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
                    ai.risk,
                    true,
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
                    ai.risk,
                    command_only_answers(
                        &c.def,
                        ai.risk,
                        read_permissions.get(c.module_id.as_str()),
                    ),
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
            Some(
                r#"{"type":"object","properties":{"search":{"type":"string","description":"Free-text filter over name/description/tags. Omit to list everything."}}}"#,
            ),
        ),
        (
            "hub.blueprints.list",
            "List the sector templates (blueprints) published for this hub — slug, name, \
             description, locale, country, version. A template brings a vertical's modules, seed \
             catalogue and role set in one step. Call it when the user describes their business \
             (\"I have a restaurant\") and the hub is empty or half set up, BEFORE walking them \
             through installing modules one by one.",
            "query",
            erplora_runtime::hub_users::VIEW_USERS_PERMISSION,
            None,
        ),
        (
            "hub.blueprints.apply",
            "Apply a sector template (blueprint) to THIS hub: installs its modules, seeds their \
             catalogue and applies the portable settings of the vertical. It is ADDITIVE and \
             verified so: it only inserts rows that do not exist yet — it never overwrites or \
             deletes what the hub already has (existing records are kept and the template's \
             duplicates are skipped), and it never imports people, fiscal identity or another \
             business's invoice numbering. A template does NOT set up the fiscal side: the \
             result carries `still_blocking` — what this hub STILL cannot do until somebody \
             configures it. Relay those items as PENDING; never describe a template's contents \
             as if they were done, and never say invoicing is ready while `still_blocking` names \
             it. Mutating: the user confirms a card before it runs — \
             never claim it is applied until the result comes back. Use the slug exactly as \
             hub.blueprints.list returned it.",
            "command",
            erplora_runtime::hub_users::ADMINISTER_PERMISSION,
            Some(
                r#"{"type":"object","properties":{"slug":{"type":"string","description":"Blueprint slug, exactly as hub.blueprints.list returned it."}},"required":["slug"]}"#,
            ),
        ),
        (
            "hub.modules.install",
            "Install a marketplace module into THIS hub (downloads, verifies, migrates and \
             activates it; its tools and screens appear immediately). Mutating: the user confirms \
             a card before it runs — never claim it is installed until the result comes back. Use \
             the module_id exactly as hub.marketplace.search returned it.",
            "command",
            erplora_runtime::hub_users::ADMINISTER_PERMISSION,
            Some(
                r#"{"type":"object","properties":{"module_id":{"type":"string","description":"Marketplace module id, e.g. \"inventory\""},"version":{"type":"string","description":"Optional. Omit to install the latest published version."}},"required":["module_id"]}"#,
            ),
        ),
    ];
    for (name, description, kind, permission, schema) in core_tools {
        if permits(permission) {
            // module_id "hub" marca tool del CORE: `filter_tools_by_modules` la preserva
            // explícitamente (el core no es un módulo y su ref_id nunca está en el índice).
            // Las tools de core no son destructivas por diseño (lo destructivo del host no se
            // ofrece jamás, y hay un barrido que lo garantiza), así que `normal` explícito.
            tools.push(tool_def(
                name,
                description,
                kind,
                "hub",
                *schema,
                None,
                *kind == "query",
            ));
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
/// ¿Esta operación solo CONTESTA, o puede cambiar lo que el hub guarda? (hub#1594)
///
/// Existe porque preguntarle al asistente «¿qué huecos me quedan el lunes?» sacaba una tarjeta de
/// confirmación: las tres respuestas de disponibilidad de `appointments` están declaradas como
/// *commands* porque un command es la única forma que tiene una operación de cruzar datos de otro
/// módulo (el horario vive en `schedules`), no porque toquen nada.
///
/// 🔴 **Las dos mitades hacen falta, y la del permiso es la que lo hace SEGURO.** Lo estructural
/// —sin `sql`, sin `emit`, sin gate de filas— NO basta: un command de Tier 2 escribe devolviéndole
/// al host una `Operation` que nombra un command hermano, y el core solo ve un `.wasm` compilado.
/// Medido contra el manifest real de `appointments`: `appointments.appointments.bulk_create`
/// («reserva varios huecos de golpe») tampoco declara `sql` ni `emit`, así que una regla solo
/// estructural auto-ejecutaría una RESERVA sin tarjeta. Lo que las separa es el permiso que el
/// módulo exige: una respuesta se paga con un permiso que el módulo también le pide a sus propias
/// queries; la reserva exige `add_appointment`, que ninguna query del módulo pide jamás.
///
/// Y un `risk` declarado gana siempre: una contradicción del manifest se resuelve por el lado
/// seguro, igual que un `risk` desconocido se trata como destructivo.
///
/// No es la puerta de seguridad —esa sigue siendo el `permission` de la operación, revalidado
/// server-side en cada llamada—: decide solo si el usuario ve la tarjeta antes.
fn command_only_answers(
    def: &erplora_runtime::manifest::CommandDef,
    risk: Option<erplora_runtime::manifest::AiRisk>,
    module_read_permissions: Option<&std::collections::HashSet<&str>>,
) -> bool {
    use erplora_runtime::manifest::AiRisk;
    if !matches!(risk, None | Some(AiRisk::Normal)) {
        return false;
    }
    if !def.sql.is_empty()
        || !def.emit.is_empty()
        || def.min_affected_rows.is_some()
        || def.expect_rows.is_some()
    {
        return false;
    }
    module_read_permissions.is_some_and(|perms| perms.contains(def.permission.as_str()))
}

fn tool_def(
    name: &str,
    description: &str,
    kind: &str,
    module_id: &str,
    schema: Option<&str>,
    risk: Option<erplora_runtime::manifest::AiRisk>,
    read_only: bool,
) -> Value {
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
        // Siempre presente, incluso sin declarar: el cliente aplica una política y no puede
        // depender de si alguien se acordó de escribir el campo.
        "risk": risk.unwrap_or(erplora_runtime::manifest::AiRisk::Normal).as_str(),
        // Igual de incondicional (hub#1594): `kind` dice por qué puerta del dispatcher va la
        // llamada, y esto si el usuario tiene que confirmarla antes. Ausente NO puede significar
        // «es una lectura»: el cliente trata la ausencia como escritura.
        "read_only": read_only,
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
         hub. If someone asks about something else — the weather, a film, general trivia — say in \
         ONE SHORT SENTENCE that you only cover their business, and offer something you can \
         actually do here. Do not lecture, do not apologise at length, and do not answer the \
         question anyway: this assistant is metered, and a turn spent on trivia is one the owner \
         paid for and cannot spend on their business.\n\n",
    );

    // The two facts a model can NEVER supply itself, injected per request.
    //
    // The version was the one the QA pass of 2026-08-19 caught worst (hub#1044): asked «what
    // version of ERPlora do I have?», with `v1.1.7` printed in the sidebar of the same screen,
    // it answered that ERPlora HAS no single version and invented a per-module versioning
    // architecture to justify it. There was no path to the answer — no block carried the number
    // and no core tool reads it — and a model with no datum and no permission to say "I don't
    // know" improvises. It comes from the one place that owns it (hub#515), the same number
    // `/readyz` and the sidebar report, so the three cannot drift.
    s.push_str(&format!(
        "## This installation\n\nERPlora version running here: **v{}**. This is THE version of \
         this installation — one number for the whole product, not one per module (installed \
         modules have their own versions on top of it). If asked which version this is, answer \
         with this number.\n\n",
        crate::version::HUB_VERSION
    ));

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
                Some(a) => s.push_str(&format!(
                    "- **{}** (`{}`) — {}\n",
                    m.name, m.id, a.description
                )),
                None => s.push_str(&format!("- **{}** (`{}`)\n", m.name, m.id)),
            }
            // Each tab, with the route the shell actually serves. This is what turns "how do I
            // change a price?" into a real answer instead of an invented menu.
            for nav in &m.navigation {
                s.push_str(&format!("    - {} → `/m/{}/{}`\n", nav.label, m.id, nav.id));
            }
        }
        s.push('\n');
    }

    // What this hub CORRECTS instead of editing (ADR-0331), straight from the manifests.
    //
    // Modules already declare it — `mutable: false` plus a CLOSED `reason` and the commands that
    // correct the record — and the block's own documentation says the vocabulary is closed
    // precisely «so the assistant can explain "an issued invoice is not edited: it is rectified
    // with `invoice.rectify`"». It was wired into the dispatcher and never into the prompt, so
    // the model never saw a single one of these rules. Asked what it could not do, it filled the
    // gap with a policy of its own invention (hub#1042) — which is worse than having no rule,
    // because the user believes it.
    //
    // Only the IMMUTABLE ones are listed: a mutable record needs no explanation, its update tool
    // is already on the table, and a prompt that lists everything stops being read.
    let mut immutable: Vec<(&str, &str, &erplora_runtime::manifest::RecordDef)> = Vec::new();
    for m in registry
        .installed
        .iter()
        .filter(|m| registry.is_active(&m.id))
    {
        for (record, def) in &m.records {
            if !def.mutable {
                immutable.push((m.id.as_str(), record.as_str(), def));
            }
        }
    }
    if !immutable.is_empty() {
        // Deterministic order: a prompt that reshuffles between turns is a prompt whose cache
        // never hits, and a diff nobody can read.
        immutable.sort_by(|a, b| (a.0, a.1).cmp(&(b.0, b.1)));
        s.push_str(
            "## What is corrected here, never edited

These records cannot be edited after              they exist — the module says so itself. Do not offer an edit, do not look for a              tool that does it, and do not invent a reason: say what the record is, why it is              fixed, and name the command that CORRECTS it.

",
        );
        for (module, record, def) in immutable {
            let reason = def.reason.as_deref().unwrap_or("declared immutable");
            if def.correct_with.is_empty() {
                s.push_str(&format!(
                    "- `{module}` · **{record}** — {reason}. No correction tool.\n"
                ));
            } else {
                s.push_str(&format!(
                    "- `{module}` · **{record}** — {reason}. Correct it with: {}\n",
                    def.correct_with
                        .iter()
                        .map(|c| format!("`{c}`"))
                        .collect::<Vec<_>>()
                        .join(", ")
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
         `8` · `8 €` · `8 euros` → **800**. `0,05` · `5 céntimos` → **5**.\n\
         In Spanish (Spain) the currency subunit is «céntimos», never «centavos» — that spelling \
         is Latin American and reads as foreign to this user.\n\n\
         Reading back, do the inverse: an amount of `1250` is presented to the user as 12,50 €. \
         If an amount is ambiguous, ask — a price written wrong by a factor of 100 is a real \
         invoice at the wrong price, and the schema will not catch it.\n\
         This conversion is yours and it applies ONLY when you call a tool. The app's own screens \
         take amounts the way a person writes them: **never tell the user to type cents into a \
         form**. Telling somebody to enter `1700` for 17 € turns a haircut into a 1.700 € one, \
         and the field will accept it.\n\n",
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
         naming the SCREEN from the map above — e.g. the Products screen of the inventory module \
         (`/m/inventory/products`). Never answer with how some other ERP does it.\n\
         - **You know the screens, not the buttons.** The map above gives you routes; it does \
         NOT tell you what controls, fields or wizards live inside a screen. So take the user to \
         the screen and stop there. Do not invent a button, a field label, a numbering scheme or \
         a step-by-step walkthrough of a form you have never seen — a confident recipe that ends \
         at a control that does not exist is worse than «I can take you there, the rest is on \
         screen».\n\
         - **Never answer from memory or from a generic idea of what ERP software does.** If it \
         is not in the map above and no tool covers it, say that this hub does not do it — that \
         is a useful answer; an invented menu is not.\n\
         - **Secrets are not yours to reveal — nor to help extract.** Never explain how to \
         obtain a credential, a token or an API key: not from the developer tools of the \
         browser, not from the network panel, not from a config file. Refusing to say it and \
         then giving the recipe is not a refusal. Say it is not available through you and name \
         the screen where the business manages its own access, if there is one.\n\
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
pub fn translate_sse_line(
    line: &str,
    notes: &std::collections::HashMap<String, Value>,
) -> Option<String> {
    let payload = line.strip_prefix("data:")?.trim();
    if payload.is_empty() {
        return None;
    }
    if payload == "[DONE]" {
        return Some(sse(&json!({ "type": "done" })));
    }

    // El Cloud emite eventos JSON del orquestador. Extraemos el texto incremental para el
    // frame `token` del frontend; `error`/`usage`/`function_call` se reenvían; el resto se ignora.
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
        // The POST-turn counters that close every stream (saas#1540, hub#1183). Forwarded
        // VERBATIM like `error`: they are the SaaS's own numbers and the runtime has no business
        // reinterpreting them. It has to be a FRAME and not the `X-Assistant-Usage` header,
        // because a header is written before the body — on a stream it is always one message
        // behind, so the drawer's counter would lag by a turn forever.
        Some("usage") => Some(sse(&ev)),
        // `function_call`: el bucle del web app ejecuta la op con la sesión del usuario
        // (§9.2). Se anota su `kind` (query/command) desde el catálogo ensamblado, para que
        // el web app sepa si es LECTURA (auto) o ESCRITURA (pide confirmación antes).
        Some("function_call") => {
            let mut out = ev;
            let name = out.get("name").and_then(Value::as_str).map(str::to_string);
            // Todo lo que el catálogo resolvió sobre esta tool viaja CON la llamada: su `kind`
            // (leer sola vs confirmar), su `risk` (hub#1042) y qué argumentos son dinero
            // (hub#1040). El drawer no tiene catálogo propio donde consultarlo, y son hechos del
            // manifest — no cosas que el modelo pueda decir de sí mismo.
            if let Some(note) = name.and_then(|n| notes.get(&n)).and_then(Value::as_object) {
                if let Some(obj) = out.as_object_mut() {
                    for (k, v) in note {
                        obj.insert(k.clone(), v.clone());
                    }
                }
            }
            Some(sse(&out))
        }
        _ => None,
    }
}

/// Lo que el catálogo YA resolvió sobre cada tool, para anotar los eventos `function_call` que
/// reenviamos. El drawer no tiene catálogo propio donde consultarlo, y nada de esto puede venir
/// del modelo — son hechos del manifest:
///
///   · `kind`         — por qué puerta del dispatcher va la llamada (query/command).
///   · `read_only`    — si el usuario tiene que confirmarla antes (hub#1594).
///   · `risk`         — cuánto daño hace la operación (hub#1042).
///   · `money_fields` — qué argumentos son dinero, para que la tarjeta enseñe «15,00 €» y no
///                      `price_cents: 1500` (hub#1040): el único punto donde un humano puede
///                      cazar un ×100, y el único del producto donde no salía en euros.
pub(crate) fn tool_notes(tools: &[Value]) -> std::collections::HashMap<String, Value> {
    tools
        .iter()
        .filter_map(|t| {
            let name = t.get("name").and_then(Value::as_str)?;
            let mut note = serde_json::Map::new();
            if let Some(kind) = t.get("kind").and_then(Value::as_str) {
                note.insert("kind".to_string(), json!(kind));
            }
            if let Some(risk) = t.get("risk").and_then(Value::as_str) {
                note.insert("risk".to_string(), json!(risk));
            }
            // Incondicional a propósito (hub#1594): el drawer no puede leer una ausencia como
            // «es una lectura» — un `false` explícito es lo que mantiene la tarjeta.
            if let Some(read_only) = t.get("read_only").and_then(Value::as_bool) {
                note.insert("read_only".to_string(), json!(read_only));
            }
            let money = t
                .get("parameters")
                .map(|p| money_fields(&p.to_string()))
                .unwrap_or_default();
            if !money.is_empty() {
                note.insert("money_fields".to_string(), json!(money));
            }
            if note.is_empty() {
                return None;
            }
            Some((name.to_string(), Value::Object(note)))
        })
        .collect()
}

/// Qué argumentos de un command son DINERO, leído de su JSON Schema (hub#1040).
///
/// La tarjeta de confirmación es el último sitio donde un humano puede cazar un error de ×100, y
/// era el único del producto donde el importe no salía en euros. Para pintarlo bien hay que saber
/// QUÉ campo es dinero — y eso no se adivina por el nombre: el día que un porcentaje se pinte como
/// importe, la tarjeta pasa de ilegible a mentirosa.
///
/// Quien lo sabe es el schema del propio command, que enuncia el contrato del dinero en la
/// descripción del campo (ADR-0123: «Minor units of the hub currency», «Céntimos por hora»). El
/// runtime lo resuelve una vez y manda la respuesta con la tool call.
///
/// **Conservador a propósito**: exige TIPO entero **y** marca explícita. No detectar un campo de
/// dinero deja un entero crudo —lo que ya pasa hoy, solo poco útil—; detectar uno de más se
/// inventa un importe.
pub(crate) fn money_fields(schema: &str) -> Vec<String> {
    /// Las formas en que un schema publicado dice «esto es dinero». Ambos idiomas: los manifests
    /// se escriben en inglés, pero las descripciones viejas siguen en castellano.
    const MARKERS: &[&str] = &["minor unit", "céntimo", "centimo", "adr-0123"];

    let Ok(parsed) = serde_json::from_str::<Value>(schema) else {
        return Vec::new();
    };
    let Some(props) = parsed.get("properties").and_then(Value::as_object) else {
        return Vec::new();
    };

    props
        .iter()
        .filter(|(_, def)| {
            // El tipo puede ser `"integer"` o `["integer","null"]` (opcional en el manifest).
            let is_integer = match def.get("type") {
                Some(Value::String(t)) => t == "integer",
                Some(Value::Array(ts)) => ts.iter().any(|t| t.as_str() == Some("integer")),
                _ => false,
            };
            if !is_integer {
                return false;
            }
            let desc = def
                .get("description")
                .and_then(Value::as_str)
                .unwrap_or("")
                .to_lowercase();
            MARKERS.iter().any(|m| desc.contains(m))
        })
        .map(|(name, _)| name.clone())
        .collect()
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

    /// Same, plus the `records` block a module uses to declare what is corrected and never
    /// edited (ADR-0331). Deserialized like the rest, so it exercises the real parse.
    fn manifest_with_records(
        id: &str,
        name: &str,
        records: Value,
    ) -> erplora_runtime::manifest::Manifest {
        let m = json!({ "id": id, "name": name, "version": "1.0.0", "records": records });
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

    /// ADR-0331 gave every module a way to say what of its data is CORRECTED and never edited,
    /// with a CLOSED `reason` vocabulary. The block's own doc says why the vocabulary is closed:
    /// «so the assistant can explain "an issued invoice is not edited: it is rectified with
    /// `invoice.rectify`"». It was wired into the dispatcher and never into the assistant, so
    /// the model never saw it — and when asked what it could not do, it INVENTED a policy
    /// instead (hub#1042: «bulk_delete no existe, está deshabilitada intencionalmente», one turn
    /// after listing it among its own tools).
    ///
    /// A model that is told the real rule does not have to make one up.
    #[test]
    fn instructions_carry_what_each_module_declares_immutable() {
        let mut reg = Registry::new();
        reg.installed.push(manifest_with_records(
            "invoice",
            "Invoicing",
            json!({ "invoice": { "mutable": false, "reason": "fiscal",
                                 "correct_with": ["invoice.rectify"] } }),
        ));
        reg.status.insert(
            "invoice".to_string(),
            erplora_runtime::registry::ModuleStatus::Active,
        );

        let ins = build_instructions(&reg, &[], "2026-08-19T14:30:00Z (Tuesday)");

        assert!(
            ins.contains("invoice.rectify"),
            "the correction door must be named: {ins}"
        );
        let lower = ins.to_lowercase();
        assert!(
            lower.contains("fiscal"),
            "the closed reason must travel: {ins}"
        );
    }

    /// A record the module declares MUTABLE says nothing worth a line in the prompt: the tools
    /// already cover editing it. Only the refusals need explaining, and a prompt that lists
    /// everything stops being read.
    #[test]
    fn a_mutable_record_does_not_crowd_the_prompt() {
        let mut reg = Registry::new();
        reg.installed.push(manifest_with_records(
            "sales",
            "Sales",
            json!({ "order": { "mutable": true, "update": "sales.order.update_line" } }),
        ));
        reg.status.insert(
            "sales".to_string(),
            erplora_runtime::registry::ModuleStatus::Active,
        );

        let ins = build_instructions(&reg, &[], "2026-08-19T14:30:00Z (Tuesday)");

        // The SECTION itself must not appear: asserting on the update command's name would pass
        // even while the record leaked in, because the rendering never prints that command. (It
        // did exactly that until a deliberate sabotage — removing the `!def.mutable` filter —
        // failed to turn this test red.)
        assert!(
            !ins.contains("corrected here, never edited"),
            "with nothing immutable there is no section to write: {ins}"
        );
        assert!(
            !ins.contains("**order**"),
            "a mutable record needs no rule: the tool already covers it: {ins}"
        );
    }

    /// An INACTIVE module's refusals are not this hub's refusals.
    #[test]
    fn an_inactive_module_declares_nothing_to_the_assistant() {
        let mut reg = Registry::new();
        reg.installed.push(manifest_with_records(
            "invoice",
            "Invoicing",
            json!({ "invoice": { "mutable": false, "reason": "fiscal",
                                 "correct_with": ["invoice.rectify"] } }),
        ));
        reg.status.insert(
            "invoice".to_string(),
            erplora_runtime::registry::ModuleStatus::Inactive,
        );

        let ins = build_instructions(&reg, &[], "2026-08-19T14:30:00Z (Tuesday)");

        assert!(
            !ins.contains("invoice.rectify"),
            "an inactive module says nothing: {ins}"
        );
    }

    /// Which arguments of a command are MONEY (hub#1040).
    ///
    /// The confirm card showed `{"price_cents": 1500}` and the owner approved it without ever
    /// reading «15,00 €» — in the one place a human could have caught a ×100, and the only place
    /// in the product where an amount was not shown in euros.
    ///
    /// The client must NOT guess this from field names: the day a percentage gets painted as an
    /// amount, the card starts lying instead of just being unreadable. Who knows is the command's
    /// JSON Schema, which states the money contract in the field's own description (ADR-0123:
    /// «Minor units of the hub currency», «Céntimos por hora»). The runtime resolves it once and
    /// sends the answer.
    ///
    /// Conservative on purpose: missing a money field shows a raw integer (what happens today,
    /// merely unhelpful); a false positive invents an amount. So it demands BOTH an integer type
    /// and an explicit marker.
    #[test]
    fn money_fields_are_read_from_the_schema_never_guessed_from_the_name() {
        let schema = r#"{
            "type": "object",
            "properties": {
                "price": { "type": ["integer","null"],
                           "description": "Minor units of the hub currency (ADR-0007/0123): 1500 = 15,00 €" },
                "hourly_rate": { "type": "integer", "description": "Céntimos por hora (dinero, ADR-0123)" },
                "duration_minutes": { "type": "integer",
                                      "description": "A service takes time: 0 or negative is not a duration." },
                "commission_rate": { "type": "number", "description": "Porcentaje de comisión (ADR-0123 no aplica)" },
                "name": { "type": "string" }
            }
        }"#;

        let mut fields = money_fields(schema);
        fields.sort();

        assert_eq!(
            fields,
            vec!["hourly_rate".to_string(), "price".to_string()],
            "solo los enteros que el schema MARCA como dinero"
        );
    }

    /// A schema that is absent, empty or unparseable marks nothing. Falling back to «no money»
    /// is the safe direction: the card shows raw integers, exactly as it does today.
    #[test]
    fn an_unreadable_schema_marks_nothing_as_money() {
        assert!(money_fields("{not json").is_empty());
        assert!(money_fields("{}").is_empty());
    }

    /// En España la subunidad son **céntimos**; «centavos» es LatAm. El prompt ya usa la palabra
    /// correcta en sus ejemplos, pero el modelo derivó a «centavos enteros» en una respuesta real
    /// (hub#1043). Basta con decirlo, porque es una preferencia de vocabulario y no un contrato —
    /// pero hay que decirlo, o se vuelve a derivar.
    #[test]
    fn instructions_name_the_currency_subunit_as_spain_says_it() {
        let ins = build_instructions(&Registry::new(), &[], "2026-08-19T14:30:00Z (Tuesday)");
        let lower = ins.to_lowercase();
        assert!(
            lower.contains("céntimo"),
            "la palabra correcta tiene que estar: {ins}"
        );
        assert!(
            lower.contains("never «centavos»") || lower.contains("not «centavos»"),
            "y hay que decir explícitamente cuál NO es, o el modelo vuelve a derivar: {ins}"
        );
    }

    /// Aplicar una plantilla NO configura lo fiscal, y decirlo por escrito importa porque el
    /// modelo lo afirmó con el banner rojo «Todavía no puedes facturar» visible en la misma
    /// pantalla (hub#1041). El resultado de la tool ya trae lo que sigue bloqueando; esto es la
    /// otra mitad: que sepa qué hacer con ese campo en vez de adornarlo.
    #[test]
    fn the_blueprint_tool_says_it_does_not_configure_the_fiscal_side() {
        // Va en la DESCRIPCIÓN de la tool, no en el prompt general: es donde el modelo la lee
        // justo antes de usarla, y donde ya vive el resto del contrato de esta acción.
        let ctx = RequestContext::new("h1", "u1", ["*".to_string()]);
        let tools = assemble_tools(&Registry::new(), &ctx);
        let apply = tools
            .iter()
            .find(|t| t["name"] == json!("hub.blueprints.apply"))
            .expect("la tool de blueprints se ofrece");
        let desc = apply["description"].as_str().unwrap_or("").to_lowercase();

        assert!(
            desc.contains("still_blocking"),
            "el campo que trae la verdad tiene que nombrarse: {desc}"
        );
        // Nombrar el campo no basta: hay que decir QUÉ hacer con él. Sin estas dos, la
        // descripción podía perder la regla entera y el test seguía en verde — comprobado
        // saboteándolo (`fiscal` ya aparecía antes en «fiscal identity», así que era vacuo).
        assert!(
            desc.contains("does not set up the fiscal side"),
            "tiene que decir que la plantilla NO deja lo fiscal hecho: {desc}"
        );
        assert!(
            desc.contains("as pending") && desc.contains("never say invoicing is ready"),
            "y que esos ítems se transmiten como PENDIENTES, sin declarar que ya se puede \
             facturar: {desc}"
        );
    }

    /// El prompt PEDÍA lo que el modelo no puede saber: «naming the screen **and the steps in
    /// it**». El asistente no tiene mapa de los botones ni de los campos de una pantalla —solo de
    /// las RUTAS— así que esa frase le encargaba inventar, y lo hizo: un recorrido completo para
    /// la factura rectificativa con un botón «Rectificar» que no existe, tres tipos de
    /// rectificación, un sufijo `-R1` y un icono 🔄 (hub#1047). Y en hub#1045, «haz clic en el
    /// nombre del servicio» sobre una lista que no abre ninguna ficha así.
    ///
    /// La frontera honesta es la que el hub puede sostener: sé en qué PANTALLA se hace, no qué
    /// botón hay dentro.
    #[test]
    fn instructions_do_not_ask_for_steps_the_assistant_cannot_know() {
        let ins = build_instructions(&Registry::new(), &[], "2026-08-19T14:30:00Z (Tuesday)");
        let lower = ins.to_lowercase();
        assert!(
            !lower.contains("and the steps in it"),
            "el prompt no puede encargar los pasos de dentro de una pantalla: {ins}"
        );
        assert!(
            lower.contains("you know the screens, not the buttons"),
            "y tiene que decir dónde está la frontera: {ins}"
        );
    }

    /// El contrato de céntimos es de los ARGUMENTOS DE TOOL, no de los formularios. El modelo lo
    /// generalizó y mandó teclear «1700 — no 17.00 ni 1700,00» en la pantalla, con el énfasis
    /// puesto justo para vencer la duda que habría salvado al usuario (hub#1045). Un corte de
    /// pelo de 17 € quedaría a 1.700 €.
    #[test]
    fn the_cents_contract_is_scoped_to_tool_arguments() {
        let ins = build_instructions(&Registry::new(), &[], "2026-08-19T14:30:00Z (Tuesday)");
        let lower = ins.to_lowercase();
        assert!(
            lower.contains("only when you call a tool"),
            "hay que acotar la regla a las tools: {ins}"
        );
        assert!(
            lower.contains("never tell the user to type cents"),
            "y prohibir explícitamente mandarlo teclear en pantalla: {ins}"
        );
    }

    /// No filtró credenciales —bien— pero enseñó a EXTRAERLAS: F12 → Network → cabeceras, paso a
    /// paso (hub#1048). Una negativa que se anula a sí misma: cualquiera que consiga que el dueño
    /// siga esos pasos obtiene el secreto sin que el asistente lo haya revelado. Y encima la
    /// receta era falsa (el `X-Hub-Token` nunca llega al navegador, ADR-0003), así que el usuario
    /// se queda convencido de que algo va mal en su hub.
    #[test]
    fn instructions_forbid_teaching_how_to_extract_a_credential() {
        let ins = build_instructions(&Registry::new(), &[], "2026-08-19T14:30:00Z (Tuesday)");
        let lower = ins.to_lowercase();
        assert!(
            lower.contains("never explain how to obtain") && lower.contains("credential"),
            "no basta con no revelarlas: hay que prohibir explicar cómo sacarlas: {ins}"
        );
        assert!(
            lower.contains("developer tools") || lower.contains("devtools"),
            "y nombrar la vía concreta que usó, o la regla se lee como abstracta: {ins}"
        );
    }

    /// El alcance lo decidió el MERCADO (skill `market-decision`, 8 referencias en hub#1046), y
    /// coincide sin fisuras: BC lo dice verbatim —«Chat is designed for enterprise use and
    /// answering questions that relate to Business Central and the business data it contains»—,
    /// Odoo «operates exclusively within business data context», Sidekick vive dentro del admin
    /// de Shopify, y Fin trata la AUSENCIA de guardarraíles de alcance como su modo de fallo
    /// conocido.
    ///
    /// Aquí la puerta la abría la propia coletilla del prompt: «unless the user plainly says
    /// otherwise». Pedir una película *es* decir otra cosa, así que no había barrera ninguna — y
    /// una respuesta así gasta uno de los 30 mensajes/mes del plan gratuito (~23k tokens) del
    /// cliente, en conocimiento del modelo que nadie ha verificado.
    #[test]
    fn the_scope_is_the_business_and_the_loophole_is_closed() {
        let ins = build_instructions(&Registry::new(), &[], "2026-08-19T14:30:00Z (Tuesday)");
        let lower = ins.to_lowercase();

        assert!(
            !lower.contains("unless the user plainly says otherwise"),
            "esa coletilla es la puerta por la que se cuela todo: {ins}"
        );
        assert!(
            lower.contains("not a general-purpose"),
            "el alcance tiene que seguir enunciado: {ins}"
        );
    }

    /// Y cómo se dice importa tanto como el límite. El mercado no cierra en seco: Fin ESCALA en
    /// vez de dejar que el bot «intente y rechace», y Copilot Studio tiene un `fallback topic`
    /// para lo de fuera. Una negativa seca en un producto que el cliente paga se lee como avería.
    #[test]
    fn out_of_scope_is_redirected_briefly_not_lectured() {
        let ins = build_instructions(&Registry::new(), &[], "2026-08-19T14:30:00Z (Tuesday)");
        let lower = ins.to_lowercase();
        assert!(
            lower.contains("one short sentence"),
            "hay que acotar la longitud, o el redirect se vuelve un sermón: {ins}"
        );
        assert!(
            lower.contains("do not lecture") || lower.contains("without lecturing"),
            "y decir explícitamente que no se sermonea: {ins}"
        );
    }

    /// The keystone: the turn reaching the Cloud must carry a system prompt that says WHAT
    /// ERPlora is and WHICH modules this hub runs. Without it the model is a generic chatbot
    /// that answers "which system do you mean?" — the Cloud inserts `instructions or ""` as
    /// the system message (`history.prepare_client_messages`), so an absent field is an EMPTY
    /// system prompt, not a default one.
    #[test]
    fn instructions_identify_erplora_and_list_active_modules() {
        let reg = registry_with(&[
            (
                "inventory",
                "Inventory",
                Some("Product catalog and basic stock control"),
                true,
            ),
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
        assert!(
            !ins.contains("Kitchen order display"),
            "inactive module leaked: {ins}"
        );
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
            setup["description"]
                .as_str()
                .unwrap_or("")
                .to_lowercase()
                .contains("configur"),
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

        let install = tools
            .iter()
            .find(|t| t["name"] == "hub.modules.install")
            .expect("install must be offered to an admin");
        assert_eq!(
            install["kind"], "command",
            "a mutation: the confirm-card gates it"
        );
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
        assert!(
            !names.contains(&"hub.modules.install"),
            "a non-admin must not see install: {names:?}"
        );
    }

    /// hub#631 steps 2-3: the guided flow «I have a restaurant in Madrid, set it up for me» needs
    /// the sector templates. `hub.blueprints.list` is a read (the SaaS catalogue); apply is the
    /// strong mutation and lives in its own test below.
    #[test]
    fn assemble_tools_offers_blueprints_list_and_apply_to_an_admin() {
        let ctx = RequestContext::new("h1", "u1", ["*".to_string()]);
        let tools = assemble_tools(&Registry::new(), &ctx);

        let list = tools
            .iter()
            .find(|t| t["name"] == "hub.blueprints.list")
            .expect("blueprints.list must be offered on an empty hub — templates are its way out");
        assert_eq!(list["kind"], "query", "a read: auto-run, no confirm-card");

        let apply = tools
            .iter()
            .find(|t| t["name"] == "hub.blueprints.apply")
            .expect("blueprints.apply must be offered to an admin");
        assert_eq!(
            apply["kind"], "command",
            "a mutation: the confirm-card gates it"
        );
        assert_eq!(apply["parameters"]["required"][0], "slug");
    }

    /// The precondition hub#631 fixed before exposing apply: is `/api/hub/import` on a hub WITH
    /// data destructive or additive? Verified additive — the import SQL subset is INSERT-only
    /// (`import_sql.rs`: no UPDATE/DELETE/DDL, no `ON CONFLICT DO UPDATE`, no DML CTEs) and every
    /// row is guarded by `NOT EXISTS` on the technical id AND the destination's natural keys
    /// (ADR-0304): an existing row is SKIPPED, never merged or overwritten. The confirm-card can
    /// only tell the owner that if the tool's description says it, so the description is contract.
    #[test]
    fn blueprints_apply_describes_the_verified_additive_semantics() {
        let ctx = RequestContext::new("h1", "u1", ["*".to_string()]);
        let tools = assemble_tools(&Registry::new(), &ctx);
        let apply = tools
            .iter()
            .find(|t| t["name"] == "hub.blueprints.apply")
            .expect("apply must be offered to an admin");
        let desc = apply["description"].as_str().unwrap_or("").to_lowercase();
        assert!(
            desc.contains("additive"),
            "must state the verified semantics: {desc}"
        );
        assert!(
            desc.contains("never") && (desc.contains("overwrit") || desc.contains("delet")),
            "must promise existing data is kept: {desc}"
        );
    }

    /// Same permission line as install: applying a template is administration. A cashier keeps
    /// the read (list mutates nothing) and never sees apply.
    #[test]
    fn blueprints_apply_is_not_offered_without_the_admin_permission() {
        let ctx = RequestContext::new("h1", "u1", ["hub.users.view".to_string()]);
        let tools = assemble_tools(&Registry::new(), &ctx);
        let names: Vec<&str> = tools.iter().filter_map(|t| t["name"].as_str()).collect();
        assert!(names.contains(&"hub.blueprints.list"));
        assert!(
            !names.contains(&"hub.blueprints.apply"),
            "a non-admin must not see apply: {names:?}"
        );
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
                !name.contains("uninstall")
                    && !name.contains("reset")
                    && !name.contains("purge")
                    && !name.contains("delete"),
                "destructive host tool offered: {name}"
            );
        }
    }

    /// The sweep above runs over `Registry::new()` — EMPTY — so it only ever constrained the
    /// five core tools. Every destructive command of every MODULE walked straight past it: the
    /// QA pass of 2026-08-19 counted 26 of them offered to the assistant, `bulk_delete` among
    /// them (hub#1042, appointments#62). Nothing was deleted that day, but by the model's
    /// judgement, not by a lock — and the same session had it claim, falsely, that a lock
    /// existed.
    ///
    /// A test that cannot fail is not a guarantee. This one runs over a LOADED registry and pins
    /// the channel that makes a lock possible at all: a module DECLARES how dangerous an
    /// operation is (`ai.risk`), and the core carries that declaration to the client instead of
    /// guessing from a name it does not parse.
    ///
    /// The core deliberately does NOT infer risk from the name. `delete` in a name means nothing
    /// portable — `sales.void` is destructive and says neither — and a core that guessed would be
    /// deciding for the module what its own data is worth. The module knows; it declares.
    #[test]
    fn a_destructive_module_tool_must_declare_its_risk() {
        let mut reg = Registry::new();
        let m: erplora_runtime::manifest::Manifest = serde_json::from_value(json!({
            "id": "appointments", "name": "Appointments", "version": "1.0.0",
            "commands": {
                "appointments.appointments.create": {
                    "permission": "appointments.add_appointment",
                    "ai": { "description": "Books an appointment." }
                },
                "appointments.appointments.bulk_delete": {
                    "permission": "appointments.delete_appointment",
                    "ai": { "description": "Permanently deletes multiple appointments in bulk.",
                            "risk": "bulk_destructive" }
                }
            }
        }))
        .expect("fixture manifest must parse");
        reg.installed.push(m.clone());
        for (name, def) in &m.commands {
            reg.commands.insert(
                name.clone(),
                erplora_runtime::registry::RegisteredCommand {
                    module_id: "appointments".to_string(),
                    def: def.clone(),
                    sql: Vec::new(),
                    wasm: None,
                    schema: None,
                },
            );
        }
        reg.status.insert(
            "appointments".to_string(),
            erplora_runtime::registry::ModuleStatus::Active,
        );

        let ctx = RequestContext::new("h1", "u1", ["*".to_string()]);
        let tools = assemble_tools(&reg, &ctx);

        let destructive = tools
            .iter()
            .find(|t| t["name"] == json!("appointments.appointments.bulk_delete"))
            .expect("the tool is offered — that is the point");
        assert_eq!(
            destructive["risk"],
            json!("bulk_destructive"),
            "a destructive tool must carry its declared risk to the client: {destructive}"
        );

        let ordinary = tools
            .iter()
            .find(|t| t["name"] == json!("appointments.appointments.create"))
            .expect("the create tool is offered");
        assert_eq!(
            ordinary["risk"],
            json!("normal"),
            "an ordinary tool is `normal`, stated rather than absent: {ordinary}"
        );
    }

    /// **hub#1594.** Asking the assistant «what slots do I have free on Monday?» pushed a
    /// confirmation card at the user: the answer to a QUESTION was gated behind «accept» before it
    /// would even be read out. The three availability answers of `appointments` are declared as
    /// *commands* only because a command is the one shape that can cross another module's data
    /// (the opening hours live in `schedules`) — not because they change anything.
    ///
    /// So the catalogue states, per tool, whether running it can change what the hub holds. The
    /// client uses it to skip the card on a read; it is NOT the security gate, which stays the
    /// operation's own `permission`, revalidated server-side on every call.
    ///
    /// 🔴 **The half that makes this safe is the permission.** A structural reading alone —
    /// «no SQL and no events, therefore a read» — is WRONG and dangerous here, because a Tier-2
    /// command writes by handing the host an `Operation` naming a sibling command, and the core
    /// only ever sees a compiled `.wasm`. Measured against the real manifest of `appointments`:
    /// `appointments.appointments.bulk_create` («books several slots at once») declares no `sql`
    /// and no `emit` either, so a structural rule would auto-run a BOOKING with no card. What
    /// separates the two is what the module asks the user to hold: an answer costs only a
    /// permission the module also grants to its own queries; the booking demands
    /// `add_appointment`, which no query of the module ever requires.
    #[test]
    fn a_command_that_only_answers_is_offered_as_a_read_and_a_writer_is_not() {
        let mut reg = Registry::new();
        let m: erplora_runtime::manifest::Manifest = serde_json::from_value(json!({
            "id": "appointments", "name": "Appointments", "version": "1.0.0",
            "queries": {
                // The module's own read door: this is what "a read permission of this module" means.
                "appointments.availability.own_slots": {
                    "permission": "appointments.view_schedule",
                    "sql": "queries/own_slots.sql"
                }
            },
            "commands": {
                // The three shapes that must come out as READS: a handler that only computes.
                "appointments.availability.slots": {
                    "permission": "appointments.view_schedule",
                    "handler": { "type": "wasm", "file": "dist/handler.wasm", "function": "available_slots" },
                    "ai": { "description": "Lists the free booking slots of a given date." }
                },
                // The trap: structurally identical (no sql, no emit, a WASM handler) and it BOOKS.
                "appointments.appointments.bulk_create": {
                    "permission": "appointments.add_appointment",
                    "handler": { "type": "wasm", "file": "dist/handler.wasm", "function": "bulk_create" },
                    "ai": { "description": "Books several slots at once for the same customer." }
                },
                // A writer that shares the read permission but declares what it does: still a write.
                "appointments.availability.touch": {
                    "permission": "appointments.view_schedule",
                    "sql": ["commands/touch.sql"],
                    "emit": ["appointments.availability.touched"],
                    "ai": { "description": "Writes something while asking only for the read permission." }
                },
                // Declaring a risk contradicts «read»; the safe side wins without arguing.
                "appointments.availability.purge": {
                    "permission": "appointments.view_schedule",
                    "handler": { "type": "wasm", "file": "dist/handler.wasm", "function": "purge" },
                    "ai": { "description": "Says it only reads but declares a destructive risk.",
                            "risk": "destructive" }
                }
            }
        }))
        .expect("fixture manifest must parse");
        reg.installed.push(m.clone());
        for (name, def) in &m.queries {
            reg.queries.insert(
                name.clone(),
                erplora_runtime::registry::RegisteredQuery {
                    module_id: "appointments".to_string(),
                    def: def.clone(),
                    sql: "SELECT 1".to_string(),
                    schema: None,
                },
            );
        }
        for (name, def) in &m.commands {
            reg.commands.insert(
                name.clone(),
                erplora_runtime::registry::RegisteredCommand {
                    module_id: "appointments".to_string(),
                    def: def.clone(),
                    sql: Vec::new(),
                    wasm: None,
                    schema: None,
                },
            );
        }
        reg.status.insert(
            "appointments".to_string(),
            erplora_runtime::registry::ModuleStatus::Active,
        );

        let ctx = RequestContext::new("h1", "u1", ["*".to_string()]);
        let tools = assemble_tools(&reg, &ctx);
        let find = |name: &str| {
            tools
                .iter()
                .find(|t| t["name"] == json!(name))
                .unwrap_or_else(|| panic!("tool `{name}` must be offered — that is the point"))
                .clone()
        };

        // A question answers itself: no card.
        let slots = find("appointments.availability.slots");
        assert_eq!(
            slots["read_only"],
            json!(true),
            "an answer must not be gated behind a confirmation card: {slots}"
        );
        // …and it is still dispatched as the command it is: `kind` picks the door, not the card.
        assert_eq!(
            slots["kind"],
            json!("command"),
            "a read-only command is still executed through the command dispatcher: {slots}"
        );

        // The positive the control has to catch, both ways.
        for name in [
            "appointments.appointments.bulk_create",
            "appointments.availability.touch",
            "appointments.availability.purge",
        ] {
            let tool = find(name);
            assert_eq!(
                tool["read_only"],
                json!(false),
                "`{name}` changes what the hub holds: it keeps its confirmation card: {tool}"
            );
        }

        // Always stated, never absent: the client applies a policy and cannot depend on whether
        // somebody remembered to write the field (same contract as `risk`).
        for tool in &tools {
            assert!(
                tool["read_only"].is_boolean(),
                "every tool states whether it only reads: {tool}"
            );
        }
    }

    /// A query is a read by construction — the field says so instead of leaving the client to
    /// re-derive it from `kind`, which is about which dispatcher door to use.
    #[test]
    fn a_query_is_always_offered_as_a_read() {
        let ctx = RequestContext::new("h1", "u1", ["*".to_string()]);
        let tools = assemble_tools(&Registry::new(), &ctx);
        let setup = tools
            .iter()
            .find(|t| t["name"] == json!("hub.setup.status"))
            .expect("the core query is offered");
        assert_eq!(setup["read_only"], json!(true), "{setup}");

        // And the core's own writers keep their card: installing is not a question.
        for name in ["hub.modules.install", "hub.blueprints.apply"] {
            let tool = tools
                .iter()
                .find(|t| t["name"] == json!(name))
                .expect("the core command is offered to an admin");
            assert_eq!(
                tool["read_only"],
                json!(false),
                "`{name}` mutates the hub: it keeps its confirmation card: {tool}"
            );
        }
    }

    /// The note the drawer reads is built from the catalogue, and `read_only` has to be IN it
    /// (hub#1594): `translate_sse_line` copies the note verbatim, so a field the note never
    /// carries is a field the confirmation card never sees — and every command would keep asking.
    #[test]
    fn the_note_carries_whether_the_tool_only_reads() {
        let notes = tool_notes(&[
            json!({ "name": "appointments.availability.slots", "kind": "command",
                    "risk": "normal", "read_only": true }),
            json!({ "name": "appointments.appointments.create", "kind": "command",
                    "risk": "normal", "read_only": false }),
        ]);
        assert_eq!(
            notes["appointments.availability.slots"]["read_only"],
            json!(true),
            "a read must reach the drawer as a read: {notes:?}"
        );
        assert_eq!(
            notes["appointments.appointments.create"]["read_only"],
            json!(false),
            "a write must reach the drawer as a write, stated rather than absent: {notes:?}"
        );
    }

    /// The tag has to travel WITH the call, like `kind` and `risk` (hub#1042): the drawer has no
    /// catalogue of its own to look it up in.
    #[test]
    fn translate_annotates_read_only() {
        let mut notes = std::collections::HashMap::new();
        notes.insert(
            "appointments.availability.slots".to_string(),
            json!({ "kind": "command", "read_only": true }),
        );
        let line = r#"data: {"type":"function_call","name":"appointments.availability.slots","call_id":"c1","arguments":"{}"}"#;
        let out = translate_sse_line(line, &notes).expect("forwarded");
        assert!(out.contains("\"read_only\":true"), "{out}");
    }

    /// The policy line itself travels in the prompt: the model must know destructive actions are
    /// off the table BY DESIGN — so it explains honestly («eso lo haces tú desde la pantalla»)
    /// instead of inventing a security policy, which is exactly the failure this session caught.
    #[test]
    fn instructions_state_that_destructive_actions_belong_to_the_user() {
        let ins = build_instructions(&Registry::new(), &[], "2026-08-09T14:30:00Z (Sunday)");
        let lower = ins.to_lowercase();
        assert!(
            lower.contains("destructive"),
            "the destructive-actions rule must be stated: {ins}"
        );
        assert!(
            lower.contains("uninstall"),
            "with its concrete examples: {ins}"
        );
    }

    /// The money contract (ADR-0123) is a HUB-WIDE invariant, so it belongs in the system prompt
    /// and not in each module's schema: every amount the runtime accepts is an **integer of
    /// cents**. The JSON Schemas only say `{"type":"integer","minimum":0}` — nothing there tells
    /// the model that 12.50 € is `1250`, and `12` validates perfectly while meaning 0.12 €. The
    /// user writes the price however they speak it ("12,50", "12.50", "12 euros 50"); converting
    /// that to cents is the assistant's job, and it has to be told so.
    #[test]
    /// «What version of ERPlora do I have?» is one of the most basic identity questions an ERP
    /// gets, and the assistant had NO path to it: no block of the prompt carried the number and
    /// none of the five core tools reads it. So the model improvised — and improvised an
    /// ARCHITECTURE: «ERPlora has no single global version», while `v1.1.7` was printed in the
    /// sidebar of the very same screen (hub#1044).
    ///
    /// The number is not a fact a model can hold: it changes with every release. It is injected,
    /// like the date, from the one place that owns it (`crate::version::HUB_VERSION`, hub#515).
    #[test]
    fn instructions_state_the_version_this_hub_is_running() {
        let ins = build_instructions(&Registry::new(), &[], "2026-08-09T14:30:00Z (Sunday)");
        assert!(
            ins.contains(crate::version::HUB_VERSION),
            "the running version must be in the prompt, from the single source (hub#515): {ins}"
        );
    }

    /// Knowing the number is half of it. The model also has to be told the number is THE hub's,
    /// so it stops answering the question with a lecture about per-module versioning.
    #[test]
    fn the_version_is_presented_as_this_hub_s_own() {
        let ins = build_instructions(&Registry::new(), &[], "2026-08-09T14:30:00Z (Sunday)");
        let lower = ins.to_lowercase();
        assert!(
            lower.contains("version"),
            "the version has to be named as such, not left as a bare number: {ins}"
        );
    }

    fn instructions_state_the_money_contract_in_cents() {
        let ins = build_instructions(&Registry::new(), &[], "2026-08-09T14:30:00Z (Sunday)");
        let lower = ins.to_lowercase();
        assert!(
            lower.contains("cent"),
            "the money contract must be stated: {ins}"
        );
        // The worked example is what makes it stick — a rule without one is re-derived wrong.
        assert!(
            ins.contains("1250"),
            "state the conversion with an example (12.50 -> 1250): {ins}"
        );
        // And it must be explicit that a decimal is never sent on the wire.
        assert!(
            lower.contains("never send")
                || lower.contains("not a decimal")
                || lower.contains("no decimal"),
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
        reg.installed
            .push(serde_json::from_value(m).expect("manifest parses"));
        reg.status.insert("inventory".into(), ModuleStatus::Active);

        let ins = build_instructions(&reg, &[], "2026-08-09T14:30:00Z (Sunday)");
        assert!(ins.contains("Products"), "nav label missing: {ins}");
        assert!(
            ins.contains("/m/inventory/products"),
            "the real route the shell serves must be there: {ins}"
        );
        assert!(
            ins.contains("/m/inventory/movements"),
            "every tab, not just the first: {ins}"
        );
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
        assert!(
            ins.contains("ERPlora"),
            "must name the product even with no modules: {ins}"
        );
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
        let ins = build_instructions(
            &Registry::new(),
            &[briefing.to_string()],
            "2026-08-09T14:30:00Z (Sunday)",
        );
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
        let ins = build_instructions(
            &Registry::new(),
            &client_system_messages(&fe),
            "2026-08-09T14:30:00Z (Sunday)",
        );
        let body = build_cloud_body(&fe, vec![], None, &ins);

        assert!(
            body["instructions"]
                .as_str()
                .unwrap_or("")
                .contains("ERPlora"),
            "instructions must reach the Cloud: {body}"
        );
        assert!(
            body["instructions"]
                .as_str()
                .unwrap_or("")
                .contains("SETUP BRIEFING"),
            "the briefing must reach the Cloud: {body}"
        );
        let roles: Vec<&str> = body["messages"]
            .as_array()
            .unwrap()
            .iter()
            .filter_map(|m| m.get("role").and_then(Value::as_str))
            .collect();
        assert_eq!(
            roles,
            vec!["user"],
            "client `system` turns must be stripped: {body}"
        );
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
        let out =
            translate_sse_line(line, &kinds).expect("function_call must be forwarded, not dropped");
        assert!(out.contains("function_call"));
        assert!(out.contains("inventory.products.list"));
        assert!(out.contains("c1"));
    }

    #[test]
    fn translate_annotates_function_call_kind() {
        // The web app auto-runs reads (query) but must CONFIRM writes (command); the
        // runtime tags each function_call with its kind from the assembled catalog.
        let mut kinds = std::collections::HashMap::new();
        kinds.insert("pos.sale.create".to_string(), json!({ "kind": "command" }));
        let line = r#"data: {"type":"function_call","name":"pos.sale.create","call_id":"c9","arguments":"{}"}"#;
        let out = translate_sse_line(line, &kinds).expect("forwarded");
        assert!(out.contains("\"kind\":\"command\""));
        // An unknown tool (not in the map) is forwarded without a kind → treated as read.
        let line2 =
            r#"data: {"type":"function_call","name":"who.knows","call_id":"c0","arguments":"{}"}"#;
        let out2 = translate_sse_line(line2, &kinds).expect("forwarded");
        assert!(!out2.contains("\"kind\""));
    }

    /// The confirm card needs two things the model cannot be trusted to supply: how DANGEROUS the
    /// operation is (hub#1042) and which of its arguments are MONEY (hub#1040). Both are facts of
    /// the manifest, resolved once when the catalogue is assembled, and they have to travel WITH
    /// the tool call — the drawer has no catalogue of its own to look them up in.
    #[test]
    fn translate_annotates_risk_and_money_fields() {
        let mut notes = std::collections::HashMap::new();
        notes.insert(
            "services.services.create".to_string(),
            json!({ "kind": "command", "risk": "normal", "money_fields": ["price_cents"] }),
        );
        let line = r#"data: {"type":"function_call","name":"services.services.create","call_id":"c1","arguments":"{}"}"#;

        let out = translate_sse_line(line, &notes).expect("forwarded");

        assert!(out.contains("\"kind\":\"command\""), "{out}");
        assert!(out.contains("\"risk\":\"normal\""), "{out}");
        assert!(
            out.contains("price_cents"),
            "the money marking must reach the card: {out}"
        );
    }

    /// Regression test for ERPlora/hub#1183 — the POST-turn `usage` frame must CROSS the runtime.
    ///
    /// The SaaS closes every stream with `{"type":"usage", …}` right before `[DONE]` (saas#1540),
    /// because `X-Assistant-Usage` cannot do that job: a header is written before the body, so on
    /// its own it is always one message behind. The runtime's `match` ended in `_ => None`, so the
    /// frame died here and the drawer's counter could never move without a reload.
    ///
    /// Forwarded VERBATIM, like `error`: these are the SaaS's own numbers and the runtime has no
    /// business reinterpreting them.
    #[test]
    fn translate_forwards_the_post_turn_usage_frame_hub_1183() {
        let notes = std::collections::HashMap::new();
        let line = r#"data: {"type":"usage","tier":"free","messages_used":24,"messages_limit":30,"resets_at":"2026-09-01T00:00:00+00:00"}"#;

        let out = translate_sse_line(line, &notes)
            .expect("the usage frame must be forwarded, not dropped");

        assert!(out.contains("\"type\":\"usage\""), "{out}");
        assert!(
            out.contains("\"messages_used\":24"),
            "the counters must survive: {out}"
        );
        assert!(
            out.contains("\"messages_limit\":30"),
            "the counters must survive: {out}"
        );
        assert!(
            out.contains("2026-09-01T00:00:00+00:00"),
            "resets_at is what turns \"0 left\" into something actionable: {out}"
        );
    }

    /// The other half of ERPlora/hub#1183: opening the door for `usage` must NOT open it for
    /// everything. An unknown frame type stays dropped — turning one into text would let the Cloud
    /// put words in the assistant's mouth that the model never wrote.
    #[test]
    fn translate_still_drops_an_unknown_frame_type_hub_1183() {
        let notes = std::collections::HashMap::new();
        let line = r#"data: {"type":"something_new","payload":"whatever"}"#;

        assert_eq!(translate_sse_line(line, &notes), None);
    }

    #[test]
    fn tool_def_carries_params_schema() {
        // The op's input schema becomes the tool's `parameters` so the model calls
        // with valid arguments (the Cloud reads `fn.parameters`).
        let schema =
            r#"{"type":"object","properties":{"since":{"type":"string"}},"required":["since"]}"#;
        let t = tool_def(
            "sales.list",
            "List sales",
            "query",
            "sales",
            Some(schema),
            None,
            true,
        );
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
                    risk: None,
                }),
                expose_api: false,
                internal,
            }
        }

        let mut reg = Registry::new();
        reg.status
            .insert("cash_register".to_string(), ModuleStatus::Active);
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
        let module_tools: Vec<_> = tools.iter().filter(|t| t["module_id"] != "hub").collect();
        assert!(
            module_tools.is_empty(),
            "ningún command interno debe exponerse como tool: {module_tools:?}"
        );
    }

    #[test]
    fn tool_def_defaults_params_when_no_schema() {
        let t = tool_def("x.y", "d", "query", "x", None, None, true);
        assert_eq!(t["parameters"]["type"], "object");
        assert_eq!(t["parameters"]["properties"], json!({}));
        // An unparseable schema also degrades to the empty object (never panics).
        let bad = tool_def("x.y", "d", "query", "x", Some("{not json"), None, true);
        assert_eq!(bad["parameters"]["properties"], json!({}));
    }
}
