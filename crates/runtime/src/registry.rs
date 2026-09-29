//! Registro en memoria de las capacidades de los módulos instalados + contexto de petición.
//! ARQUITECTURA.md §4. Soporta ciclo de vida: un módulo instalado puede estar ACTIVO o
//! INACTIVO; solo los activos exponen menú/queries/commands/eventos (hot-plug, §4 paso 11).
use std::collections::{HashMap, HashSet};

use crate::manifest::{
    CommandDef, FloorRequirement, FlowTemplateDiscard, FlowTemplateScan, Manifest,
    ModuleFlowTemplate, ModuleLocale, Nav, QueryDef, FLOOR_MODULE_MISSING, FLOOR_MODULE_PAUSED,
    FLOOR_MODULE_TOO_OLD, FLOOR_UNREADABLE, OWNER_PAUSED,
};

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

    /// Reescribe los números de `params` a la FORMA que su propiedad declara (hub#1092):
    /// `"type": "number"` → siempre flotante; `"type": "integer"` → siempre entero.
    ///
    /// # Por qué existe
    ///
    /// El binder de `erplora-db` tipa cada bind **por el valor**: un JSON `10` sale como `int8` y
    /// un `10.5` como `float8`. Para un campo declarado `"number"` esas son la MISMA ranura de la
    /// MISMA sentencia con dos tipos de cable distintos — y la caché de sentencias preparadas de
    /// sqlx (indexada por texto, sin re-Parse) congela el primero que la calentó. Como `int8` y
    /// `float8` miden los dos 8 bytes, el servidor no puede detectar el cambiazo: lee los bytes
    /// como el tipo que tenía guardado. Medido (services#55): `int8` con un `10.5` encima guarda
    /// `4.6e18`; `float8` con un `10` encima guarda un denormal `5e-323` — o revienta con `22003`
    /// en una columna `real` estrecha. Ruidoso **a veces**, corrupto **siempre**.
    ///
    /// La corrección no puede vivir en el binder (no conoce el schema): vive aquí, donde el
    /// runtime SABE lo que el módulo declaró. Se llama tras [`Self::validate`] (y tras
    /// [`Self::apply_defaults`], cuyos `default` llegan con la forma del JSON del módulo), antes
    /// de bajar a SQL.
    ///
    /// # Reglas
    ///
    /// - Solo propiedades de PRIMER nivel con `"type"` `"number"`/`"integer"` (también como
    ///   lista, p. ej. `["number", "null"]`): los payloads del motor son planos y bindean por
    ///   nombre; lo demás queda como está.
    /// - `number`: un entero en JSON (`10`) ES un number válido (el validador lo acepta) → se
    ///   reescribe como `10.0`. Un entero > 2^53 pierde precisión al bajar a `f64`: es lo que el
    ///   schema declaró (semántica JS de `number`), y hoy ninguna tasa ni precio la alcanza.
    /// - `integer`: un flotante de valor integral (`4.0` ES un integer válido para JSON Schema)
    ///   se reescribe como `4`. Un flotante NO integral no se toca: el validador ya lo rechazó en
    ///   el camino declarativo, y en el camino de handler (sin validación de payload) tocarlo
    ///   cambiaría el valor, no la forma.
    /// - Strings, bools, `null` y ausentes: nunca se tocan.
    pub fn coerce_declared_number_shapes(&self, params: &mut crate::Params) {
        let Some(props) = self.raw.get("properties").and_then(|p| p.as_object()) else {
            return;
        };
        for (key, prop) in props {
            let declared = match declared_number_type(prop) {
                Some(t) => t,
                None => continue, // sin declaración de tipo numérico → el valor manda, como siempre
            };
            let Some(value) = params.get_mut(key) else {
                continue;
            };
            let serde_json::Value::Number(n) = value else {
                continue;
            };
            match declared {
                DeclaredNumberType::Number => {
                    if !n.is_f64() {
                        if let Some(f) =
                            serde_json::Number::from_f64(n.as_f64().unwrap_or(f64::NAN))
                        {
                            *value = serde_json::Value::Number(f);
                        }
                    }
                }
                DeclaredNumberType::Integer => {
                    if let Some(f) = n.as_f64() {
                        if f.fract() == 0.0 && f >= i64::MIN as f64 && f <= i64::MAX as f64 {
                            *value = serde_json::Value::Number(serde_json::Number::from(f as i64));
                        }
                    }
                }
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

/// The FIELD NAMES a [`CompiledSchema::validate`] detail names — hub#1094.
///
/// The Settings screen the shell generates for any module swallowed its 422: the person pressed
/// «Save», the runtime answered `invalid_payload`, and the screen stayed exactly as it was. To mark
/// the controls the runtime refused, the screen needs the names — and in this house such a list
/// travels as a FIELD of the error envelope, never parsed out of the sentence by the client (the
/// rule `permission` in hub#360 and `dependents` in hub#1101 already follow).
///
/// So the split lives here, right under the `format!` that produces the detail: producer and reader
/// are two halves of ONE format, and keeping them apart is how a format changes and the far end
/// quietly stops understanding it. The tests feed real `validate()` output through this to pin both.
///
/// Rules, all deliberately conservative:
/// - Only chunks that begin with a JSON Pointer (`/…`) count. The ~25 doors that raise
///   `InvalidPayload` by hand write free prose with no pointer, and prose must yield NOTHING rather
///   than an invented field name.
/// - A violation of the object itself (a missing `required` key) carries an EMPTY instance path and
///   so names no field. An empty name would mark no control and make the refusal look understood.
/// - A nested pointer names its ROOT property: that is the control the form paints.
/// - Order of first appearance, no duplicates — two violations of one field are one bad field.
pub fn invalid_payload_fields(detail: &str) -> Vec<String> {
    let mut out: Vec<String> = Vec::new();
    for chunk in detail.split("; ") {
        let Some(pointer) = chunk.strip_prefix('/') else {
            continue;
        };
        // `{path}: {e}` — the pointer ends at the first `: ` the formatter wrote.
        let pointer = pointer.split_once(": ").map(|(p, _)| p).unwrap_or(pointer);
        let Some(root) = pointer.split('/').next().filter(|s| !s.is_empty()) else {
            continue;
        };
        // RFC 6901: `~1` is a literal `/` and `~0` a literal `~`. Undo in that order or a name
        // containing `~1` would come back mangled.
        let name = root.replace("~1", "/").replace("~0", "~");
        if !out.contains(&name) {
            out.push(name);
        }
    }
    out
}

/// El tipo numérico que una propiedad de schema declara (hub#1092). `None` = no declara
/// `number`/`integer` (o declara otra cosa): el bind sigue tipado por el valor, como siempre.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum DeclaredNumberType {
    Number,
    Integer,
}

/// Lee el `"type"` de una propiedad como tipo numérico declarado. Acepta la forma string
/// (`"number"`) y la forma lista (`["number", "null"]`, el idioma de «opcional/nullable»);
/// en la lista manda el primer tipo numérico que aparezca.
fn declared_number_type(prop: &serde_json::Value) -> Option<DeclaredNumberType> {
    let pick = |s: &str| match s {
        "number" => Some(DeclaredNumberType::Number),
        "integer" => Some(DeclaredNumberType::Integer),
        _ => None,
    };
    match prop.get("type")? {
        serde_json::Value::String(s) => pick(s.as_str()),
        serde_json::Value::Array(types) => types.iter().find_map(|t| t.as_str().and_then(pick)),
        _ => None,
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

    /// [`Self::emit`], plus the shell tab whose request caused the event (hub#1980,
    /// [`RequestContext::client_instance`]). A sink that has nowhere to put it keeps the default,
    /// which drops it: the instance is a hint for live listeners, never part of the event.
    fn emit_from(
        &self,
        source: EventSource<'_>,
        client_instance: Option<&str>,
        event: &str,
        payload: &serde_json::Value,
    ) {
        let _ = client_instance;
        self.emit(source, event, payload);
    }
}

/// Un módulo que el hub recibió la orden de instalar y **no** se instaló (hub#1477).
///
/// No es un log: es estado que la sonda de readiness consulta. Por eso lleva las tres cosas que
/// hacen falta para actuar sin entrar al contenedor — **quién** falta, **de dónde** salía y **por
/// qué** no entró.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct FailedInstall {
    /// Id del módulo. Si el manifest ni siquiera cargó no hay id que leer, y entonces es el nombre
    /// de la carpeta: es lo único que hay y es justo lo que el operador ve en el disco.
    pub module_id: String,
    /// El paquete del que salía, para poder ir a mirarlo.
    pub source: String,
    /// El error, tal cual: sin el motivo, saber que falta no dice qué arreglar.
    pub reason: String,
}

#[derive(Debug, Default)]
pub struct Registry {
    pub installed: Vec<Manifest>,
    /// Código máquina de los handlers WASM, compilado una vez por versión de módulo (hub#926).
    /// Vive aquí porque su vida ES la del módulo instalado: `remove_module` —el paso previo de
    /// toda actualización— tira lo suyo, así que un hub nunca ejecuta el código de la versión
    /// anterior.
    pub wasm_cache: std::sync::Arc<crate::wasm_cache::WasmCache>,
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
    /// Automatizaciones de fábrica por módulo: `module_id → plantillas` (hub#1611). Se cargan de
    /// `flows/` del paquete al instalar/re-hidratar, igual que `locales`. Vacío = el módulo no
    /// trae ninguna, que es el caso de 26 de los 27 módulos de hoy.
    pub flow_templates: HashMap<String, FlowTemplateScan>,
    /// **Where the owner may put a rule**: `module_id → checkpoints` (hub#1701, ADR-0476). They are
    /// loaded from the package's `policies/` at install/re-hydrate time, just like `locales` and
    /// `flow_templates`, and for the same reason — that way the modules already installed publish
    /// their checkpoints on the first boot after this release, without reinstalling.
    pub policy_checkpoints: HashMap<String, crate::policies::CheckpointScan>,
    /// `command → checkpoint`, derived from [`Self::policy_checkpoints`] (hub#1701).
    ///
    /// It exists so the `commands::execute_at` gate resolves in **O(1)**: it runs on EVERY command,
    /// and walking the installed modules looking for who gates this name would be work per sale (the
    /// bounded-cost guard). It is rebuilt by [`Self::rebuild_policy_command_index`], which is the
    /// ONLY place that writes it and the one both of the map's only two mutators above call — so it
    /// cannot fall out of step with it.
    ///
    /// It does not filter by `is_active`: that is looked at on read, because a module's state
    /// changes without coming through here.
    policy_checkpoint_by_command: HashMap<String, crate::policies::PolicyCheckpoint>,
    /// **The rules in force**, indexed by command (hub#1701).
    ///
    /// It lives here, and not in a parameter of the signature, for the same reason as
    /// [`Self::demo_hub`]: the `&Registry` is the only authority that reaches
    /// `commands::execute_at` through **every** path (HTTP, public API, assistant, outbox relay,
    /// scheduler) and that no caller can fabricate. One more parameter would be a label the next new
    /// door could forget to attach, and forgetting it here means leaving the gate open.
    ///
    /// It is an IN-MEMORY index with interior mutability: boot and **every write** of the CRUD
    /// ([`crate::Runtime::reload_policies`]) rebuild it, and the gate only reads. Not having to ask
    /// for a `&mut Registry` to refresh it is what lets a rule just saved be in force on the next
    /// sale without restarting.
    pub policies: crate::policies::PolicyIndex,
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
    /// Módulos que este hub **recibió la orden de instalar** y no llegaron a instalarse
    /// (hub#1477). Lo llena [`crate::Runtime::install_all_from_dir`], que es tolerante a propósito
    /// —un módulo de terceros roto no debe brickear el arranque— pero cuya tolerancia era, hasta
    /// ahora, **silencio**: el fallo salía por un `eprintln!` y ahí moría.
    ///
    /// Vive aquí porque es la ÚNICA huella que queda de ese módulo: un install que falla no
    /// escribe en `hub_module`, así que `/readyz` —que compara `hub_module` contra el Registry— no
    /// tenía forma de saber que faltaba y publicaba `missing: []` sobre un hub incompleto.
    ///
    /// Describe el **último intento**, no un historial: cada pasada de `install_all_from_dir` lo
    /// reemplaza. Si acumulase, un módulo ya arreglado seguiría denunciado para siempre y la sonda
    /// no volvería a ponerse verde nunca.
    pub failed_installs: Vec<FailedInstall>,
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
    /// **Las claves naturales que el SEED de cada módulo declara** sobre sus propias tablas
    /// (hub#842): `module_id → (tabla → claves)`. Las lee
    /// [`crate::seed::declared_natural_keys`] del mismo texto que se va a sembrar, en
    /// `installer::register_module`, así que existen para todo módulo registrado por cualquiera de
    /// las tres puertas (arranque desde `modules_dir`, instalación desde el marketplace,
    /// re-hidratación desde la caché) y no sobreviven a un módulo desinstalado.
    ///
    /// Vive en el Registry, y no en disco ni en `hub_module`, por lo mismo que el resto de lo que
    /// aporta un módulo: su vida ES la del módulo instalado.
    pub(crate) seed_natural_keys: HashMap<String, HashMap<String, Vec<crate::export::NaturalKey>>>,
    /// **Las tablas que el seed de cada módulo siembra como MARCADOR DE POSICIÓN** (hub#1535):
    /// `module_id → tablas`. Las lee [`crate::seed::declared_placeholder_tables`] del mismo texto
    /// que se siembra, en el mismo sitio y con la misma vida que [`Self::seed_natural_keys`].
    ///
    /// Una tabla está aquí cuando la guarda de su seed es el hub entero (`WHERE hub_id = :hub_id`):
    /// el módulo declara así que planta un objeto completo y solo mientras el hub no tenga nada
    /// suyo. El import lo lee para retirar el marcador cuando llegan los datos del negocio.
    pub(crate) seed_placeholder_tables: HashMap<String, Vec<String>>,
    /// **The column types of every list's base SELECT**, asked of the database once per installed
    /// version instead of on every request (hub#2359). It lives here, and not in a `static`, for
    /// the same reason as [`Self::wasm_cache`]: its life IS the installed modules', and one
    /// registry serves exactly one database. Forgotten whole by `installer::register_module` before
    /// it migrates, the one door every schema change comes through — see
    /// [`crate::column_kinds_cache`].
    pub(crate) list_column_kinds: crate::column_kinds_cache::ColumnKindsCache,
}

impl Registry {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn is_installed(&self, module_id: &str) -> bool {
        self.installed.iter().any(|m| m.id == module_id)
    }

    /// Does the installed module declare that its data belongs to the installation that produced
    /// it? ([`crate::manifest::Manifest::installation_bound_data`], hub#380.)
    ///
    /// Asked of the module installed **in the destination hub**, which is where the import engine
    /// stands: the server installs the bundle's modules before the engine runs, so by then this is
    /// the manifest the data would be applied against. A module nobody installed answers `false` —
    /// its section cannot be applied anyway (`apply_section` fails it as not installed).
    pub fn is_installation_bound(&self, module_id: &str) -> bool {
        self.installed
            .iter()
            .any(|m| m.id == module_id && m.installation_bound_data)
    }

    /// Las claves naturales que algún módulo instalado declara, en su seed, sobre `table`
    /// (hub#842).
    ///
    /// Se pregunta por TABLA y no por módulo a propósito: un módulo solo puede escribir sus
    /// propias tablas (hub#633 lo valida al instalar), así que una tabla tiene un único dueño y la
    /// respuesta no puede mezclar declaraciones de dos módulos. Preguntar por tabla, además, es lo
    /// que sirve al import, que trabaja sobre el SQL de una sección y no siempre tiene un módulo
    /// (`data/hub_user_profile.sql`).
    pub(crate) fn seed_natural_keys_for(&self, table: &str) -> Vec<crate::export::NaturalKey> {
        self.seed_natural_keys
            .values()
            .filter_map(|by_table| by_table.get(table))
            .flatten()
            .cloned()
            .collect()
    }

    /// ¿Algún módulo instalado siembra `table` como MARCADOR DE POSICIÓN de tabla entera
    /// (hub#1535)?
    ///
    /// Por tabla y no por módulo, por lo mismo que [`Self::seed_natural_keys_for`]: una tabla
    /// tiene un único dueño (hub#633 lo valida al instalar) y el import trabaja sobre el SQL de
    /// una sección, no siempre sobre un módulo.
    pub(crate) fn seeds_placeholder_table(&self, table: &str) -> bool {
        self.seed_placeholder_tables
            .values()
            .any(|tables| tables.iter().any(|t| t == table))
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

    /// Registra las automatizaciones de fábrica de un módulo (hub#1611). Vacío = se olvidan las
    /// previas, que es lo que hace que **quitar** una plantilla de una versión nueva del módulo la
    /// retire de la galería: si se acumularan, se seguiría ofreciendo una que su autor ya no
    /// publica.
    pub fn set_flow_templates(&mut self, module_id: &str, scan: FlowTemplateScan) {
        if scan.is_empty() {
            self.flow_templates.remove(module_id);
        } else {
            self.flow_templates.insert(module_id.to_string(), scan);
        }
    }

    /// Registers the checkpoints a module declares (hub#1701). Empty = the previous ones are
    /// forgotten, just like the templates above: a checkpoint a new version of the module no longer
    /// declares stops being offered, instead of lingering there naming a command that may not exist
    /// any more.
    pub fn set_policy_checkpoints(&mut self, module_id: &str, scan: crate::policies::CheckpointScan) {
        if scan.is_empty() {
            self.policy_checkpoints.remove(module_id);
        } else {
            self.policy_checkpoints.insert(module_id.to_string(), scan);
        }
        self.rebuild_policy_command_index();
    }

    /// Rebuilds `command → checkpoint` from scratch. Cheap (a few dozen entries) and called only
    /// when installing/removing a module, never on a command's path.
    fn rebuild_policy_command_index(&mut self) {
        self.policy_checkpoint_by_command = self
            .policy_checkpoints
            .values()
            .flat_map(|scan| scan.checkpoints.iter())
            .map(|cp| (cp.command.clone(), cp.clone()))
            .collect();
    }

    /// The checkpoint that gates `command`, if an installed and **active** module declares it
    /// (hub#1701). It is what the gate reads, and that is why it is a map lookup and not a walk.
    ///
    /// Filtering by `is_active` is the same criterion as `navigation`: a paused module offers no
    /// screens and does not gate either. Its rules stay stored and apply again when it is
    /// reactivated.
    pub fn policy_checkpoint_for_command(
        &self,
        command: &str,
    ) -> Option<&crate::policies::PolicyCheckpoint> {
        self.policy_checkpoint_by_command
            .get(command)
            .filter(|cp| self.is_active(&cp.module_id))
    }

    /// The checkpoint with that `<module>/<name>`, if an active module offers it (hub#1701).
    /// It is the WRITE door that uses it, not the gate.
    pub fn policy_checkpoint_for_id(&self, id: &str) -> Option<&crate::policies::PolicyCheckpoint> {
        self.policy_checkpoint_by_command
            .values()
            .find(|cp| cp.id == id && self.is_active(&cp.module_id))
    }

    /// The checkpoints of **every** installed and active module (hub#1701).
    ///
    /// It filters by `is_active` with the same criterion as [`Self::flow_templates`]: a paused
    /// module offers no screens, and it must not offer places to put a rule on a command that
    /// cannot be run right now either. Stable order (module, then id) so the owner's screen does
    /// not dance between two requests.
    pub fn policy_checkpoints(&self) -> Vec<&crate::policies::PolicyCheckpoint> {
        let mut out: Vec<&crate::policies::PolicyCheckpoint> = self
            .policy_checkpoints
            .iter()
            .filter(|(module_id, _)| self.is_active(module_id))
            .flat_map(|(_, scan)| scan.checkpoints.iter())
            .collect();
        out.sort_by(|a, b| (&a.module_id, &a.id).cmp(&(&b.module_id, &b.id)));
        out
    }

    /// Las plantillas de **todos** los módulos instalados y activos, con su módulo de origen
    /// (hub#1611).
    ///
    /// Filtra por `is_active` con el mismo criterio que `navigation`: un módulo pausado no ofrece
    /// pantallas, y tampoco debe ofrecer automatizaciones que nombran commands que ahora mismo no
    /// se pueden ejecutar. El orden es estable (módulo, luego familia) para que la galería no baile
    /// entre dos peticiones.
    ///
    /// Y filtra por el **suelo de versión de cada plantilla** ([`Self::flow_template_floor_problem`]):
    /// una plantilla cuyo `requires.json` no se cumple no se ofrece, mientras el módulo que la trae
    /// sigue funcionando igual.
    pub fn flow_templates(&self) -> Vec<(&str, &ModuleFlowTemplate)> {
        let mut out: Vec<(&str, &ModuleFlowTemplate)> = self
            .flow_templates
            .iter()
            .filter(|(module_id, _)| self.is_active(module_id))
            .flat_map(|(module_id, scan)| {
                scan.templates.iter().map(move |t| (module_id.as_str(), t))
            })
            .filter(|(_, tpl)| self.flow_template_floor_problem(tpl).is_none())
            .collect();
        out.sort_by(|a, b| (a.0, &a.1.family).cmp(&(b.0, &b.1.family)));
        out
    }

    /// ¿Se cumple el suelo de versión que declara esta plantilla? (hub#1611)
    ///
    /// El suelo es **por plantilla** y a propósito NO es el `depends_on` del módulo: `whatsapp_inbox`
    /// fija `appointments >= 1.1.69` para su plantilla y su `depends_on` es solo `["customers"]`,
    /// porque la plantilla es opcional y el módulo funciona sin ella. Por eso esto decide si se
    /// OFRECE, y nunca si el módulo se instala.
    ///
    /// Un módulo que no está instalado vale `0.0.0` ([`Self::module_version`]), así que «no está»
    /// y «está pero es viejo» son el mismo «no se ofrece» sin un caso aparte.
    ///
    /// 🔴 **Falla cerrado.** Una versión que no se lee como triple —la del hub o la que pide la
    /// plantilla— deja la plantilla FUERA en vez de dentro: ofrecer una automatización cuyo suelo
    /// no se ha podido comprobar es ofrecer una que al ejecutarse nombra commands que este hub
    /// quizá no tiene, y el daño de no enseñarla es que el dueño no la ve.
    fn flow_template_floor_problem(&self, tpl: &ModuleFlowTemplate) -> Option<FlowTemplateDiscard> {
        // `requires` es un mapa: se recorre ORDENADO para que dos peticiones seguidas nombren
        // siempre el mismo vecino cuando falla más de uno.
        let mut needed: Vec<(&String, &String)> = tpl.requires.iter().collect();
        needed.sort();
        for (module_id, floor) in needed {
            // hub#2123: the neighbour travels as data too, so a module can name it without
            // parsing `detail`. `installed` is `None` only when the module is not installed.
            let installed = self
                .is_installed(module_id)
                .then(|| self.module_version(module_id));
            let discard = |code: &str, detail: String| {
                Some(FlowTemplateDiscard {
                    family: tpl.family.clone(),
                    code: code.to_string(),
                    detail,
                    requires: Some(FloorRequirement {
                        module: module_id.clone(),
                        floor: floor.clone(),
                        installed: installed.clone(),
                    }),
                })
            };
            if installed.is_none() {
                return discard(
                    FLOOR_MODULE_MISSING,
                    format!("necesita `{module_id}` >= {floor} y no está instalado"),
                );
            }
            // 🔴 hub#1649: un vecino PAUSADO cuenta como AUSENTE. Sus commands no se pueden
            // ejecutar ahora mismo, que es exactamente el motivo por el que un módulo pausado
            // tampoco ofrece las plantillas que trae él.
            if !self.is_active(module_id) {
                return discard(
                    FLOOR_MODULE_PAUSED,
                    format!("necesita `{module_id}` >= {floor} y está pausado"),
                );
            }
            let installed_version = self.module_version(module_id);
            match (
                crate::core_version::version_triple(&installed_version),
                crate::core_version::version_triple(floor),
            ) {
                (Some(installed), Some(min)) if installed >= min => {}
                (Some(_), Some(_)) => {
                    return discard(
                        FLOOR_MODULE_TOO_OLD,
                        format!(
                            "necesita `{module_id}` >= {floor} y hay {installed_version}"
                        ),
                    )
                }
                _ => {
                    return discard(
                        FLOOR_UNREADABLE,
                        format!(
                            "el suelo `{module_id}` >= {floor} no se lee como versión \
                             (instalada: {installed_version})"
                        ),
                    )
                }
            }
        }
        None
    }

    /// Las plantillas de fábrica que este hub **NO** ofrece, con su módulo de origen y su motivo
    /// (hub#1649).
    ///
    /// Es la otra mitad de [`Self::flow_templates`] y se responde con ella: una galería que solo
    /// dice lo que hay deja «este módulo no trae ninguna» y «la trae y el hub la ha descartado»
    /// exactamente iguales, y desde ahí no hay nadie —dueño, soporte o la autora del módulo— que
    /// pueda arreglar nada.
    ///
    /// Junta las dos familias de motivo, que se deciden en momentos distintos: lo que se descartó
    /// al LEER la carpeta (guardado al instalar) y lo que se descarta al SERVIR, porque depende de
    /// qué más hay instalado ahora mismo — el suelo de versión y el módulo pausado.
    pub fn flow_template_discards(&self) -> Vec<(&str, FlowTemplateDiscard)> {
        let mut out: Vec<(&str, FlowTemplateDiscard)> = Vec::new();
        for (module_id, scan) in &self.flow_templates {
            for discard in &scan.discards {
                out.push((module_id.as_str(), discard.clone()));
            }
            if !self.is_active(module_id) {
                // El módulo que las trae está pausado: sus plantillas no se ofrecen, y decirlo es
                // lo que separa «pausé el módulo» de «se ha roto algo».
                out.extend(scan.templates.iter().map(|tpl| {
                    (
                        module_id.as_str(),
                        FlowTemplateDiscard {
                            family: tpl.family.clone(),
                            code: OWNER_PAUSED.to_string(),
                            detail: format!("`{module_id}` está pausado"),
                            requires: None,
                        },
                    )
                }));
                continue;
            }
            for tpl in &scan.templates {
                if let Some(discard) = self.flow_template_floor_problem(tpl) {
                    out.push((module_id.as_str(), discard));
                }
            }
        }
        out.sort_by(|a, b| (a.0, &a.1.family, &a.1.code).cmp(&(b.0, &b.1.family, &b.1.code)));
        out
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
    /// Los handlers WASM que conviene tener compilados antes del primer cobro (hub#926):
    /// **uno por módulo**, con la versión instalada y sus bytes.
    ///
    /// Deduplica a propósito: los bytes del `.wasm` viven en cada `RegisteredCommand`, y un módulo
    /// declara muchos comandos contra el mismo handler (`sales` tiene 21). Precalentar por comando
    /// compilaría 21 veces lo mismo — costaría más que el problema que quita.
    pub fn handlers_to_warm_up(&self) -> Vec<(String, String, Option<Vec<u8>>)> {
        let mut seen: HashMap<&str, &Vec<u8>> = HashMap::new();
        for cmd in self.commands.values() {
            if let Some(bytes) = &cmd.wasm {
                seen.entry(cmd.module_id.as_str()).or_insert(bytes);
            }
        }
        seen.into_iter()
            .map(|(id, bytes)| (id.to_string(), self.module_version(id), Some(bytes.clone())))
            .collect()
    }

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
                    .any(|c| c.emit.iter().any(|e| e.event() == event_name));
            if declared {
                ids.insert(module.id.clone());
            }
        }
        ids.into_iter().collect()
    }

    /// Every event some installed module declares it emits, as `event name → declaring module
    /// ids` (both sorted). The whole-catalogue reading of [`Self::modules_emitting`], and it looks
    /// in the same two places for the same reason: `events.emits` and each command's `emit`,
    /// because hub#722 left a manifest that only carries the second as a warning, not a refusal.
    ///
    /// It is one half of the hub's event catalogue (hub#823) — what is DECLARED; the outbox
    /// contributes what was SEEN. Without this, the flow editor's «Cuando pase…» dropdown had to
    /// be seeded from a hand-written file that could never offer an event this hub emits and the
    /// file does not know.
    pub fn declared_events(&self) -> std::collections::BTreeMap<String, Vec<String>> {
        let mut events: std::collections::BTreeMap<String, std::collections::BTreeSet<String>> =
            std::collections::BTreeMap::new();
        for module in &self.installed {
            let command_emits = module
                .commands
                .values()
                .flat_map(|c| c.emit.iter().map(|e| e.event()));
            for event in module
                .events
                .emits
                .iter()
                .map(String::as_str)
                .chain(command_emits)
            {
                events
                    .entry(event.to_string())
                    .or_default()
                    .insert(module.id.clone());
            }
        }
        events
            .into_iter()
            .map(|(name, ids)| (name, ids.into_iter().collect()))
            .collect()
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
        // hub#926: el código compilado del módulo se va con él. Toda actualización pasa por aquí,
        // así que esto es lo que garantiza que la versión nueva no ejecute el binario de la vieja.
        self.wasm_cache.forget_module(module_id);
        self.status.remove(module_id);
        // hub#1611: sus automatizaciones de fábrica se van con él — una plantilla que sobreviviera
        // a su módulo se ofrecería para siempre, nombrando commands que este hub ya no tiene.
        self.flow_templates.remove(module_id);
        // hub#1701: its checkpoints go with it, for the same reason. The owner's RULES do not: they
        // are theirs and not the module's, so they survive an update (which is a remove + install)
        // and are in force again with the `reload_policies` that comes after. What keeps an orphaned
        // rule from gating anything is that the index is rebuilt by joining rows WITH checkpoints.
        self.policy_checkpoints.remove(module_id);
        self.rebuild_policy_command_index();
        self.queries.retain(|_, q| q.module_id != module_id);
        self.commands.retain(|_, c| c.module_id != module_id);
        self.navigation.retain(|n| n.module_id != module_id);
        self.locales.remove(module_id);
        self.seed_natural_keys.remove(module_id);
        self.seed_placeholder_tables.remove(module_id);
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
            flow_templates: self
                .flow_templates
                .get(module_id)
                .cloned()
                .unwrap_or_default(),
            policy_checkpoints: self
                .policy_checkpoints
                .get(module_id)
                .cloned()
                .unwrap_or_default(),
            seed_natural_keys: self
                .seed_natural_keys
                .get(module_id)
                .cloned()
                .unwrap_or_default(),
            seed_placeholder_tables: self
                .seed_placeholder_tables
                .get(module_id)
                .cloned()
                .unwrap_or_default(),
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
        self.set_flow_templates(&module_id, snapshot.flow_templates);
        self.set_policy_checkpoints(&module_id, snapshot.policy_checkpoints);
        if !snapshot.seed_natural_keys.is_empty() {
            self.seed_natural_keys
                .insert(module_id.clone(), snapshot.seed_natural_keys);
        }
        if !snapshot.seed_placeholder_tables.is_empty() {
            self.seed_placeholder_tables
                .insert(module_id.clone(), snapshot.seed_placeholder_tables);
        }
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
    /// The factory automations that were registered, and what the package's `flows/` folder
    /// had to discard (hub#1611, hub#1649). Without this, a failed update would restore the
    /// module WITHOUT its templates: the rollback puts the till back and silently drops the
    /// gallery entry until the next boot.
    flow_templates: FlowTemplateScan,
    /// The policy checkpoints the module declared (hub#1701). Same reason as the templates above:
    /// a failed update would otherwise put the till back WITHOUT the places where the owner's rules
    /// hang, and every rule written on one of them would stop being enforced until the next boot —
    /// silently, which is the one way a policy must never stop working.
    policy_checkpoints: crate::policies::CheckpointScan,
    /// `(event, command)` pairs whose command belongs to the module.
    listeners: Vec<(String, String)>,
    /// The natural keys the module's seed declares, per table (hub#842).
    seed_natural_keys: HashMap<String, Vec<crate::export::NaturalKey>>,
    /// The tables the module's seed plants as a whole-table placeholder (hub#1535).
    seed_placeholder_tables: Vec<String>,
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
    /// **This hub is an ephemeral DEMO** (`Registry::demo_hub`, sealed at boot from `HUB_DEMO`
    /// — ADR-0197, hub#1135). The dispatcher copies it here next to the business identity,
    /// EXACTLY the same pattern as [`Self::has_certificate`]: a hub condition a module needs in
    /// order to paint (verifactu#40 — do not offer "Production" in a demo that
    /// `enforce_fiscal_environment_pin` is always going to deny), sounded by the runtime and
    /// exposed as 0/1 so the SQL never reads a system table.
    ///
    /// It is a READ-ONLY copy for `system_params`, never the source of truth: the fiscal close
    /// (`fiscal_environment_pin`, `fiscal_profile::determine_fiscal_mode`…) keeps reading
    /// `Registry::demo_hub` DIRECTLY, not this field — for the same reason `Registry::demo_hub`
    /// itself documents: a `ctx` is a label a new door could forget to stamp, and the close
    /// cannot afford that fail-open. This field exists only so `system_params` has something to
    /// read; a caller never writes it — `system_params` overwrites it with the value from `ctx`
    /// after cloning the payload, exactly like `hub_id` or `has_certificate`.
    pub is_demo_hub: bool,
    /// **¿Están CONCEDIDAS todas las capabilities que declara el módulo que está llamando?**
    /// (ADR-0079, hub#1425). Lo sella el dispatcher —`commands::execute_at` y `queries::execute`,
    /// por módulo llamante— con [`crate::capabilities::all_granted`], que es [`enforce`] mismo;
    /// `system_params` lo expone como `:capabilities_granted` (0/1).
    ///
    /// MISMO patrón que [`Self::has_certificate`]: una condición del hub que el módulo necesita
    /// para PINTAR —verifactu#62: «estás activado y no puedes firmar»—, sonada por el runtime y
    /// nunca adivinada por el módulo, que además no puede leer `_module_capability_grants` (tabla
    /// de sistema, vedada por `migration_guard`).
    ///
    /// **Es 0/1 agregado, no la lista**: el módulo ya sabe qué declara (está en su manifest); lo
    /// que no sabe es si se lo han concedido. Un booleano cierra el caso sin publicar el mapa de
    /// permisos del hub a cualquier módulo instalado.
    ///
    /// El default es `false`, y es deliberado: sin sellar significa «no lo sé», y de las dos
    /// lecturas equivocadas la cara es la otra —una pantalla que calla mientras el módulo no puede
    /// firmar es exactamente el fallo que hub#1425 cierra; una que avisa de más se corrige mirando
    /// Ajustes → Permisos—. Nunca lo escribe quien llama: `system_params` lo sobrescribe DESPUÉS
    /// de clonar el payload, igual que `:hub_id`.
    pub capabilities_granted: bool,
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
    /// **La zona horaria del NEGOCIO** (hub#731, hub#1022), como nombre IANA (`Europe/Madrid`) y ya
    /// RESUELTA: la `timezone` declarada en settings o, lo normal, la deducida de
    /// `country_code`/`region_code` (`settings::timezone_of`). La inyecta el dispatcher junto a la
    /// identidad de negocio; `system_params` la expone como `:timezone` y el contexto de los
    /// handlers WASM/nativos como `context.timezone`, para que un módulo que agenda «mañana a las
    /// 09:00» sepa en qué reloj son las 09:00 sin adivinarlo del país. Vacía hasta que el
    /// dispatcher la resuelve — [`Self::timezone_name`] degrada a `UTC`, igual que el boot del
    /// server.
    pub timezone: String,
    /// **El idioma EFECTIVO de quien llama** (hub#1098): su override personal
    /// (`hub_user_pref.language`) → el setting del hub (`hub_settings.language`) → el default del
    /// core (`es`). Es la MISMA precedencia que el shell (`bootHubLanguage`) y la que taxes#38
    /// reimplementaba en el SQL de cada módulo — con el default adivinado, y mal (taxes#40: era
    /// `en` y el core dice `es`). La inyecta el dispatcher; `system_params` la expone como
    /// `:caller_lang` para que cualquier SELECT que proyecte texto traducido deje de leer las
    /// tablas del core. Vacía hasta resolver — [`Self::caller_lang`] degrada a `es`.
    pub caller_lang: String,
    /// **Who is behind this request**: a person, or a machine (hub#361). See [`Principal`].
    pub principal: Principal,
    /// Reference to a **step-up approval** this runtime is holding (hub#361), if the caller
    /// presented one (`X-Elevation-Token`). It is a lookup key into
    /// [`crate::elevation::Grants`] — **never** a claim: an unknown, expired or foreign token is
    /// indistinguishable from no token at all, and the payload is never read for it.
    pub elevation_token: Option<String>,
    /// **Which open shell sent this request** (hub#1980): the `X-Client-Instance` a shell tab makes
    /// for itself at load, read by the command door and nowhere else. It only NAMES — it grants
    /// nothing, and an unknown or absent one changes no decision of the dispatcher. It exists to
    /// travel on the live frames this request's events produce, so the till that charged a sale is
    /// the one that prints it: every shell hears `sale.completed`, and before this none could tell
    /// its own sales from the till next to it.
    ///
    /// `None` = nobody's shell (an API integration, a flow, a scheduled task, a listener).
    pub client_instance: Option<String>,
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
    /// **Which AEAT this hub files to** (`testing` | `production`) — `_hub_fiscal_profile.environment`
    /// (ADR-0273 D3: the go-live IS `testing → production`). Stamped by the dispatcher next to
    /// [`Self::fiscal_mode`], from the core's own tables.
    ///
    /// Private with a `pub(crate)` setter for the same reason as [`Self::automation`]: this
    /// struct crosses into `erplora-server`, where every context is built from something a
    /// caller sent. The certificate arm of `commands::enforce_fiscal_precondition` is keyed on
    /// this value (ADR-0360, hub#1087: in `testing` there is nothing to authorize), so a route
    /// able to stamp it would hand a TPV the very requirement the ADR exists to enforce. Empty
    /// means UNRESOLVED, and every gate that reads it fails CLOSED (production's answer).
    fiscal_environment: String,
    /// **What stops this hub from getting a record to the tax authority** (hub#1935) — the stable
    /// code of [`crate::fiscal_profile::filing_gap`], or `""` when nothing does. Stamped by the
    /// dispatcher next to [`Self::fiscal_environment`], from the core's own tables.
    ///
    /// Private with a `pub(crate)` setter for the same reason: a context built from what a caller
    /// sent must not be able to say «my road is fine» to the gate that refuses a sale nobody could
    /// file.
    fiscal_filing_gap: String,
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
    /// Ids of installed modules the SaaS entitlement no longer grants this hub (hub#1175):
    /// retired or revoked, per the hybrid revalidation that lives in `erplora-server`
    /// (`crate::entitlement` there, `RevalidationState::blocked_modules`). The runtime has no way
    /// to know this on its own — it has no view of the SaaS's signed claims, only of what is
    /// installed and active in THIS hub's own tables — so the server stamps the set on the way
    /// in, the same shape as [`Self::permissions`]. Empty by default: every context nobody
    /// populated (dev mode, tests, a machine principal, `erplora-server` builds that predate this
    /// field) keeps seeing every installed module unfiltered, exactly like today.
    ///
    /// `pub`, not `pub(crate)`: unlike [`Self::automation`] this carries no privilege — a caller
    /// that lied and claimed nothing is blocked would only get back the pre-hub#1175 behaviour
    /// (an item that points at a route the dispatcher's own entitlement gate still refuses), never
    /// an escalation.
    pub blocked_modules: HashSet<String>,
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

impl Principal {
    /// The name handlers receive in `context.principal` (hub#2113): the kernel TELLS a module
    /// whether a person or an automation is calling, so no module has to guess it from the shape
    /// of `current_user_id` — a guess that fails open the day a new machine caller appears.
    pub fn as_str(self) -> &'static str {
        match self {
            Principal::Human => "human",
            Principal::Machine => "machine",
        }
    }
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
            timezone: String::new(),
            caller_lang: String::new(),
            business_tax_id: String::new(),
            business_legal_name: String::new(),
            business_address: String::new(),
            has_certificate: false,
            capabilities_granted: false,
            is_demo_hub: false,
            fiscal_mode: None,
            fiscal_triggers: Vec::new(),
            fiscal_providers: Vec::new(),
            fiscal_environment: String::new(),
            fiscal_filing_gap: String::new(),
            principal: Principal::Human,
            elevation_token: None,
            client_instance: None,
            approved_by: None,
            automation: None,
            parent_event_id: String::new(),
            blocked_modules: HashSet::new(),
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

    /// Stamps which AEAT this hub files to (`testing` | `production`, hub#1087/ADR-0360). Only
    /// the dispatcher calls it, from `_hub_fiscal_profile` — `pub(crate)` is the point: see
    /// [`RequestContext::fiscal_environment`]. An empty value is UNRESOLVED and every gate that
    /// reads it fails CLOSED.
    pub(crate) fn with_fiscal_environment(mut self, environment: impl Into<String>) -> Self {
        self.fiscal_environment = environment.into();
        self
    }

    /// The fiscal environment the gate keys on (ADR-0360): `testing`, `production`, or `""` when
    /// unresolved (read as production — the conservative answer).
    pub fn fiscal_environment(&self) -> &str {
        &self.fiscal_environment
    }

    /// Stamps what stops this hub from filing (hub#1935). Only the dispatcher calls it — see
    /// [`RequestContext::fiscal_filing_gap`].
    pub(crate) fn with_fiscal_filing_gap(mut self, gap: Option<&str>) -> Self {
        self.fiscal_filing_gap = gap.unwrap_or_default().to_string();
        self
    }

    /// The stable code of what stops this hub from filing, or `""` when nothing does.
    pub fn fiscal_filing_gap(&self) -> &str {
        &self.fiscal_filing_gap
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

    /// Names the shell tab this request came from (hub#1980). See [`Self::client_instance`].
    pub fn with_client_instance(mut self, instance: impl Into<String>) -> Self {
        self.client_instance = Some(instance.into());
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

    /// Fija la **zona horaria resuelta del negocio** (hub#731, hub#1022). La llama el dispatcher
    /// tras `settings::timezone_of`. Builder para no romper los `new(...)`/tests existentes.
    pub fn with_timezone(mut self, timezone: impl Into<String>) -> Self {
        self.timezone = timezone.into();
        self
    }

    /// Fija el **idioma efectivo de quien llama** (hub#1098). La llama el dispatcher tras leer
    /// `hub_user_pref`/`hub_settings` (ver `effective_caller_lang`). Builder para no romper los
    /// `new(...)`/tests existentes.
    pub fn with_caller_lang(mut self, lang: impl Into<String>) -> Self {
        self.caller_lang = lang.into();
        self
    }

    /// La zona horaria del negocio como nombre IANA, lista para bindear/exponer. `UTC` si el
    /// dispatcher aún no la resolvió — el mismo fallback documentado del boot del server, nunca
    /// una cadena vacía que un `context.timezone` del guest leería como «no lo sé».
    pub fn timezone_name(&self) -> &str {
        if self.timezone.is_empty() {
            "UTC"
        } else {
            &self.timezone
        }
    }

    /// El idioma efectivo de quien llama, listo para bindear. `es` (el default del core,
    /// taxes#40) si el dispatcher aún no lo resolvió — nunca una cadena vacía.
    pub fn caller_lang(&self) -> &str {
        if self.caller_lang.is_empty() {
            "es"
        } else {
            &self.caller_lang
        }
    }

    /// Copia con el flag de presencia del certificado fiscal del negocio (`_hub_certificate`, core).
    /// Lo rellena el dispatcher junto a `with_business`. Builder para no romper los `new(...)`/tests.
    pub fn with_certificate(mut self, present: bool) -> Self {
        self.has_certificate = present;
        self
    }

    /// Copia con la respuesta de `capabilities::all_granted` para el módulo LLAMANTE (hub#1425).
    /// Solo la sella el dispatcher, por módulo y en cada dispatch; nunca quien llama. Builder para
    /// no romper los `new(...)`/tests.
    pub fn with_capabilities_granted(mut self, granted: bool) -> Self {
        self.capabilities_granted = granted;
        self
    }

    /// Copy with the hub's ephemeral DEMO mark (hub#1135). The dispatcher fills it next to
    /// `with_business`/`with_certificate`, reading `Registry::demo_hub` — never the caller. A
    /// builder so it does not break existing `new(...)`/tests.
    pub fn with_demo_hub(mut self, is_demo: bool) -> Self {
        self.is_demo_hub = is_demo;
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

    // ── hub#1094: invalid_payload_fields ───────────────────────────────────────────────────
    //
    // The Settings screen the shell generates for ANY module swallowed the 422: the user pressed
    // «Save», the request came back `invalid_payload` and the screen stayed exactly as it was. To
    // say WHICH field the runtime refused, the screen needs the field NAMES — and the house rule
    // is that such a list travels as a FIELD of the envelope, never parsed out of the sentence by
    // the client (same as `permission` in hub#360 and `dependents` in hub#1101).
    //
    // So the split lives HERE, one function below the `format!` that produces the detail. Producer
    // and reader are adjacent on purpose: they are the two halves of one format, and a test that
    // feeds `validate()`'s real output through it cannot drift apart in silence.

    /// The round trip that matters: what `CompiledSchema::validate` really emits, parsed back.
    #[test]
    fn field_names_survive_the_round_trip_from_a_real_validation_failure() {
        let schema = compiled(serde_json::json!({
            "type": "object",
            "properties": {
                "auto_bump_delay_seconds": { "type": "integer" },
                "default_order_type": { "type": "string", "enum": ["dine_in", "takeaway"] },
            },
            "required": ["auto_bump_delay_seconds", "default_order_type"],
        }));
        // Exactly the payload the generic form sends for a module that declares `required`
        // properties with no `default`: nulls and empty strings (hub#1094 causa 3).
        let detail = schema
            .validate(&serde_json::json!({
                "auto_bump_delay_seconds": null,
                "default_order_type": "",
            }))
            .expect_err("este payload NO cumple el schema");

        let mut fields = invalid_payload_fields(&detail);
        fields.sort();
        assert_eq!(
            fields,
            vec!["auto_bump_delay_seconds", "default_order_type"]
        );
    }

    /// A violation of the object ITSELF (a missing required key) has an empty instance path, so it
    /// names no field. It must not become a phantom entry: an empty name would mark no control on
    /// screen and the message would look like it had been understood when it had not.
    #[test]
    fn a_violation_with_no_instance_path_names_no_field() {
        let schema = compiled(serde_json::json!({
            "type": "object",
            "properties": { "warning_time_minutes": { "type": "integer" } },
            "required": ["warning_time_minutes"],
        }));
        let detail = schema
            .validate(&serde_json::json!({}))
            .expect_err("falta una propiedad obligatoria");

        assert!(
            invalid_payload_fields(&detail).is_empty(),
            "sin ruta de instancia no hay campo que nombrar, got {detail}"
        );
    }

    /// The refusals of the OTHER 25 doors that raise `InvalidPayload` by hand are free prose with
    /// no pointer in them (`device_mode`, `pin_policy`, `roles`…). They must yield nothing rather
    /// than a made-up field name.
    #[test]
    fn a_hand_written_refusal_without_pointers_yields_no_fields() {
        assert!(invalid_payload_fields("modo de dispositivo desconocido: `kiosko`").is_empty());
    }

    /// Nested pointers name their ROOT property: that is the control the form paints, and the one
    /// the screen can mark. Duplicates collapse — two violations of one field are one bad field.
    #[test]
    fn a_nested_pointer_names_the_root_property_once() {
        assert_eq!(
            invalid_payload_fields("/lines/0/qty: null is not of type \"integer\"; /lines/1/qty: null is not of type \"integer\""),
            vec!["lines"],
        );
    }

    /// RFC 6901: a property whose name carries `/` or `~` arrives escaped (`~1`, `~0`) in the
    /// pointer. The screen keys its controls by the RAW property name, so the escape has to be
    /// undone — and in the right order, or `a~1b` would come back as `a/b` twice removed.
    #[test]
    fn an_escaped_property_name_comes_back_unescaped() {
        assert_eq!(
            invalid_payload_fields("/rate~1kg: null is not of type \"number\"; /tilde~0x: bad"),
            vec!["rate/kg", "tilde~x"],
        );
    }

    // ── hub#1092: coerce_declared_number_shapes ─────────────────────────────────────────────

    fn compiled(schema: serde_json::Value) -> CompiledSchema {
        CompiledSchema::compile(&schema).expect("schema compila")
    }

    fn shape_of(v: &serde_json::Value) -> &'static str {
        // The WIRE form of a JSON number, which is what the binder keys on: serde_json keeps
        // integers and floats in separate variants even when they are equal as reals.
        let n = v.as_number().expect("es un número");
        if n.is_u64() || n.is_i64() {
            "int"
        } else if n.is_f64() {
            "float"
        } else {
            "???"
        }
    }

    /// `"number"` declara FLOTANTE: un `10` en JSON (entero para serde_json) se reescribe como
    /// `10.0` para que el bind salga siempre `float8`. Es la mitad que congela la sentencia.
    #[test]
    fn number_field_rewrites_integer_shaped_values_to_float() {
        let schema = compiled(serde_json::json!({
            "type": "object",
            "properties": { "rate": { "type": "number" } }
        }));
        let mut p = crate::Params::new();
        p.insert("rate".into(), serde_json::json!(10));
        schema.coerce_declared_number_shapes(&mut p);
        assert_eq!(shape_of(&p["rate"]), "float", "10 debe salir como 10.0");
        assert_eq!(p["rate"].as_f64(), Some(10.0), "mismo valor, otra forma");
    }

    /// `"integer"` declara ENTERO: un `4.0` (float que ES un integer válido para JSON Schema,
    /// el validador lo acepta) se reescribe como `4` para que el bind salga siempre `int8`.
    /// Un `4.5` no se toca: cambiarlo sería cambiar el VALOR, no la forma.
    #[test]
    fn integer_field_rewrites_integral_floats_and_leaves_fractions() {
        let schema = compiled(serde_json::json!({
            "type": "object",
            "properties": { "qty": { "type": "integer" } }
        }));
        let mut p = crate::Params::new();
        p.insert("qty".into(), serde_json::json!(4.0));
        schema.coerce_declared_number_shapes(&mut p);
        assert_eq!(shape_of(&p["qty"]), "int", "4.0 debe salir como 4");

        let mut p = crate::Params::new();
        p.insert("qty".into(), serde_json::json!(4.5));
        schema.coerce_declared_number_shapes(&mut p);
        assert_eq!(
            shape_of(&p["qty"]),
            "float",
            "4.5 no es integral: se queda como está"
        );
    }

    /// La forma nullable (`["number", "null"]`) es la misma declaración; strings, bools, `null`
    /// y claves sin declaración numérica nunca se tocan.
    #[test]
    fn nullable_number_form_coerces_but_non_numbers_are_untouched() {
        let schema = compiled(serde_json::json!({
            "type": "object",
            "properties": {
                "rate": { "type": ["number", "null"] },
                "note": { "type": "string" },
                "qty": { "type": ["integer", "null"] },
                "free": { "type": ["string", "null"] }
            }
        }));
        let mut p = crate::Params::new();
        p.insert("rate".into(), serde_json::json!(21));
        p.insert("note".into(), serde_json::json!("21"));
        p.insert("qty".into(), serde_json::json!(3.0));
        p.insert("free".into(), serde_json::json!(7));
        schema.coerce_declared_number_shapes(&mut p);
        assert_eq!(
            shape_of(&p["rate"]),
            "float",
            "['number','null'] declara number"
        );
        assert_eq!(p["note"], serde_json::json!("21"), "un string no se toca");
        assert_eq!(
            shape_of(&p["qty"]),
            "int",
            "['integer','null'] declara integer"
        );
        assert_eq!(
            p["free"],
            serde_json::json!(7),
            "sin tipo numérico declarado, el valor manda"
        );
    }

    /// Un `null` explícito sobre un campo `number` nullable sigue siendo `null`: se bindea como
    /// `DynNull` (inferido por contexto), que es correcto y no congela ningún tipo.
    #[test]
    fn explicit_null_stays_null() {
        let schema = compiled(serde_json::json!({
            "type": "object",
            "properties": { "rate": { "type": ["number", "null"] } }
        }));
        let mut p = crate::Params::new();
        p.insert("rate".into(), serde_json::Value::Null);
        schema.coerce_declared_number_shapes(&mut p);
        assert_eq!(p["rate"], serde_json::Value::Null);
    }

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
            on_unique: Default::default(),
        }
    }

    fn registry_with(name: &str, expose_api: bool, internal: bool) -> Registry {
        let mut reg = Registry::new();
        reg.status
            .insert("pricing".to_string(), ModuleStatus::Active);
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

    /// hub#2113: the wire names handlers read in `context.principal`. They are a contract with
    /// every module (appointments reads them), so they are pinned here, not only through an e2e.
    #[test]
    fn principal_wire_names_are_human_and_machine() {
        assert_eq!(Principal::Human.as_str(), "human");
        assert_eq!(Principal::Machine.as_str(), "machine");
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
        let reg = registry_with_setup_locale("inventory", &[("en", Some("Your catalog"), None)]);
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
