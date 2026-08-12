//! Registro en memoria de las capacidades de los módulos instalados + contexto de petición.
//! ARQUITECTURA.md §4. Soporta ciclo de vida: un módulo instalado puede estar ACTIVO o
//! INACTIVO; solo los activos exponen menú/queries/commands/eventos (hot-plug, §4 paso 11).
use std::collections::{HashMap, HashSet};

use crate::manifest::{CommandDef, Manifest, ModuleLocale, Nav, QueryDef};

/// Estado de un módulo instalado en este hub (equivalente a la tabla `hub_module`, §2.5).
#[derive(Debug, Clone, Copy, PartialEq, Eq, serde::Serialize)]
#[serde(rename_all = "snake_case")]
pub enum ModuleStatus {
    Active,
    /// Apagado A MANO por el admin: se respeta hasta que él lo reactive (o algo que dependa de él
    /// se active y lo arrastre hacia arriba).
    Inactive,
    /// Caído EN CASCADA al apagarse una dependencia (ADR-0128): quiere volver, y vuelve solo en
    /// cuanto todas sus `depends_on` estén activas.
    InactiveAuto,
}

/// JSON Schema **compilado** del payload de una query/command. Se compila UNA vez al
/// instalar el módulo (no por petición) y se cachea aquí; la validación por petición es
/// solo el `validate` sobre el validador ya compilado (§5.2, hub#27).
///
/// Conserva también el JSON crudo del schema (`raw`) para que el generador OpenAPI (ADR-0057)
/// pueda emitirlo tal cual en el `requestBody` (OpenAPI 3.1 = JSON Schema directo) sin
/// re-serializar desde el validador.
#[derive(Clone)]
pub struct CompiledSchema {
    pub validator: std::sync::Arc<jsonschema::Validator>,
    pub raw: std::sync::Arc<serde_json::Value>,
}

impl std::fmt::Debug for CompiledSchema {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str("CompiledSchema(..)")
    }
}

impl CompiledSchema {
    /// Compila `schema` (el JSON del fichero `schemas/*.json` del módulo) y conserva su JSON crudo.
    pub fn compile(schema: &serde_json::Value) -> Result<Self, String> {
        jsonschema::validator_for(schema)
            .map(|v| Self {
                validator: std::sync::Arc::new(v),
                raw: std::sync::Arc::new(schema.clone()),
            })
            .map_err(|e| e.to_string())
    }

    /// Inyecta los `default` del JSON Schema en `params` para cada propiedad **ausente**
    /// (causa raíz, decision-log 2026-06-25): el SQL declarativo bindea `:campo` por nombre, y un
    /// campo opcional omitido por el caller no llegaba con valor → `NOT NULL constraint failed`
    /// salvo que el módulo lo parchease con `COALESCE`. Aplicar el `default` del schema aquí hace
    /// ese COALESCE redundante (pero inofensivo): el caller que omite la clave obtiene el valor por
    /// defecto declarado.
    ///
    /// Reglas (conservadoras, JSON-Schema-fieles):
    /// - **Solo claves ausentes.** Un valor aportado por el caller NUNCA se sobreescribe.
    /// - **`null` explícito se respeta** (es un valor presente, no una ausencia): no se toca, igual
    ///   que cualquier otro valor aportado. El COALESCE/`NOT NULL` del SQL sigue mandando sobre el
    ///   `null` exactamente como hoy — este cambio no altera el trato del `null` explícito.
    /// - Solo `properties.<k>.default` de primer nivel (los `default` del estándar son por-propiedad;
    ///   no resolvemos `$ref`/`allOf`/anidados — alcance mínimo y suficiente para los schemas planos
    ///   de los commands declarativos).
    ///
    /// Se llama tras [`Self::validate`], así que el `default` ya pasó el contrato; solo se materializa.
    pub fn apply_defaults(&self, params: &mut crate::Params) {
        let Some(props) = self.raw.get("properties").and_then(|p| p.as_object()) else {
            return;
        };
        for (key, prop) in props {
            if params.contains_key(key) {
                continue; // valor aportado (incl. `null` explícito) → no tocar
            }
            if let Some(default) = prop.get("default") {
                params.insert(key.clone(), default.clone());
            }
        }
    }

    /// Valida `instance`; `Err` lleva el detalle legible de las violaciones (máx. 5).
    pub fn validate(&self, instance: &serde_json::Value) -> Result<(), String> {
        let errors: Vec<String> = self
            .validator
            .iter_errors(instance)
            .take(5)
            .map(|e| {
                let path = e.instance_path.to_string();
                if path.is_empty() {
                    e.to_string()
                } else {
                    format!("{path}: {e}")
                }
            })
            .collect();
        if errors.is_empty() {
            Ok(())
        } else {
            Err(errors.join("; "))
        }
    }
}

/// Una query registrada: su definición + el SQL ya leído de disco + el módulo que la aporta.
#[derive(Debug, Clone)]
pub struct RegisteredQuery {
    pub module_id: String,
    pub def: QueryDef,
    pub sql: String,
    /// JSON Schema del payload, ya compilado al instalar. `None` si la query no declara `schema`.
    pub schema: Option<CompiledSchema>,
}

/// Un command registrado: definición + SQLs leídos (en orden) + módulo.
#[derive(Debug, Clone)]
pub struct RegisteredCommand {
    pub module_id: String,
    pub def: CommandDef,
    pub sql: Vec<String>,
    /// Bytes del `.wasm` del handler Tier 2, ya leídos de disco. `None` si el
    /// command no declara handler (Tier 0/1).
    pub wasm: Option<Vec<u8>>,
    /// JSON Schema del payload, ya compilado al instalar. `None` si el command no declara `schema`.
    pub schema: Option<CompiledSchema>,
}

/// Entrada de menú con el módulo que la aporta.
#[derive(Debug, Clone)]
pub struct NavEntry {
    pub module_id: String,
    pub nav: Nav,
}

/// **Who emitted an event** (hub#529).
///
/// The event stream filters what it fans out by the module a frame came from, and the only place
/// that knows is the emitter: the dispatcher holds `cmd.module_id`. It is passed down here rather
/// than inferred from the event's *name* because the `module.event` shape is a convention **nobody
/// verifies** — a module may declare `emit: ["invoice.paid"]` and nothing stops it, so a filter
/// reading the prefix would let any module hand itself another module's audience.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum EventSource<'a> {
    /// An installed module's event, by module id.
    Module(&'a str),
    /// The hub itself: nobody's module. Flow approvals, an inbound WhatsApp message, the frames
    /// the installer and the print queue publish. See `erplora_server::event_stream`.
    Core,
}

impl EventSource<'_> {
    /// The emitting module id, or `None` for the hub's own events. An **empty** module id is also
    /// `None`: the outbox already writes `""` for a core event ([`crate::outbox::insert_core_event_once`]),
    /// and two spellings of "nobody" would eventually disagree.
    pub fn module_id(&self) -> Option<&str> {
        match self {
            EventSource::Module(id) if !id.is_empty() => Some(id),
            _ => None,
        }
    }
}

/// Observador de eventos del runtime. El server lo implementa con un canal
/// broadcast para reenviar los eventos por WebSocket (ARQUITECTURA.md §7.7).
///
/// `source` is **not optional and has no default** on purpose (hub#529): a sink that could forget
/// who emitted would publish a frame the stream cannot attribute, and an unattributable frame is
/// one the scope filter can only refuse — a silent loss of events with nothing to point at.
pub trait EventSink: Send + Sync + std::fmt::Debug {
    fn emit(&self, source: EventSource<'_>, event: &str, payload: &serde_json::Value);
}

#[derive(Debug, Default)]
pub struct Registry {
    pub installed: Vec<Manifest>,
    /// Estado por módulo (id → activo/inactivo).
    pub status: HashMap<String, ModuleStatus>,
    pub queries: HashMap<String, RegisteredQuery>,
    pub commands: HashMap<String, RegisteredCommand>,
    pub permissions: HashSet<String>,
    /// evento → lista de commands a ejecutar cuando se emite.
    pub listeners: HashMap<String, Vec<String>>,
    pub navigation: Vec<NavEntry>,
    /// Traducciones por módulo: `module_id → (lang → ModuleLocale)` (ADR-0055). Se cargan de
    /// `locales/*.json` del paquete al instalar/re-hidratar. Vacío = el módulo no trae i18n
    /// (se usan los valores del manifest, en inglés canónico).
    pub locales: HashMap<String, HashMap<String, ModuleLocale>>,
    /// Observador opcional de eventos (lo pone el server para el WS).
    pub event_sink: Option<std::sync::Arc<dyn EventSink>>,
    /// Plugins **nativos first-party** (ADR-0009): `module_id` → motor horneado en el
    /// runtime. Los registra el host (server/Tauri) al arrancar, no la instalación.
    pub native: HashMap<String, std::sync::Arc<dyn crate::native::NativeHandler>>,
    /// Transporte de `host.notify` (ADR-0012): el cliente real de email/sms/whatsapp. Lo
    /// inyecta el host al arrancar (`Runtime::set_notify_transport`). `None` = la capacidad
    /// `host.notify` no está disponible (los eventos `*.reminder.due` se entregan a sus
    /// listeners de módulo, pero el listener-host no envía nada). Ver `outbox.rs`.
    pub notify_transport: Option<std::sync::Arc<dyn crate::host_notify::NotifyTransport>>,
    /// Conjunto de módulos cuyo canal WhatsApp es **premium de ERPlora** (sale por el proxy de
    /// Cloud con `check_quota`, ADR-0006/ADR-0012). El `tier` vive en Cloud (ADR-0007), así que
    /// el host lo siembra; un módulo no listado usa WhatsApp del tenant (secreto local).
    pub premium_whatsapp_modules: HashSet<String>,
    /// Backend de `static_files` declarado por módulos. Lo inyecta el host y resuelve a disco
    /// Local o Cloud→S3 sin exponer paths físicos al módulo.
    pub module_storage: Option<std::sync::Arc<dyn crate::module_storage::ModuleStorage>>,
    /// **This deploy is an ephemeral DEMO hub** (ADR-0197, hub#376). The host seals it at boot
    /// from `HubConfig.demo` (env `HUB_DEMO`, written only by the SaaS provisioning), exactly
    /// like it seals `native`, `notify_transport` or `module_storage`. It lives HERE, and not in
    /// [`RequestContext`], for one reason: `&Registry` is the only authority that reaches
    /// `commands::execute_at` on **every** path (HTTP, public API, assistant, outbox relay,
    /// scheduler) and that no caller can forge — a ctx field would be a label the next new door
    /// could forget to stamp.
    ///
    /// It is deliberately **not** a `hub_settings` key and not a header: a demo hub must not be
    /// able to leave the sandbox, and a REAL hub must not be able to declare itself a demo (that
    /// would be the way to make real sales stop reaching the AEAT — hub#485).
    ///
    /// Default `false` = a normal hub, so every hub that already exists keeps behaving exactly as
    /// before. Of the two ways to get this wrong, mislabelling a REAL hub as a demo is the worse
    /// one: it would freeze its fiscal identity and strand it out of production **without saying
    /// anything**. A demo missing the variable is still stopped by the SaaS-side R5 gate
    /// (hub#315) — but only by that, so the writer of `HUB_DEMO` is load-bearing: since
    /// `verifactu-gateway.md` §3.4 (2026-08-04, superseding ADR-0197 §2) a demo DOES carry the
    /// delegated certificate, so the environment pin below is what keeps it off the real AEAT.
    pub demo_hub: bool,
}

impl Registry {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn is_installed(&self, module_id: &str) -> bool {
        self.installed.iter().any(|m| m.id == module_id)
    }

    /// ¿Está el módulo instalado **y** activo?
    pub fn is_active(&self, module_id: &str) -> bool {
        matches!(self.status.get(module_id), Some(ModuleStatus::Active))
    }

    /// Nº de módulos **activos**. Lo usa el router de tools (§9.2b) para decidir si vale la pena
    /// enrutar (con pocos módulos sale más barato mandar todos los tools al LLM).
    pub fn active_module_count(&self) -> usize {
        self.status
            .values()
            .filter(|s| matches!(s, ModuleStatus::Active))
            .count()
    }

    /// Query registrada, **solo si su módulo está activo** (hot-plug).
    pub fn get_query(&self, name: &str) -> Option<&RegisteredQuery> {
        self.queries
            .get(name)
            .filter(|q| self.is_active(&q.module_id))
    }

    /// Command registrado, **solo si su módulo está activo**.
    pub fn get_command(&self, name: &str) -> Option<&RegisteredCommand> {
        self.commands
            .get(name)
            .filter(|c| self.is_active(&c.module_id))
    }

    /// Commands suscritos a un evento, **solo de módulos activos**.
    pub fn listeners_for(&self, event: &str) -> Vec<String> {
        self.listeners
            .get(event)
            .map(|cmds| {
                cmds.iter()
                    .filter(|name| {
                        self.commands
                            .get(*name)
                            .map(|c| self.is_active(&c.module_id))
                            .unwrap_or(false)
                    })
                    .cloned()
                    .collect()
            })
            .unwrap_or_default()
    }

    /// Menú dinámico: entradas de navegación **solo de módulos activos**.
    pub fn active_navigation(&self) -> Vec<&NavEntry> {
        self.navigation
            .iter()
            .filter(|n| self.is_active(&n.module_id))
            .collect()
    }

    /// Registra las traducciones de un módulo (ADR-0055). Vacío = se olvida cualquier i18n previa.
    pub fn set_locales(&mut self, module_id: &str, locales: HashMap<String, ModuleLocale>) {
        if locales.is_empty() {
            self.locales.remove(module_id);
        } else {
            self.locales.insert(module_id.to_string(), locales);
        }
    }

    /// Catálogo del idioma pedido para un módulo, con fallback `locale → en` (ADR-0055).
    fn locale_for(&self, module_id: &str, locale: &str) -> Option<&ModuleLocale> {
        let by_lang = self.locales.get(module_id)?;
        by_lang.get(locale).or_else(|| by_lang.get("en"))
    }

    /// Nombre del módulo traducido. Fallback: `locale → en → fallback` (el `name` del manifest).
    pub fn module_name_localized(&self, module_id: &str, fallback: &str, locale: &str) -> String {
        self.locale_for(module_id, locale)
            .and_then(|l| l.name.clone())
            .unwrap_or_else(|| fallback.to_string())
    }

    /// Label de una entrada de navegación traducido. Fallback: `locale → en → fallback`
    /// (el `label` del manifest).
    pub fn nav_label_localized(
        &self,
        module_id: &str,
        nav_id: &str,
        fallback: &str,
        locale: &str,
    ) -> String {
        self.locale_for(module_id, locale)
            .and_then(|l| l.navigation.get(nav_id))
            .and_then(|n| n.label.clone())
            .unwrap_or_else(|| fallback.to_string())
    }

    /// Localized title of a module's checklist item (ADR-0055, hub#762). Fallback:
    /// `locale → en → fallback` (the English-canonical `title` from `module.json#setup`).
    ///
    /// Without this the dashboard mixed core items (translated by the shell) with module items
    /// in English: the `title` travelled raw in the payload and the frontend had no shell i18n
    /// key for that module (hub#762).
    pub fn setup_title_localized(&self, module_id: &str, fallback: &str, locale: &str) -> String {
        self.locale_for(module_id, locale)
            .and_then(|l| l.setup.title.clone())
            .unwrap_or_else(|| fallback.to_string())
    }

    /// Localized description of a module's checklist item (ADR-0055, hub#762). Same fallback
    /// chain as [`Self::setup_title_localized`].
    pub fn setup_description_localized(
        &self,
        module_id: &str,
        fallback: &str,
        locale: &str,
    ) -> String {
        self.locale_for(module_id, locale)
            .and_then(|l| l.setup.description.clone())
            .unwrap_or_else(|| fallback.to_string())
    }

    // ── API pública por módulo (ADR-0057, public-api.md) ─────────────────────────────────────

    /// Queries de un módulo **activo** marcadas `expose_api` → `(nombre, &RegisteredQuery)`.
    /// Fuente de la "lectura" del scope de una API key y de los `path` GET del OpenAPI.
    pub fn exposed_queries<'a>(&'a self, module_id: &str) -> Vec<(&'a str, &'a RegisteredQuery)> {
        if !self.is_active(module_id) {
            return Vec::new();
        }
        self.queries
            .iter()
            .filter(|(_, q)| q.module_id == module_id && q.def.expose_api)
            .map(|(name, q)| (name.as_str(), q))
            .collect()
    }

    /// Commands de un módulo **activo** marcados `expose_api` → `(nombre, &RegisteredCommand)`.
    /// Fuente de la "escritura" del scope de una API key y de los `path` POST del OpenAPI.
    ///
    /// Excluye SIEMPRE los commands **internos** (prefijo `_` en el último segmento, o
    /// `internal: true`) — hub#131, hub#145 — incluso si un manifest los marcara `expose_api` por
    /// error: defensa en profundidad, el runtime nunca ANUNCIA (OpenAPI, doble puerta de API key)
    /// lo que luego rechazaría en `execute_at` con `internal_command`.
    pub fn exposed_commands<'a>(
        &'a self,
        module_id: &str,
    ) -> Vec<(&'a str, &'a RegisteredCommand)> {
        if !self.is_active(module_id) {
            return Vec::new();
        }
        self.commands
            .iter()
            .filter(|(name, c)| {
                c.module_id == module_id && c.def.expose_api && !c.def.is_internal(name)
            })
            .map(|(name, c)| (name.as_str(), c))
            .collect()
    }

    /// Nombre legible de un módulo instalado (el `name` del manifest), o el `module_id` si no
    /// está instalado. Lo usa el generador OpenAPI para los `tags`.
    pub fn module_display_name(&self, module_id: &str) -> String {
        self.installed
            .iter()
            .find(|m| m.id == module_id)
            .map(|m| m.name.clone())
            .unwrap_or_else(|| module_id.to_string())
    }

    /// Versión instalada de un módulo (del manifest), o `"0.0.0"` si no está instalado.
    pub fn module_version(&self, module_id: &str) -> String {
        self.installed
            .iter()
            .find(|m| m.id == module_id)
            .map(|m| m.version.clone())
            .unwrap_or_else(|| "0.0.0".to_string())
    }

    /// Installed modules that **declare they emit** `event_name` (hub#715), sorted, deduplicated.
    ///
    /// Both places a module can say it count: `events.emits` — which hub#709/#722 widened to mean
    /// *the whole catalogue* of what a module emits — and the `emit` of a declarative command,
    /// because a manifest that has not been updated yet only carries the second one and hub#722
    /// deliberately made that a warning rather than a refusal.
    ///
    /// It is what separates «this hub has never heard of that event» from «that event exists here
    /// and has not happened yet»: the second is an ordinary state of an infrequent event once
    /// retention has pruned its last occurrence (hub#699), and answering `404` to it would have
    /// the flow editor telling an owner that something in their own business does not exist.
    pub fn modules_emitting(&self, event_name: &str) -> Vec<String> {
        let mut ids: std::collections::BTreeSet<String> = std::collections::BTreeSet::new();
        for module in &self.installed {
            let declared = module.events.emits.iter().any(|e| e == event_name)
                || module
                    .commands
                    .values()
                    .any(|c| c.emit.iter().any(|e| e == event_name));
            if declared {
                ids.insert(module.id.clone());
            }
        }
        ids.into_iter().collect()
    }

    /// Ids de los módulos **activos** que exponen al menos una query/command `expose_api`
    /// (orden estable por id). Lo usan el generador OpenAPI y la matriz de scope de la UI.
    pub fn modules_with_public_api(&self) -> Vec<String> {
        let mut ids: Vec<String> = self
            .installed
            .iter()
            .map(|m| m.id.clone())
            .filter(|id| {
                self.is_active(id)
                    && (!self.exposed_queries(id).is_empty()
                        || !self.exposed_commands(id).is_empty())
            })
            .collect();
        ids.sort();
        ids
    }

    /// ¿Es `name` una query de `module_id`, marcada `expose_api`, de un módulo activo? La **doble
    /// puerta** del data-surface: la ruta `POST /api/v1/{module}/q/{query}` solo deja pasar si esto
    /// es `true` (luego el gate de permisos del runtime revalida igual). Comprueba además que la
    /// operación **pertenece** al módulo de la ruta (evita cruzar namespaces).
    pub fn is_query_exposed(&self, module_id: &str, name: &str) -> bool {
        self.get_query(name)
            .map(|q| q.module_id == module_id && q.def.expose_api)
            .unwrap_or(false)
    }

    /// Espejo de [`is_query_exposed`] para commands (`POST /api/v1/{module}/c/{command}`). Un
    /// command INTERNO (hub#131, hub#145) nunca pasa esta puerta, aunque `expose_api` fuera `true`.
    pub fn is_command_exposed(&self, module_id: &str, name: &str) -> bool {
        self.get_command(name)
            .map(|c| c.module_id == module_id && c.def.expose_api && !c.def.is_internal(name))
            .unwrap_or(false)
    }

    /// Cambia el estado de un módulo instalado. Devuelve `false` si no existe.
    pub fn set_status(&mut self, module_id: &str, status: ModuleStatus) -> bool {
        if !self.is_installed(module_id) {
            return false;
        }
        self.status.insert(module_id.to_string(), status);
        true
    }

    /// Elimina un módulo del registro (sus capacidades dejan de existir). No borra su BD.
    pub fn remove_module(&mut self, module_id: &str) -> bool {
        if !self.is_installed(module_id) {
            return false;
        }
        self.installed.retain(|m| m.id != module_id);
        self.status.remove(module_id);
        self.queries.retain(|_, q| q.module_id != module_id);
        self.commands.retain(|_, c| c.module_id != module_id);
        self.navigation.retain(|n| n.module_id != module_id);
        self.locales.remove(module_id);
        for cmds in self.listeners.values_mut() {
            cmds.retain(|name| self.commands.contains_key(name));
        }
        self.listeners.retain(|_, v| !v.is_empty());
        true
    }

    /// Everything [`remove_module`](Self::remove_module) would strip, kept aside so it can be put
    /// back (hub#516).
    ///
    /// This is what makes an update safe to attempt: installing a new version has to unregister the
    /// old one before registering the new, and if the new one fails halfway the hub would be left
    /// **without the module** — no queries, no commands, no navigation — while `hub_module` still
    /// says it is installed. Taking the snapshot costs a clone of what one module contributes; not
    /// taking it costs a till.
    ///
    /// `None` when the module is not installed: a first install that fails has nothing to restore,
    /// and must not end up half-registered because of this.
    pub fn snapshot_module(&self, module_id: &str) -> Option<ModuleSnapshot> {
        let manifest = self.installed.iter().find(|m| m.id == module_id)?.clone();
        Some(ModuleSnapshot {
            status: self.status.get(module_id).copied(),
            queries: self
                .queries
                .iter()
                .filter(|(_, q)| q.module_id == module_id)
                .map(|(name, q)| (name.clone(), q.clone()))
                .collect(),
            commands: self
                .commands
                .iter()
                .filter(|(_, c)| c.module_id == module_id)
                .map(|(name, c)| (name.clone(), c.clone()))
                .collect(),
            navigation: self
                .navigation
                .iter()
                .filter(|n| n.module_id == module_id)
                .cloned()
                .collect(),
            locales: self.locales.get(module_id).cloned().unwrap_or_default(),
            // A listener belongs to the module that owns the command it fires (hub#659 makes that
            // the only shape a manifest can declare), so this is exactly the module's own share of
            // the map — the same rule `remove_module` uses to prune it.
            listeners: self
                .listeners
                .iter()
                .flat_map(|(event, commands)| {
                    commands
                        .iter()
                        .filter(|name| {
                            self.commands
                                .get(*name)
                                .is_some_and(|c| c.module_id == module_id)
                        })
                        .map(move |name| (event.clone(), name.clone()))
                })
                .collect(),
            manifest,
        })
    }

    /// Puts a [`ModuleSnapshot`] back, replacing whatever is registered for that module now.
    ///
    /// Used after a failed update: the version that was running goes back to serving. It is NOT a
    /// schema rollback — migrations are forward-only and expand-only (ADR-0269 §3.4/§7), so what
    /// already applied stays and the previous version simply ignores it.
    pub fn restore_module(&mut self, snapshot: ModuleSnapshot) {
        let module_id = snapshot.manifest.id.clone();
        self.remove_module(&module_id);

        self.installed.push(snapshot.manifest);
        if let Some(status) = snapshot.status {
            self.status.insert(module_id.clone(), status);
        }
        self.queries.extend(snapshot.queries);
        self.commands.extend(snapshot.commands);
        self.navigation.extend(snapshot.navigation);
        self.set_locales(&module_id, snapshot.locales);
        for (event, command) in snapshot.listeners {
            let listeners = self.listeners.entry(event).or_default();
            if !listeners.contains(&command) {
                listeners.push(command);
            }
        }
    }
}

/// What one module contributes to the [`Registry`], kept aside so a failed update can put the
/// working version back (hub#516). Opaque on purpose: it is a restore token, not a view.
#[derive(Debug, Clone)]
pub struct ModuleSnapshot {
    manifest: Manifest,
    status: Option<ModuleStatus>,
    queries: Vec<(String, RegisteredQuery)>,
    commands: Vec<(String, RegisteredCommand)>,
    navigation: Vec<NavEntry>,
    locales: HashMap<String, ModuleLocale>,
    /// `(event, command)` pairs whose command belongs to the module.
    listeners: Vec<(String, String)>,
}

impl ModuleSnapshot {
    /// The manifest of the version that was running — what the restore puts back.
    pub fn manifest(&self) -> &Manifest {
        &self.manifest
    }

    /// The version that was running (`1.0.0`), i.e. the `from` of an update.
    pub fn version(&self) -> &str {
        &self.manifest.version
    }
}

/// Contexto de una petición: identidad y alcance. El runtime inyecta `hub_id`,
/// `current_user_id` y `now` en cada query/command (ARQUITECTURA.md §2.5, §2.9).
#[derive(Debug, Clone)]
pub struct RequestContext {
    pub hub_id: String,
    pub user_id: String,
    pub permissions: HashSet<String>,
    /// Identidad de NEGOCIO GLOBAL del hub (FUENTE ÚNICA país-agnóstica, `hub_settings`:
    /// business_tax_id/legal_name/address — ADR-0061). La inyecta el dispatcher
    /// (`commands::execute_at`, profundidad 0) leyendo los settings, y `system_params` la expone como
    /// `:business_tax_id`/`:business_legal_name`/`:business_address` a TODO el SQL (incl. las
    /// operaciones que emiten los handlers WASM/nativos) para que los módulos (p.ej. invoice como
    /// emisor) usen el identificador fiscal del obligado sin que el caller lo pase. Vacío si no se ha
    /// configurado o fuera del flujo de comandos.
    pub business_tax_id: String,
    pub business_legal_name: String,
    pub business_address: String,
    /// ¿El hub tiene cargado el certificado fiscal del negocio (`_hub_certificate`, core — ADR-0081)?
    /// Lo rellena el dispatcher junto a la identidad de negocio; `system_params` lo expone como
    /// `:has_certificate` (0/1) para que los módulos con capability `certificate` (p.ej. verifactu)
    /// muestren el estado SIN leer la tabla de sistema directamente.
    pub has_certificate: bool,
    /// **IDENTIDAD FISCAL del hub** (`hub_settings.country_code` / `region_code` — ADR-0085). La
    /// inyecta el dispatcher junto a la identidad de negocio.
    ///
    /// Es la mitad de la clave con la que el SERVIDOR resuelve el impuesto de una venta: una regla
    /// fiscal es `(country_code, region_code, tax_category_key) → rate_pct`. Sin el país del hub,
    /// ninguna regla casa y el handler cae a su fallback… que es la pista del cliente. O sea: sin
    /// esto, **el navegador decide el IVA que se le declara a la AEAT**.
    pub country_code: String,
    /// Subdivisión ISO-3166-2 (`ES-CN`…) o vacío = todo el país. Una regla con región gana a la del
    /// país (Canarias/IGIC, Ceuta y Melilla/IPSI).
    pub region_code: String,
    /// **Who is behind this request**: a person, or a machine (hub#361). See [`Principal`].
    pub principal: Principal,
    /// Reference to a **step-up approval** this runtime is holding (hub#361), if the caller
    /// presented one (`X-Elevation-Token`). It is a lookup key into
    /// [`crate::elevation::Grants`] — **never** a claim: an unknown, expired or foreign token is
    /// indistinguishable from no token at all, and the payload is never read for it.
    pub elevation_token: Option<String>,
    /// **What this hub owes right now** (ADR-0273 D2, hub#550): the fiscal profile's status
    /// resolved against what is mounted, including the derived `BLOCKED`. The dispatcher fills it
    /// alongside the business identity and the certificate flag, from the core's own tables — no
    /// caller can state it.
    ///
    /// `None` means **not resolved**, never "nothing owed". It is deliberately not defaulted to a
    /// permissive value: an enrichment path that forgot to stamp it would otherwise look compliant,
    /// which is the failure mode `Registry::demo_hub` is placed in the registry to avoid. Whoever
    /// gates on this (hub#556) resolves `None` rather than passing it.
    pub fiscal_mode: Option<crate::fiscal_profile::FiscalMode>,
    /// The events that START a fiscal chain in this hub — learnt by the core from a healthy
    /// provider and **remembered** after it disappears (ADR-0273 D4, hub#550). The dispatcher fills
    /// it from the profile alongside [`RequestContext::fiscal_mode`]; the gate of hub#556 uses it
    /// as its trigger, so a transaction that would open a fiscal chain is refused **precisely when
    /// there is nobody left to close it**.
    pub fiscal_triggers: Vec<String>,
    /// Ids of the installed **and active** modules that fulfil the regime this hub owes (ADR-0273
    /// D4/D6). Resolved by the dispatcher from the profile + the registry, so `CLOSED` can let a
    /// provider drain what it still owes **without the core naming a single module**.
    pub fiscal_providers: Vec<String>,
    /// `hub_user.id` of the manager whose approval let this command past the permission gate.
    /// Filled by the dispatcher **after** spending a grant, so it is a fact about what happened,
    /// not something a caller can assert. This is the seam hub#362 writes next to the cashier's
    /// `created_by` — the double attribution is the whole point of approving instead of sharing a
    /// password.
    pub approved_by: Option<String>,
    /// **Which flow is acting, when no person is** (ADR-0283 D2, hub#661). `Some` means this
    /// request is a step of a flow run, and the permission gate in `commands::execute_at` asks
    /// `_flow_grants` about THAT flow instead of asking a role about a human.
    ///
    /// The field is **private and its setter is `pub(crate)`** on purpose, and that is the whole
    /// mechanism: `RequestContext` crosses the crate boundary into `erplora-server`, where every
    /// context is built from something a caller sent (a session, an API key, a header). Were this
    /// `pub`, a route could stamp `automation: Some(flow_id)` on a request and inherit that flow's
    /// grants — turning «the hub acting on its own» into a privilege anybody with an HTTP client
    /// could claim. Only the runtime's own executor can fill it in.
    automation: Option<AutomationCtx>,
    /// **The event whose delivery caused this request** (hub#666), if any. Stamped by the outbox
    /// relay when it reconstructs a listener's context, and carried by a flow run from the event
    /// that started it, so every event emitted downstream can name what set it off.
    ///
    /// `_event_outbox.depth` already said how FAR a cascade had travelled; it never said **from
    /// what**. On a till closing two sales a second, "the row before it in time" is a guess, and a
    /// guess is not an answer to "why does this invoice exist".
    ///
    /// Private with a `pub(crate)` setter for the same reason as [`Self::automation`]: this
    /// struct crosses into `erplora-server`, where contexts are built from what a caller sent. A
    /// route able to stamp it could file its events under somebody else's execution, which makes
    /// the whole audit trail worth exactly nothing.
    parent_event_id: String,
}

/// Identity of the flow behind an automation request: which flow, and which of its runs.
///
/// Both halves are needed and neither is decoration: `flow_id` is what the grant gate reads, and
/// `run_id` is what ties the effects back to the execution that caused them when somebody later
/// asks why a row exists.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct AutomationCtx {
    pub flow_id: String,
    pub run_id: String,
}

/// Who is behind a request. The distinction only exists because of what it forbids.
///
/// A **machine** principal (an API key, ADR-0057) has nobody standing at it: telling a nightly
/// integration to «ask a manager to type their PIN» is an instruction nothing can follow. Before
/// hub#361 that was merely an absurd message; now that an approval GRANTS, it would be a second,
/// quieter way in for a credential that is stored, copied and long-lived. So a machine principal
/// is **never offered** elevation ([`crate::permissions::check_command`]) and can **never be
/// approved** ([`crate::Runtime::approve_elevation`]).
///
/// [`Principal::Human`] is the default on purpose: a surface that forgets to say what it is gets
/// the ordinary behaviour, and the only thing `Machine` ever does is take capability away.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub enum Principal {
    #[default]
    Human,
    Machine,
}

impl RequestContext {
    pub fn new(
        hub_id: impl Into<String>,
        user_id: impl Into<String>,
        permissions: impl IntoIterator<Item = String>,
    ) -> Self {
        Self {
            hub_id: hub_id.into(),
            user_id: user_id.into(),
            permissions: permissions.into_iter().collect(),
            country_code: String::new(),
            region_code: String::new(),
            business_tax_id: String::new(),
            business_legal_name: String::new(),
            business_address: String::new(),
            has_certificate: false,
            fiscal_mode: None,
            fiscal_triggers: Vec::new(),
            fiscal_providers: Vec::new(),
            principal: Principal::Human,
            elevation_token: None,
            approved_by: None,
            automation: None,
            parent_event_id: String::new(),
        }
    }

    /// Marks this context as **a step of a flow run** (ADR-0283 D2). `pub(crate)` is the point:
    /// see [`RequestContext::automation`].
    pub(crate) fn with_automation(mut self, automation: AutomationCtx) -> Self {
        self.automation = Some(automation);
        self
    }

    /// The flow this request belongs to, if any. Readable everywhere (the audit and the error
    /// reporter want it); settable only inside the runtime.
    pub fn automation(&self) -> Option<&AutomationCtx> {
        self.automation.as_ref()
    }

    /// Marks this context as **caused by the delivery of an event** (hub#666). Only the relay and
    /// the flow executor call it — see [`RequestContext::parent_event_id`].
    pub(crate) fn caused_by_event(mut self, event_id: impl Into<String>) -> Self {
        self.parent_event_id = event_id.into();
        self
    }

    /// The event that caused this request, or `""` when a person started it directly.
    pub fn parent_event_id(&self) -> &str {
        &self.parent_event_id
    }

    /// Marks this context as a **machine** principal (an API key — [`Principal::Machine`]). Only
    /// ever takes capability away: it cannot be offered elevation, and it cannot be approved.
    pub fn as_machine(mut self) -> Self {
        self.principal = Principal::Machine;
        self
    }

    /// Attaches the step-up approval token the caller presented (hub#361). The HTTP layer reads it
    /// from `X-Elevation-Token` — **out of band, never from the payload**, so the body of a
    /// command stays pure data and a hostile client cannot smuggle authority through it.
    pub fn with_elevation_token(mut self, token: impl Into<String>) -> Self {
        self.elevation_token = Some(token.into());
        self
    }

    /// Copy that has **spent** an approval: it records who approved and drops the token, so the
    /// reference cannot be looked at twice further down the call chain.
    ///
    /// Note what it does **not** do: it never adds the permission to [`Self::permissions`]. The
    /// approval authorises passing **one gate**, not holding the permission — anything downstream
    /// that asks again must ask again.
    pub(crate) fn spent_approval_of(mut self, approver_id: impl Into<String>) -> Self {
        self.approved_by = Some(approver_id.into());
        self.elevation_token = None;
        self
    }

    /// Devuelve una copia con la identidad de negocio global rellena (la usa el dispatcher tras leer
    /// `hub_settings`). Builder para no romper los `new(...)` existentes.
    pub fn with_business(
        mut self,
        tax_id: impl Into<String>,
        legal_name: impl Into<String>,
        address: impl Into<String>,
    ) -> Self {
        self.business_tax_id = tax_id.into();
        self.business_legal_name = legal_name.into();
        self.business_address = address.into();
        self
    }

    /// Fija la **identidad fiscal** del hub (país/región, ADR-0085). Es lo que permite al servidor
    /// resolver el impuesto contra el catálogo en vez de creerse el % que le mande el cliente.
    pub fn with_fiscal(
        mut self,
        country_code: impl Into<String>,
        region_code: impl Into<String>,
    ) -> Self {
        self.country_code = country_code.into();
        self.region_code = region_code.into();
        self
    }

    /// Copia con el flag de presencia del certificado fiscal del negocio (`_hub_certificate`, core).
    /// Lo rellena el dispatcher junto a `with_business`. Builder para no romper los `new(...)`/tests.
    pub fn with_certificate(mut self, present: bool) -> Self {
        self.has_certificate = present;
        self
    }

    /// Stamps the hub's effective fiscal mode (ADR-0273 D2, hub#550). Only the dispatcher calls it,
    /// from the core's own tables — it is a fact about the hub, not a claim from the caller.
    pub fn with_fiscal_mode(
        mut self,
        mode: crate::fiscal_profile::FiscalMode,
        triggers: Vec<String>,
        providers: Vec<String>,
    ) -> Self {
        self.fiscal_mode = Some(mode);
        self.fiscal_triggers = triggers;
        self.fiscal_providers = providers;
        self
    }
}

// ── helpers de parámetros del sistema ───────────────────────────────────────────────────

/// Timestamp RFC3339 (UTC) para `:now`.
pub(crate) fn now_rfc3339() -> String {
    chrono::Utc::now().to_rfc3339()
}

/// Id nuevo (uuid v4) para `:new_id`.
pub(crate) fn new_id() -> String {
    uuid::Uuid::new_v4().to_string()
}

#[cfg(test)]
mod tests {
    use super::*;

    fn cmd_def(expose_api: bool, internal: bool) -> CommandDef {
        CommandDef {
            permission: "m.write".to_string(),
            reads: Vec::new(),
            transaction: false,
            sql: vec![],
            schema: None,
            emit: vec![],
            min_affected_rows: None,
            expect_rows: None,
            handler: None,
            ai: None,
            expose_api,
            internal,
        }
    }

    fn registry_with(name: &str, expose_api: bool, internal: bool) -> Registry {
        let mut reg = Registry::new();
        reg.status.insert("pricing".to_string(), ModuleStatus::Active);
        reg.commands.insert(
            name.to_string(),
            RegisteredCommand {
                module_id: "pricing".to_string(),
                def: cmd_def(expose_api, internal),
                sql: vec![],
                wasm: None,
                schema: None,
            },
        );
        reg
    }

    /// (d) hub#131/#145 — un command "privado por convención" (último segmento con `_`, estilo
    /// `pricing._insert_price_list`) NUNCA aparece en `exposed_commands`/`is_command_exposed`
    /// —las fuentes que alimentan tanto el generador OpenAPI (`openapi::build_spec`) como la
    /// doble puerta de la API pública (`api_keys::data_command`)— NI SIQUIERA si el manifest lo
    /// marca (por error) `expose_api: true`.
    #[test]
    fn exposed_commands_excludes_underscore_command_even_with_expose_api_true() {
        let reg = registry_with("pricing._insert_price_list", true, false);
        assert!(
            reg.exposed_commands("pricing").is_empty(),
            "un command `_` con expose_api=true NO debe listarse"
        );
        assert!(!reg.is_command_exposed("pricing", "pricing._insert_price_list"));
    }

    /// Espejo con `internal: true` explícito (sin prefijo `_`): tampoco se anuncia.
    #[test]
    fn exposed_commands_excludes_manifest_flagged_internal_even_with_expose_api_true() {
        let reg = registry_with("pricing.reindex_catalog", true, true);
        assert!(
            reg.exposed_commands("pricing").is_empty(),
            "internal:true con expose_api=true NO debe listarse"
        );
        assert!(!reg.is_command_exposed("pricing", "pricing.reindex_catalog"));
    }

    /// Control: un command público normal (sin `_`, sin `internal:true`) marcado `expose_api`
    /// SÍ se lista — el filtro no bloquea de más.
    #[test]
    fn exposed_commands_includes_a_normal_public_command() {
        let reg = registry_with("pricing.set_default", true, false);
        assert_eq!(reg.exposed_commands("pricing").len(), 1);
        assert!(reg.is_command_exposed("pricing", "pricing.set_default"));
    }

    /// hub#361: spending an approval opens **one gate**, it does not hand out the permission.
    ///
    /// This is the property that keeps an approval from spreading. Nothing downstream of the gate
    /// re-asks the RBAC question — a handler resolves its own module's SQL under the command that
    /// invoked it (§5.3), the fiscal and capability gates ask different questions — so if the
    /// elevated context simply *held* `till.take_payment`, an approval would silently become the
    /// permission for the rest of the call. It never enters the set.
    #[test]
    fn spending_an_approval_records_who_approved_without_granting_anything() {
        let ctx = RequestContext::new("h1", "u-cashier", ["till.add_sale".to_string()])
            .with_elevation_token("t-1");
        assert_eq!(ctx.elevation_token.as_deref(), Some("t-1"));
        assert_eq!(ctx.approved_by, None);

        let spent = ctx.clone().spent_approval_of("u-manager");
        assert_eq!(spent.approved_by.as_deref(), Some("u-manager"));
        assert_eq!(
            spent.permissions, ctx.permissions,
            "the approval must not add the permission it approved — nor any other"
        );
        assert_eq!(
            spent.elevation_token, None,
            "the reference is dropped with the grant, so nothing further down can look twice"
        );
        assert_eq!(
            spent.user_id, "u-cashier",
            "who was at the till does not change"
        );
    }

    /// The default side of [`Principal`] is not decoration: it decides what a context that never
    /// says what it is may do. `Machine` only ever takes capability away, so the default has to be
    /// `Human` — and nothing else in the crate asserts it, because `RequestContext::new` spells it
    /// out. The day somebody derives `Default` for a context, or builds one with `..Default`,
    /// this is what stops the elevation dialog from silently disappearing for everyone.
    #[test]
    fn the_default_principal_is_the_human_one() {
        assert_eq!(Principal::default(), Principal::Human);
        assert_eq!(
            RequestContext::new("h1", "u1", Vec::<String>::new()).principal,
            Principal::default(),
            "`new` and the derive must not drift apart"
        );
    }

    // ── Setup item i18n (ADR-0055, hub#762) ──────────────────────────────────────────────────
    //
    // The checklist used to mix Spanish (core items, translated by the shell) with English (module
    // items, the raw `title` from the payload). The contract of ADR-0055 already covered
    // `setup.{title,description}` in `locales/<lang>.json` — these tests pin the half that was
    // missing: the runtime resolving that locale.

    fn registry_with_setup_locale(
        module_id: &str,
        locales: &[(&str, Option<&str>, Option<&str>)],
    ) -> Registry {
        use crate::manifest::{ModuleLocale, SetupLocale};
        let mut reg = Registry::new();
        let mut map = std::collections::HashMap::new();
        for (lang, title, desc) in locales {
            map.insert(
                (*lang).to_string(),
                ModuleLocale {
                    setup: SetupLocale {
                        title: title.map(|s| s.to_string()),
                        description: desc.map(|s| s.to_string()),
                        ..Default::default()
                    },
                    ..Default::default()
                },
            );
        }
        reg.set_locales(module_id, map);
        reg
    }

    /// The regression itself (hub#762): a module item title resolves to the hub's locale when the
    /// module ships a translation for it. Before the fix this returned the English fallback.
    #[test]
    fn setup_title_resolves_to_the_hub_locale() {
        let reg = registry_with_setup_locale(
            "inventory",
            &[
                ("es", Some("Tu catálogo"), Some("Añade un producto.")),
                ("en", Some("Your catalog"), Some("Add a product.")),
            ],
        );
        assert_eq!(
            reg.setup_title_localized("inventory", "Your catalog", "es"),
            "Tu catálogo"
        );
        assert_eq!(
            reg.setup_description_localized("inventory", "Add a product.", "es"),
            "Añade un producto."
        );
    }

    /// A module that did not bother with an English locale still renders: the asked locale wins,
    /// and when it is missing the registry hands back the manifest fallback rather than `None`.
    #[test]
    fn setup_title_falls_back_to_manifest_when_locale_is_missing() {
        let reg = registry_with_setup_locale(
            "inventory",
            &[("es", Some("Tu catálogo"), Some("Añade un producto."))],
        );
        // Asked locale present → translated.
        assert_eq!(
            reg.setup_title_localized("inventory", "Your catalog", "es"),
            "Tu catálogo"
        );
        // Asked locale absent, no `en` either → the English canonical title of the manifest.
        assert_eq!(
            reg.setup_title_localized("inventory", "Your catalog", "fr"),
            "Your catalog"
        );
    }

    /// A third-party module that ships no `locales/` at all must not break the checklist: the
    /// English canonical of the manifest is the answer, for both title and description.
    #[test]
    fn setup_title_falls_back_to_manifest_when_module_has_no_locales() {
        let reg = Registry::new();
        assert_eq!(
            reg.setup_title_localized("acme", "Acme setup", "es"),
            "Acme setup"
        );
        assert_eq!(
            reg.setup_description_localized("acme", "Configure acme.", "es"),
            "Configure acme."
        );
    }

    /// The fallback chain is `locale → en → manifest`: an `fr` hub whose module ships `en` (but no
    /// `fr`) renders the English translation, not the raw manifest value.
    #[test]
    fn setup_title_falls_back_to_en_before_the_manifest() {
        let reg = registry_with_setup_locale(
            "inventory",
            &[("en", Some("Your catalog"), None)],
        );
        assert_eq!(
            reg.setup_title_localized("inventory", "Your catalog", "fr"),
            "Your catalog",
            "`en` matches before the manifest fallback"
        );
        // Description was not translated even in `en` → manifest wins.
        assert_eq!(
            reg.setup_description_localized("inventory", "Add a product.", "fr"),
            "Add a product."
        );
    }
}
