//! Parseo de `module.json` (el contrato declarativo del módulo). Espejo del JSON Schema
//! en `schemas/module.schema.json`. ARQUITECTURA.md §5.2.
use std::collections::HashMap;
use std::path::Path;

use crate::errors::{Result, RuntimeError};

#[derive(Debug, Clone, serde::Deserialize)]
pub struct Manifest {
    pub id: String,
    pub name: String,
    pub version: String,
    #[serde(default)]
    pub depends_on: Vec<String>,
    #[serde(default)]
    pub permissions: Vec<String>,
    #[serde(default)]
    pub role_permissions: HashMap<String, Vec<String>>,
    /// Business roles the module DECLARES for the vertical it serves (paso 2b, hub#351).
    ///
    /// The base catalogue of the hub is frozen at three keys (`admin`/`manager`/`employee`,
    /// [`crate::hub_users::BASE_ROLES`]) because renaming one would cost 24 repos, 24 version
    /// bumps and 24 republications. So a vertical does not rename the base: it adds on top of it.
    /// A restaurant needs Waiter · Bartender · Kitchen · Cashier; a salon needs Receptionist ·
    /// Stylist; both may want Accountant. Each of those is declared here by the module that
    /// invents it, and every one of them hangs from a base role through `extends`.
    ///
    /// Absent = the module declares no role of its own, which is the shape of the ~24 already
    /// published manifests: the block is **optional** and adding it never invalidates them.
    ///
    /// `role_permissions` is what actually GRANTS: a role's effective permissions are the union of
    /// what the installed modules give to that key, so a module may grant to a key another module
    /// declared (`sales` gives `waiter` `add_sale` but not `take_payment`). Declaring is naming a
    /// role; granting is a separate axis on purpose.
    ///
    /// Validated at install time by `installer::validate_role_declarations`.
    #[serde(default)]
    pub roles: Vec<RoleDef>,
    #[serde(default)]
    pub navigation: Vec<Nav>,
    #[serde(default)]
    pub migrations: Migrations,
    /// **Datos de referencia** que el módulo siembra al instalarse (ADR-0147; `taxes` lo usa desde
    /// ADR-0085 para las categorías fiscales canónicas). DML **idempotente por hub** —
    /// `WHERE NOT EXISTS` por la clave natural—, aplicado DESPUÉS de migrar, con `:hub_id`, `:now`
    /// y `:current_user_id` inyectados. Reinstalar no duplica.
    ///
    /// Es para datos que **todo hub necesita** y que no puede aportar el usuario: unidades de
    /// medida, categorías fiscales. No para datos de ejemplo — eso son las blueprints.
    #[serde(default)]
    pub seed: Migrations,
    #[serde(default)]
    pub queries: HashMap<String, QueryDef>,
    #[serde(default)]
    pub commands: HashMap<String, CommandDef>,
    /// Carpeta persistente del módulo dentro del árbol común `media/modules/`.
    ///
    /// El valor del manifest es solo un nombre de carpeta (nunca una ruta). El host decide el
    /// backend físico: disco en Hub Local y almacenamiento de objetos vía Cloud en Hub Cloud.
    /// Ausente = el módulo no puede escribir ficheros persistentes.
    #[serde(default)]
    pub static_files: Option<StaticFilesDef>,
    /// Widgets de dashboard que aporta el módulo (ADR-0054). Mapa `id.completo → WidgetDef`,
    /// misma convención que `queries`/`commands`. El shell del Hub los recolecta de TODOS los
    /// manifests instalados y los pinta en `<ok-widget-board>`. Vía declarativa (`kind`+`query`,
    /// render genérico del shell) o escape hatch a `component` (WC del propio módulo). El runtime
    /// no ejecuta nada por widget: solo transporta el contrato (el shell fetchea el `module.json`
    /// crudo, igual que `navigation`/`provides_slots`). Ver `architecture/hub/dashboard/widgets.md`.
    #[serde(default)]
    pub widgets: HashMap<String, WidgetDef>,
    /// Pantalla de **ajustes declarativa** del módulo (estilo widgets, ADR nuevo). El módulo declara
    /// el formulario (un JSON Schema) + a qué `get`/`set` del propio módulo llama; el shell lo pinta
    /// genéricamente. Escape-hatch a un Web Component propio (`component`) para lo estructural. El
    /// runtime no ejecuta nada por settings: solo transporta el contrato (el shell fetchea el
    /// `module.json` crudo, igual que `widgets`). Ausente = el módulo no expone ajustes declarativos.
    #[serde(default)]
    pub settings: Option<SettingsDef>,
    /// **Is this module configured?** (ADR-0063, extended by hub#369). The module declares a read
    /// query of its own plus the conditions its first row must meet; the runtime evaluates it and
    /// surfaces the result as one item of `hub.setup.status`.
    ///
    /// It used to be transported and nothing else — the shell fetched the raw `module.json` and ran
    /// the loop in the browser. The computation moved to the runtime, so the block is now PARSED
    /// here: one query, one source of truth, and the assistant and the checklist read the same
    /// thing. Absent = the module contributes no checklist item (the shape of 22 of the 24
    /// published manifests, which must keep installing untouched).
    #[serde(default)]
    pub setup: Option<SetupDef>,
    #[serde(default)]
    pub events: Events,
    /// Resumen del módulo para el routing del asistente (nivel 1). ARQUITECTURA.md §9.2b.
    #[serde(default)]
    pub agent: Option<Agent>,
    /// Conocimiento del módulo para RAG (§9.4) — aparcado/en diseño. Se captura tal cual.
    #[serde(default)]
    pub ai_context: Option<serde_json::Value>,
    /// Tareas programadas del módulo (ADR-0011). Cada una ejecuta un command del **propio
    /// módulo** cuando vence su `cron`, sin usuario (contexto de sistema). Se vuelcan a la tabla
    /// de sistema `_scheduled_tasks` al instalar (idempotente). Ver `scheduler.rs`.
    #[serde(default)]
    pub scheduled_tasks: Vec<ScheduledTaskDef>,
    /// Capacidad `host.notify` de alto nivel (ADR-0012): qué canales de notificación
    /// (`email`/`sms`/`whatsapp`) declara necesitar el módulo. El host resuelve DÓNDE viven
    /// los secretos/cuota por canal y por `tier`; el módulo solo declara qué canal usa.
    #[serde(default)]
    pub notify: Option<NotifyCapability>,
    /// Capacidad `http.fetch` mediada (ADR-0012, campo `network` ya en el schema): allowlist de
    /// hosts y secretos que el host inyecta. El WASM no tiene red; el runtime hace la llamada.
    /// **Deprecado** a favor de `capabilities.network`; se pliega en `capabilities` al cargar.
    #[serde(default)]
    pub network: Option<NetworkCapability>,
    /// Permisos que el módulo SOLICITA al host (ADR-0079, estilo Android). Bloque vacío/ausente =
    /// el módulo no pide nada. NO confundir con `permissions` (RBAC de usuario). El usuario los
    /// concede explícitamente; el host media. Consolida los `network`/`notify` de ADR-0012.
    #[serde(default)]
    pub capabilities: Capabilities,
    /// **The fiscal regime this module IMPLEMENTS** (ADR-0259 D6, hub#555). Only declared by
    /// whoever implements one; an inventory module declares nothing.
    ///
    /// It is the answer to the core's single question — *«is there any installed and active module
    /// fulfilling the regime THIS hub owes?»* ([`crate::fiscal_profile`]). The core **counts**, it
    /// does not choose: the marketplace may carry N modules of one regime, swapping one for another
    /// is the user's call, and the profile deliberately does not store which one is in use.
    ///
    /// **This is not the opt-in flag ADR-0203 rejected.** That one would have been a `fiscal: true`
    /// a module could FORGET, emitting without a gate. Here the direction is inverted: declaring
    /// turns nothing off — it is what the core *requires to exist*. A module that does not declare
    /// simply does not count as a provider, and the hub stays blocked. Fail-closed, the same shape
    /// as `capabilities.certificate`, which likewise makes the gate stricter rather than laxer.
    ///
    /// Absent in all 24 published manifests, and it must stay valid there: absence means "I am not
    /// a fiscal provider", which is simply true of them.
    #[serde(default)]
    pub fiscal_regime: Option<FiscalRegimeDef>,
}

/// Bloque `fiscal_regime` del manifest (ADR-0259 D6): qué régimen fiscal, y de qué país, cumple
/// este módulo. `{ "country": "ES", "regime": "verifactu" }`.
#[derive(Debug, Clone, serde::Deserialize)]
pub struct FiscalRegimeDef {
    /// ISO-3166-1 alpha-2 — la misma forma con la que se compara: `hub_settings.country_code` y
    /// `_hub_fiscal_regime_registry.country_code`.
    pub country: String,
    /// Clave del régimen (`verifactu`, `facturx`…), la misma que el registro de regímenes del core.
    pub regime: String,
}

/// Acción que un **usuario** puede intentar sobre un fichero o carpeta desde la pantalla `/files`.
///
/// Ver y descargar NO están aquí: son siempre posibles (con sesión y permiso de lectura). Esta
/// enumeración cubre solo lo que **modifica** el contenido, que es lo que un módulo debe conceder
/// explícitamente (ADR-0172).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum UserFileAction {
    /// Subir ficheros o crear subcarpetas dentro de la carpeta del módulo.
    Upload,
    /// Renombrar un fichero o una subcarpeta.
    Rename,
    /// Borrar un fichero o una subcarpeta.
    Delete,
}

impl UserFileAction {
    /// Nombre declarativo tal y como aparece en `module.json`.
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Upload => "upload",
            Self::Rename => "rename",
            Self::Delete => "delete",
        }
    }

    /// Todas las acciones, para construir la política de una carpeta sin módulo dueño.
    pub const ALL: [Self; 3] = [Self::Upload, Self::Rename, Self::Delete];
}

/// A business role declared by a module (`roles[]`, paso 2b / hub#351). Mirror of `$defs/role` in
/// `schemas/module.schema.json`; the three fields are required there and here, so a half-declared
/// role never reaches the validation.
#[derive(Debug, Clone, serde::Deserialize)]
pub struct RoleDef {
    /// Stable identifier of the role (`waiter`, `shift_lead`). It is the key `role_permissions`
    /// grants against and the value stored in `hub_user.role`, so it is an identifier, not a
    /// label: snake_case ASCII, and never one of the base keys.
    pub key: String,
    /// Human name shown to the administrator who activates the role. **English canonical**
    /// (ADR-0055): the translation travels in `locales/<lang>.json`, like `navigation[].label`.
    pub label: String,
    /// Base role this one hangs from — the reason the frozen three-key contract survives: every
    /// declared role resolves to a base one, so the core gate and the 24 published modules keep
    /// working without a republish or a migration.
    ///
    /// Only the NON-administrative base roles can be extended (`manager`, `employee`). See
    /// `installer::validate_role_declarations`: administering the hub is granted by the hub, never
    /// by a manifest (hub#347).
    pub extends: String,
}

/// Almacenamiento persistente declarado por un módulo.
///
/// El nombre se valida también en el toolkit y en el runtime porque el manifest instalado es una
/// frontera de seguridad. Se resuelve siempre como `media/modules/<folder>/`.
#[derive(Debug, Clone, serde::Deserialize)]
pub struct StaticFilesDef {
    pub folder: String,
    /// Qué puede hacer el **usuario** con estos ficheros desde `/files`. Ausente o vacío =
    /// **solo ver y descargar**, que es el default deliberado: los documentos que genera un
    /// módulo suelen ser evidencia (los XML de VeriFactu son inalterables por ley) y borrarlos a
    /// mano desde un gestor de archivos no puede ser el camino fácil.
    ///
    /// No limita al módulo: este sigue escribiendo por `ModuleStorage`/`NativeHost`. Es la
    /// diferencia entre "el módulo guarda su XML" y "el cajero puede borrarlo".
    #[serde(default)]
    pub user_actions: Vec<String>,
}

impl StaticFilesDef {
    /// Un solo segmento portable: minúsculas ASCII, dígitos, `_` y `-`; sin separadores ni `..`.
    pub fn is_valid_folder(&self) -> bool {
        let mut chars = self.folder.chars();
        matches!(chars.next(), Some(c) if c.is_ascii_lowercase())
            && self.folder.len() <= 64
            && chars.all(|c| c.is_ascii_lowercase() || c.is_ascii_digit() || c == '_' || c == '-')
    }

    /// `true` si el módulo concedió esa acción. Una acción que el host no conoce simplemente no
    /// concede nada (compatibilidad hacia adelante: un manifest más nuevo no rompe un hub viejo,
    /// y tampoco le abre una puerta que no entiende).
    pub fn allows(&self, action: UserFileAction) -> bool {
        self.user_actions.iter().any(|a| a == action.as_str())
    }
}

/// Una tarea programada declarada en el manifest (ADR-0011). Espejo de `$defs/scheduledTask`
/// en `schemas/module.schema.json`. El `command` debe pertenecer al **propio módulo** (mismo
/// aislamiento que el handler WASM); se valida al volcar la tarea a `_scheduled_tasks`.
#[derive(Debug, Clone, serde::Deserialize)]
pub struct ScheduledTaskDef {
    /// Nombre único de la tarea **dentro del módulo** (clave de idempotencia con `module_id`).
    pub name: String,
    /// Command del propio módulo a ejecutar al vencer el cron (sin usuario).
    pub command: String,
    /// Expresión cron de 5 campos (`min hora dom mes dow`) o atajo (`@daily`, `@hourly`…).
    /// Ver `scheduler::cron` para la gramática soportada.
    pub cron: String,
    /// Payload fijo que recibe el command en cada ejecución (opcional).
    #[serde(default)]
    pub payload: Option<serde_json::Value>,
    /// Comportamiento de catch-up tras un apagado (ADR-0011): `collapse` (por defecto) ejecuta
    /// **una sola vez** el backlog al arrancar; `skip` no ejecuta nada vencido durante el apagado
    /// y solo reprograma. (No hay modo "run-all": el ADR fija collapse para tareas idempotentes.)
    #[serde(default)]
    pub catch_up: CatchUp,
}

/// Política de catch-up de una scheduled task tras un periodo apagado (ADR-0011).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default, serde::Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum CatchUp {
    /// Ejecuta una sola vez si había backlog vencido (idempotente). Por defecto.
    #[default]
    Collapse,
    /// No ejecuta el backlog; solo reprograma al siguiente vencimiento.
    Skip,
}

/// Bloque `notify` del manifest (ADR-0012): los canales de alto nivel que usa el módulo.
#[derive(Debug, Clone, serde::Deserialize)]
pub struct NotifyCapability {
    /// Canales declarados (`email`/`sms`/`whatsapp`).
    #[serde(default)]
    pub channels: Vec<String>,
}

/// Bloque `network` del manifest (ADR-0012, §5.5): allowlist de `http.fetch` mediado.
#[derive(Debug, Clone, serde::Deserialize)]
pub struct NetworkCapability {
    /// Hosts/patrones permitidos para las llamadas salientes mediadas por el host.
    #[serde(default)]
    pub allow: Vec<String>,
    /// Nombres de secretos del hub que el host inyecta en las llamadas (no su valor).
    #[serde(default)]
    pub secrets: Vec<String>,
}

/// Bloque `capabilities` del manifest (ADR-0079): los permisos que el módulo SOLICITA al host.
/// Consolida los antiguos `network`/`notify` (ADR-0012) y añade `certificate`/`printer`. El
/// usuario los concede explícitamente (toggle en Settings); el host media. Vacío = no pide nada.
#[derive(Debug, Clone, Default, serde::Deserialize)]
pub struct Capabilities {
    #[serde(default)]
    pub network: Option<NetworkCapability>,
    #[serde(default)]
    pub certificate: Option<CertificateCapability>,
    #[serde(default)]
    pub printer: Option<PrinterCapability>,
    #[serde(default)]
    pub notify: Option<NotifyCapability>,
}

/// Acceso al certificado PKCS#12 del negocio (firma/transmisión fiscal). El host firma; el
/// módulo nunca recibe la clave privada.
#[derive(Debug, Clone, serde::Deserialize)]
pub struct CertificateCapability {
    /// Para qué se usa (texto legible, p.ej. `fiscal-sign`).
    #[serde(default)]
    pub purpose: Option<String>,
}

/// Acceso a impresora ESC/POS vía el bridge/peripherals. Marcador sin parámetros (de momento).
#[derive(Debug, Clone, Default, serde::Deserialize)]
pub struct PrinterCapability {}

/// Clases de capability que el host conoce y puede gatear (ADR-0079). El nombre canónico (kebab)
/// es la clave de grant en `_module_capability_grants` y la etiqueta de la UI.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum CapabilityKind {
    Network,
    Certificate,
    Printer,
    Notify,
}

impl CapabilityKind {
    /// Nombre canónico estable (clave de grant + de UI).
    pub fn as_str(self) -> &'static str {
        match self {
            CapabilityKind::Network => "network",
            CapabilityKind::Certificate => "certificate",
            CapabilityKind::Printer => "printer",
            CapabilityKind::Notify => "notify",
        }
    }
    /// Parsea un nombre canónico; `None` si no es una capability conocida.
    pub fn parse(s: &str) -> Option<Self> {
        match s {
            "network" => Some(CapabilityKind::Network),
            "certificate" => Some(CapabilityKind::Certificate),
            "printer" => Some(CapabilityKind::Printer),
            "notify" => Some(CapabilityKind::Notify),
            _ => None,
        }
    }
}

impl Manifest {
    /// Capabilities que el módulo SOLICITA, plegando los campos `network`/`notify` top-level
    /// deprecados (ADR-0012) dentro del modelo `capabilities` (ADR-0079). El bloque
    /// `capabilities` tiene precedencia. Orden estable para UI.
    pub fn requested_capabilities(&self) -> Vec<CapabilityKind> {
        let mut out = Vec::new();
        if self.capabilities.network.is_some() || self.network.is_some() {
            out.push(CapabilityKind::Network);
        }
        if self.capabilities.certificate.is_some() {
            out.push(CapabilityKind::Certificate);
        }
        if self.capabilities.printer.is_some() {
            out.push(CapabilityKind::Printer);
        }
        if self.capabilities.notify.is_some() || self.notify.is_some() {
            out.push(CapabilityKind::Notify);
        }
        out
    }

    /// ¿El módulo declara necesitar esta capability? (incluye los alias deprecados).
    pub fn requests_capability(&self, kind: CapabilityKind) -> bool {
        self.requested_capabilities().contains(&kind)
    }

    /// Does this module fulfil `regime` for `country`? (ADR-0259 D6, hub#555.)
    ///
    /// This is the predicate the fiscal profile **counts** with — never "is this module
    /// `verifactu`". The country is part of it on purpose: a French Factur-X provider is not a
    /// VeriFactu provider for a Spanish hub. Country comparison is case-insensitive because
    /// `hub_settings.country_code` is normalised to upper case while a manifest is typed by hand.
    ///
    /// A module with no `fiscal_regime` block fulfils nothing, which is the whole fail-closed
    /// property: staying silent never counts as complying.
    pub fn fulfils_regime(&self, country: &str, regime: &str) -> bool {
        self.fiscal_regime.as_ref().is_some_and(|f| {
            f.country.eq_ignore_ascii_case(country.trim()) && f.regime.trim() == regime.trim()
        })
    }
}

/// Bloque `settings` del manifest: la pantalla de ajustes declarativa del módulo. El shell pinta un
/// formulario genérico a partir del `schema` (JSON Schema: campos/tipos/defaults/`title`/`enum`),
/// lo carga con la query `get` y lo guarda con el command `set` (ambos del propio módulo, que ya
/// existen). Si `component` está presente, el shell pinta ese Web Component en vez del form genérico
/// (escape-hatch para ajustes estructurales, p.ej. la estructura del ticket).
#[derive(Debug, Clone, serde::Deserialize)]
pub struct SettingsDef {
    /// Título de la sección de ajustes (legible).
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub title: Option<String>,
    /// Icono ionicons para la sección/pestaña.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub icon: Option<String>,
    /// Ruta (relativa al paquete del módulo) del JSON Schema que describe el formulario.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub schema: Option<String>,
    /// Query del propio módulo que devuelve los valores actuales (fila singleton). P.ej. `cash_register.settings.get`.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub get: Option<String>,
    /// Command del propio módulo que persiste (upsert del snapshot). P.ej. `cash_register.settings.update`.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub set: Option<String>,
    /// Escape-hatch: Web Component propio que el shell pinta en vez del form genérico (lo estructural).
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub component: Option<String>,
}

/// `setup` block of the manifest: the module's own answer to "am I configured?" (ADR-0063, extended
/// by hub#369). Mirror of `setup` in `schemas/module.schema.json`.
///
/// The runtime runs [`query`](Self::query) through the dispatcher — with the caller's permissions,
/// against real data, zero mocks — takes the FIRST row and evaluates
/// [`configured_when`](Self::configured_when). All checks pass ⇒ configured; a missing row ⇒ not
/// configured. The result becomes one item of `hub.setup.status`.
///
/// What a module may NOT declare is how important it is. `required` maps to 🔴 functional / 🟡
/// recommended, and the ⛔ blocking level stays core-owned (`setup_status`), so a third-party module
/// cannot proclaim itself a blocker of the sale.
#[derive(Debug, Clone, serde::Deserialize)]
pub struct SetupDef {
    /// Namespaced read query of the module itself that reports the configuration state.
    pub query: String,
    /// Static params for [`query`](Self::query).
    #[serde(default)]
    pub params: serde_json::Map<String, serde_json::Value>,
    /// Configured ⇔ ALL of these pass on the first row. Empty ⇒ merely having a row is enough.
    #[serde(default)]
    pub configured_when: Vec<SetupCheck>,
    /// Alert title, **English canonical** (ADR-0055) — the translation travels in
    /// `locales/<lang>.json` under `setup.title`.
    pub title: String,
    /// Short help text, English canonical (`locales/<lang>.json` → `setup.description`).
    #[serde(default)]
    pub description: String,
    /// Ionicons name for the item.
    #[serde(default)]
    pub icon: String,
    /// Screen that completes the item.
    pub route: String,
    /// Permission needed to configure it. Only whoever can act is told about it: an item a cashier
    /// cannot clear is noise, and the query would reject them anyway.
    #[serde(default)]
    pub permission: String,
    /// Countries this item applies to (ISO-3166-1 alpha-2). Empty = every country.
    ///
    /// The Hub is international and knows no concrete module, so "VeriFactu does not show outside
    /// Spain" cannot be a rule hardcoded in the core: the module that carries a national obligation
    /// declares where it applies.
    #[serde(default)]
    pub countries: Vec<String>,
    /// Slot in the checklist. The scale belongs to the core (see `setup_status`), which reserves
    /// the positions of its own items; a module takes the slot the core assigned to it. Absent =
    /// after everything the core placed.
    #[serde(default)]
    pub order: Option<i64>,
    /// `true` (the default) = 🔴 functional; `false` = 🟡 recommended. Never ⛔: that list is
    /// core-owned.
    #[serde(default = "default_true")]
    pub required: bool,
}

fn default_true() -> bool {
    true
}

/// One check of [`SetupDef::configured_when`] against a column of the first row. Exactly one of
/// `truthy`/`equals` per entry; neither ⇒ the check never passes (a half-written contract must not
/// silently tick the item as done).
#[derive(Debug, Clone, serde::Deserialize)]
pub struct SetupCheck {
    /// Column of the result to evaluate.
    pub field: String,
    /// Passes when the field is truthy (`truthy: false` inverts it).
    #[serde(default)]
    pub truthy: Option<bool>,
    /// Passes when the field equals this value (lax, compared as text).
    #[serde(default)]
    pub equals: Option<serde_json::Value>,
}

/// Bloque `agent` del manifest: descripción del módulo (en inglés) para el routing del
/// asistente y palabras clave opcionales para pre-filtro léxico. ARQUITECTURA.md §9.2b.
#[derive(Debug, Clone, serde::Deserialize)]
pub struct Agent {
    pub description: String,
    #[serde(default)]
    pub keywords: Vec<String>,
}

/// Una lectura pre-cargada (ADR-0069). Dos formas, y la primera es la de siempre:
///
/// ```json
/// "reads": [
///   "taxes.rules.list",
///   { "query": "inventory.products.unit_of", "params": { "product_id": "payload.product_id" } }
/// ]
/// ```
///
/// **Sin parámetros** (string) el handler recibe la query entera — sirve para catálogos pequeños
/// como las reglas de IVA. **Con parámetros** recibe solo la fila que le importa, que es lo que
/// hacía falta para validar contra el dato concreto: sin esto, un handler podía pedir «todas las
/// reglas» pero no «la unidad de ESTE producto», y cualquier validación por fila se quedaba sin
/// sitio — en el SQL no vale (un `WHERE` que no casa responde `ok`, no error) y pedírselo al
/// cliente rompe que el servidor sea la autoridad.
///
/// Los valores de `params` referencian el **payload del command** (`payload.<campo>`). Solo eso:
/// nada de expresiones ni de leer otras reads, para que el manifest siga siendo declarativo y
/// auditable de un vistazo.
#[derive(Debug, Clone, serde::Deserialize)]
#[serde(untagged)]
pub enum ReadDef {
    /// `"taxes.rules.list"` — la query entera, sin filtrar.
    Query(String),
    /// `{ "query": …, "params": { … } }` — filtrada por campos del payload.
    Parameterized {
        query: String,
        #[serde(default)]
        params: HashMap<String, String>,
    },
}

impl ReadDef {
    /// El nombre de la query, sea cual sea la forma.
    pub fn query(&self) -> &str {
        match self {
            ReadDef::Query(q) => q,
            ReadDef::Parameterized { query, .. } => query,
        }
    }
    /// Resuelve los parámetros contra el payload del command. `payload.<campo>` toma un campo de
    /// primer nivel; cualquier otra cosa se pasa como literal (útil para constantes).
    pub fn resolve_params_from_map(&self, payload: &erplora_db::Params) -> erplora_db::Params {
        let mut out = erplora_db::Params::new();
        if let ReadDef::Parameterized { params, .. } = self {
            for (name, expr) in params {
                let value = match expr.strip_prefix("payload.") {
                    Some(field) => payload
                        .get(field)
                        .cloned()
                        .unwrap_or(serde_json::Value::Null),
                    None => serde_json::Value::String(expr.clone()),
                };
                out.insert(name.clone(), value);
            }
        }
        out
    }
}

/// Operation supported by the declarative affected-rows contract (hub#139).
#[derive(Debug, Clone, Copy, PartialEq, Eq, serde::Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum ExpectRowsOp {
    Min,
}

/// Gate of a declarative SQL command (hub#139) that turns an `UPDATE ... WHERE` matching fewer
/// rows than expected into a stable business rejection instead of an ambiguous `200 ok`.
#[derive(Debug, Clone, serde::Deserialize)]
pub struct ExpectRows {
    pub op: ExpectRowsOp,
    pub n: u64,
    /// Namespaced code the caller programs/translates against (`inventory.insufficient_stock`).
    pub error: String,
    /// Optional human fallback. When omitted, the runtime generates one without internal data.
    #[serde(default)]
    pub message: Option<String>,
}

#[derive(Debug, Clone, Default, serde::Deserialize)]
pub struct Migrations {
    #[serde(default)]
    pub sqlite: Vec<String>,
    #[serde(default)]
    pub postgres: Vec<String>,
}

#[derive(Debug, Clone, serde::Deserialize)]
pub struct Nav {
    pub id: String,
    pub label: String,
    #[serde(default)]
    pub icon: Option<String>,
    pub component: String,
    /// Acciones de topbar de esta pestaña: el shell las pinta en `slot="end"` y al pulsar
    /// reenvía `module-action` al Web Component montado. El manifest declara el botón;
    /// el comportamiento vive en el componente del módulo.
    #[serde(default)]
    pub actions: Vec<NavAction>,
}

#[derive(Debug, Clone, serde::Deserialize)]
pub struct NavAction {
    pub id: String,
    pub label: String,
    #[serde(default)]
    pub icon: Option<String>,
    /// Botón destacado (color primario).
    #[serde(default)]
    pub primary: bool,
    /// Permiso para MOSTRAR el botón (show/hide de UI; Rust revalida siempre el command real).
    #[serde(default)]
    pub permission: Option<String>,
}

/// Un widget de dashboard declarado en el manifest (ADR-0054). Espejo de `$defs/widget` en
/// `schemas/module.schema.json`. El módulo declara metadatos (título/icono/categoría/tamaño,
/// `sectors`+`default` para la diferenciación por tipo de negocio) y EXACTAMENTE UNA de las dos
/// vías de render: declarativa (`kind` + `query` + `map`/`options`/`params`) o `component` (WC
/// propio). El runtime no ejecuta nada por widget; solo parsea y transporta el contrato (el shell
/// fetchea el `module.json` crudo y construye el `WidgetDef` de `ok-widget-board`).
///
/// CERO MOCKS (directriz del proyecto): la vía declarativa SIEMPRE se alimenta de una `query` real
/// del módulo; un widget sin datos reales no se inventa, se omite. La regla "exactamente uno de
/// { kind, component }" la valida el JSON Schema (no este struct, permisivo por compat hacia
/// adelante igual que el resto del fichero).
#[derive(Debug, Clone, serde::Deserialize, serde::Serialize)]
pub struct WidgetDef {
    /// Título mostrado en el board y en el selector. OBLIGATORIO.
    pub title: String,
    /// Nombre de icono ionicons para el selector (p. ej. `trending-up-outline`).
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub icon: Option<String>,
    /// Grupo en el selector (p. ej. "Ventas", "Inventario").
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub category: Option<String>,
    /// Tamaño en la rejilla de 12 columnas (`sm`=3, `md`=6, `lg`=8). Por defecto `md`.
    #[serde(default)]
    pub size: WidgetSize,
    /// Permiso para ver el widget (se filtra en cliente; la `query` lo revalida server-side).
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub permission: Option<String>,
    /// Tipos de negocio a los que aplica (`hosteleria`/`retail`/`gestoria`/`rrhh`/`general`).
    /// Ausente/vacío = todos.
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub sectors: Vec<String>,
    /// Sugerido ACTIVO cuando el sector del hub coincide con `sectors` (preset "Recomendado").
    #[serde(default)]
    pub default: bool,
    /// Refresco EN VIVO (ADR-0054 T1): eventos de dominio cuya emisión re-ejecuta la `query` de
    /// este widget. El shell se suscribe al canal push existente (Outbox→broadcast) y re-consulta
    /// con debounce. Ausente/vacío = el widget se monta una vez. El Hub solo TRANSPORTA el campo
    /// (el shell lee el `module.json` crudo); aquí se declara para no perderlo en un round-trip.
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub refresh_on: Vec<String>,
    /// Tipo de render declarativo. Mutuamente excluyente con `component` (lo valida el schema).
    /// Si está presente, `query` es obligatoria.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub kind: Option<WidgetKind>,
    /// Query YA declarada del módulo que alimenta el widget (vía declarativa). Nombre completo
    /// namespaced (p. ej. `sales.metrics.today`).
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub query: Option<String>,
    /// Params estáticos pasados a la `query` (opcional).
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub params: Option<serde_json::Value>,
    /// Mapeo COLUMNA del resultado → prop del widget (`prop → nombreColumna`). Las props válidas
    /// dependen del `kind` (ver `architecture/hub/dashboard/widgets.md`). Permisivo aquí.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub map: Option<serde_json::Value>,
    /// Props LITERALES estáticas (label, icon, format, currency, …). El shell parte de `options`
    /// y luego sobreescribe con lo resuelto por `map` desde los datos.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub options: Option<serde_json::Value>,
    /// Escape hatch: custom element del propio módulo (de su `ui.entry`). Mutuamente excluyente
    /// con `kind`. El shell lo carga con la misma maquinaria que `provides_slots`/`module-loader`
    /// y el WC consulta sus datos vía el cliente del Hub.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub component: Option<String>,
}

/// Tamaño de un widget en la rejilla de 12 columnas del dashboard. `sm`=3, `md`=6, `lg`=8.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default, serde::Deserialize, serde::Serialize)]
#[serde(rename_all = "lowercase")]
pub enum WidgetSize {
    Sm,
    #[default]
    Md,
    Lg,
}

/// Tipo de render declarativo de un widget → componente OutfitKit que el shell construye.
/// Cada `kind` acepta un conjunto distinto de columnas en `map` y props en `options`
/// (contrato en `architecture/hub/dashboard/widgets.md`).
#[derive(Debug, Clone, Copy, PartialEq, Eq, serde::Deserialize, serde::Serialize)]
#[serde(rename_all = "lowercase")]
pub enum WidgetKind {
    /// `ok-kpi` — valor único con delta/trend.
    Kpi,
    /// `ok-stat` — valor único con label/severity.
    Stat,
    /// `ok-kpi`+`ok-sparkline` (o `ok-sparkline` suelto) — serie numérica por filas.
    Sparkline,
    /// `ok-bar-list` — lista label/valor.
    #[serde(rename = "bar-list")]
    BarList,
    /// `ok-timeline` — eventos cronológicos.
    Timeline,
    /// `ok-chart` — serie única (multi-serie → usar `component`).
    Chart,
}

#[derive(Debug, Clone, serde::Deserialize)]
pub struct QueryDef {
    pub permission: String,
    pub sql: String,
    #[serde(default)]
    pub schema: Option<String>,
    /// Si está presente, la query es **paginada/lista**: el runtime envuelve el SELECT base
    /// como subconsulta y compone búsqueda + filtro por columna + orden (whitelist) +
    /// LIMIT/OFFSET, devolviendo `{rows,total,limit,offset}`. ARQUITECTURA.md §4, §8.2.
    #[serde(default)]
    pub list: Option<ListSpec>,
    /// Si está presente, expone esta query al asistente como tool (nivel 2). El permiso y el
    /// schema se heredan de la propia query, no se redeclaran. ARQUITECTURA.md §9.2.
    #[serde(default)]
    pub ai: Option<AiTool>,
    /// Opt-in: expone esta query en la **API pública REST/OpenAPI** por módulo (ADR-0057,
    /// `architecture/hub/public-api.md`). Doble puerta: además de este flag, la API key debe
    /// tener el `permission` de la query (lectura del módulo). Por defecto `false` → la query no
    /// es accesible vía API key aunque la key tuviera el permiso. El gate del runtime no cambia.
    #[serde(default)]
    pub expose_api: bool,
}

/// Contrato declarativo de una query de lista (`list` en `module.json`). Espejo de
/// `$defs/listSpec` en `schemas/module.schema.json`. El runtime lo consume en `queries.rs`
/// para componer el SQL paginado. ARQUITECTURA.md §4, §8.2.
#[derive(Debug, Clone, serde::Deserialize)]
pub struct ListSpec {
    /// Columnas sobre las que aplica el buscador global (LIKE).
    #[serde(default)]
    pub search: Vec<String>,
    /// Whitelist de columnas ordenables (anti-inyección: solo estas se interpolan en ORDER BY).
    #[serde(default)]
    pub sort: Vec<String>,
    /// Columna de orden por defecto (debe estar en `sort`).
    #[serde(default)]
    pub default_sort: Option<String>,
    /// Dirección por defecto (`asc`/`desc`).
    #[serde(default)]
    pub default_dir: Option<String>,
    /// Filtros por columna (orden determinista para SQL estable → `BTreeMap`).
    #[serde(default)]
    pub filters: std::collections::BTreeMap<String, FilterSpec>,
    /// Tamaño de página por defecto si el llamador no envía `limit`.
    #[serde(default = "default_page_size")]
    pub page_size: u64,
}

fn default_page_size() -> u64 {
    50
}

/// Operador de un filtro por columna.
#[derive(Debug, Clone, serde::Deserialize)]
pub struct FilterSpec {
    pub op: FilterOp,
}

/// Tipos de filtro soportados. `eq`: igualdad. `like`: subcadena. `range`: rango (from/to).
#[derive(Debug, Clone, Copy, PartialEq, Eq, serde::Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum FilterOp {
    Eq,
    Like,
    Range,
}

/// Bloque `ai` inline de una operación: la descripción legible (en inglés) que ve el LLM.
/// `permission`/`schema`/`sql` se heredan de la operación. ARQUITECTURA.md §9.2.
#[derive(Debug, Clone, serde::Deserialize)]
pub struct AiTool {
    pub description: String,
    /// Nombre opcional que ve el LLM (por defecto, el nombre de la operación).
    #[serde(default)]
    pub name: Option<String>,
}

#[derive(Debug, Clone, serde::Deserialize)]
pub struct CommandDef {
    pub permission: String,
    #[serde(default)]
    pub transaction: bool,
    #[serde(default)]
    pub sql: Vec<String>,
    /// Ruta (relativa a la carpeta del módulo) del JSON Schema del payload. Si está
    /// presente, el runtime valida el payload del llamador contra él ANTES de ejecutar
    /// (se compila una vez al instalar y se cachea en el `Registry`). §5.2, hub#27.
    #[serde(default)]
    pub schema: Option<String>,
    /// **Lecturas PRE-CARGADAS** que el runtime le entrega al handler antes de invocarlo
    /// (ADR-0069): nombres de query cuyas filas aterrizan en `context.reads["<query>"]`.
    ///
    /// Existe porque el handler WASM corre en un **sandbox** y no puede leer la BD. Sin esto, un
    /// handler solo sabe lo que le cuenta el cliente — y eso es exactamente cómo el navegador
    /// acababa decidiendo **el IVA que se le declara a la AEAT**: `sales.complete_sale` recibía el
    /// `tax_rate` de cada línea en el payload y se fiaba. Con `reads`, el handler resuelve el % del
    /// **catálogo de confianza del hub** (`taxes.rules.list`) y la pista del cliente pasa a ser solo
    /// un fallback.
    ///
    /// **Alcance**: queries del propio módulo o de los declarados en `depends_on`. Se gatea por la
    /// DEPENDENCIA, no por el permiso del usuario: el permiso del command ya se comprobó y las reads
    /// son contrato *vouched* por el autor del módulo (un empleado de POS sin `taxes.view_tax` igual
    /// necesita los tipos para cobrar). Una read que falle se **omite**: cobrar es lo último que
    /// puede romperse en un TPV.
    #[serde(default)]
    pub reads: Vec<ReadDef>,
    #[serde(default)]
    pub emit: Vec<String>,
    /// **Contrato de mutación** (hub#140): mínimo de filas que la(s) sentencia(s) `sql` del
    /// command DEBEN afectar para que el command se considere exitoso y se emitan sus `emit`.
    /// Si el recuento real queda por debajo, la transacción se revierte entera y NO se escribe
    /// ningún evento en el outbox (ni notificación al WS) — porque el hecho declarado nunca ocurrió.
    ///
    /// - `None` (default, opt-in): la gate está **desactivada**. Comportamiento de siempre: el
    ///   command emite sus eventos tanto si muta 1 fila como 0. Así no rompemos los módulos ya
    ///   publicados ni los commands genuinamente idempotentes (`UPDATE … WHERE NOT EXISTS`).
    /// - `Some(n)`: exige `>= n` filas afectadas en TOTAL por las sentencias `sql` del command
    ///   (no cuenta los INSERT del outbox). `Some(1)` es el caso habitual de un command de
    ///   transición: "confirmar" / "anular" / "cerrar" que NO debe emitir su evento si el `WHERE`
    ///   no casa (recurso inexistente o ya en el estado destino). `Some(0)` declararía
    ///   explícitamente un no-op idempotente permitido que igual emite.
    ///
    /// Ver [`crate::commands`] para el gate y
    /// [`crate::errors::RuntimeError::MinAffectedRows`].
    #[serde(default)]
    pub min_affected_rows: Option<u64>,
    /// Declarative domain error based on affected rows (hub#139). The translatable, namespaced
    /// flavour of `min_affected_rows`; the two fields cannot coexist on one command (the
    /// installer rejects the manifest).
    #[serde(default)]
    pub expect_rows: Option<ExpectRows>,
    /// Handler de lógica: Tier 2 (WASM sandbox) o **plugin nativo first-party**
    /// (ADR-0009, crate horneado en el runtime). Si está presente, el command ejecuta
    /// el handler en vez de su `sql` directo. ARQUITECTURA.md §5.3.
    #[serde(default)]
    pub handler: Option<HandlerRef>,
    /// Si está presente, expone este command al asistente como tool (nivel 2). El permiso y el
    /// schema se heredan del propio command, no se redeclaran. ARQUITECTURA.md §9.2.
    #[serde(default)]
    pub ai: Option<AiTool>,
    /// Opt-in: expone este command en la **API pública REST/OpenAPI** por módulo (ADR-0057,
    /// `architecture/hub/public-api.md`). Doble puerta: además de este flag, la API key debe
    /// tener el `permission` del command (escritura del módulo). Por defecto `false` → el command
    /// no es accesible vía API key aunque la key tuviera el permiso. El gate del runtime no cambia.
    #[serde(default)]
    pub expose_api: bool,
    /// Marca este command como **INTERNO** (hub#131, hub#145): solo lo puede invocar el propio
    /// runtime (un listener del outbox entregado por el relay, una scheduled task del mismo
    /// módulo) — nunca un caller EXTERNO (HTTP `/api/command`, API pública de API keys,
    /// asistente/SDK). Aditivo al convenio legacy de prefijo `_` en el último segmento del nombre
    /// (`cash_register._reverse_sale`): un command internal puede DEMÁS no llevar `_`, para
    /// módulos que prefieren blindarlo explícitamente sin ese prefijo. Ver [`CommandDef::is_internal`].
    #[serde(default)]
    pub internal: bool,
}

impl CommandDef {
    /// ¿Es `self` (registrado bajo `name`, el nombre namespaced completo) un command INTERNO?
    /// Dos señales, aditivas — cualquiera de las dos basta (hub#131, hub#145):
    ///  1. `internal: true` explícito en el manifest.
    ///  2. El **último segmento** de `name` (tras el último `.`) empieza por `_` — el convenio
    ///     legacy que ya usan los listeners cross-módulo (`cash_register._reverse_sale`,
    ///     `inventory._restock_on_void`) sin tener que migrar manifests existentes.
    pub fn is_internal(&self, name: &str) -> bool {
        self.internal
            || name
                .rsplit('.')
                .next()
                .map(|last| last.starts_with('_'))
                .unwrap_or(false)
    }
}

/// Referencia al handler de un command. ARQUITECTURA.md §5.3, §9.2.
///
/// - `type: "wasm"` — Tier 2: fichero `.wasm` del módulo (`file`) + función exportada.
/// - `type: "native"` — plugin nativo first-party (ADR-0009): la función vive en un
///   crate Rust horneado en el runtime, registrado por `module_id` vía
///   [`crate::Runtime::register_native`]. No lleva `file`.
#[derive(Debug, Clone, serde::Deserialize)]
pub struct HandlerRef {
    /// Tipo de handler: `"wasm"` | `"native"`.
    #[serde(rename = "type")]
    pub kind: String,
    /// Ruta (relativa a la carpeta del módulo) del `.wasm`. Solo para `type: "wasm"`.
    #[serde(default)]
    pub file: Option<String>,
    /// Función del handler a invocar (exportada del guest WASM o del plugin nativo).
    pub function: String,
}

#[derive(Debug, Clone, Default, serde::Deserialize)]
pub struct Events {
    #[serde(default)]
    pub listen: HashMap<String, Listener>,
    /// Eventos que el módulo **emite desde sus handlers** (WASM/nativo). Es el allowlist que el
    /// runtime comprueba antes de encolar en el outbox un evento devuelto por un handler (hub#240).
    ///
    /// Por qué existe: `emit` declara los eventos de un command **declarativo**; los que devuelve
    /// un handler no tenían dónde declararse, así que no se validaban contra nada — el handler
    /// elegía el nombre y el relay se lo entregaba a los listeners de otros módulos y al
    /// **listener-host de `host.notify`** (`*.reminder.due` → email/SMS/WhatsApp).
    ///
    /// Declarar esta lista pone al módulo en **modo estricto**: solo estos nombres (más los `emit`
    /// de sus commands) pueden salir de sus handlers. Un manifest que no la declara mantiene la
    /// compatibilidad con lo ya publicado, pero sigue sujeto a las dos reglas duras: no emitir en
    /// el namespace de otro módulo instalado y no emitir `*.reminder.due` sin la capability
    /// `notify`. Ver `commands::validate_handler_event`.
    #[serde(default)]
    pub emits: Vec<String>,
}

#[derive(Debug, Clone, serde::Deserialize)]
pub struct Listener {
    pub command: String,
}

impl Manifest {
    /// Lee y parsea `<dir>/module.json`.
    pub fn load(dir: &Path) -> Result<Manifest> {
        let path = dir.join("module.json");
        let text = std::fs::read_to_string(&path)?;
        serde_json::from_str(&text).map_err(|source| RuntimeError::Manifest {
            path: path.display().to_string(),
            source,
        })
    }

    /// Carga las traducciones del módulo desde `<dir>/locales/*.json` → `lang → ModuleLocale`
    /// (ADR-0055). Best-effort: si no hay carpeta o un fichero está roto, se omite (un locale
    /// inválido NUNCA rompe la instalación; siempre queda el fallback al manifest).
    pub fn load_locales(dir: &Path) -> HashMap<String, ModuleLocale> {
        let mut out: HashMap<String, ModuleLocale> = HashMap::new();
        let Ok(entries) = std::fs::read_dir(dir.join("locales")) else {
            return out;
        };
        for entry in entries.flatten() {
            let path = entry.path();
            if path.extension().and_then(|e| e.to_str()) != Some("json") {
                continue;
            }
            let Some(lang) = path.file_stem().and_then(|s| s.to_str()) else {
                continue;
            };
            if let Ok(text) = std::fs::read_to_string(&path) {
                if let Ok(loc) = serde_json::from_str::<ModuleLocale>(&text) {
                    out.insert(lang.to_string(), loc);
                }
            }
        }
        out
    }
}

/// Catálogo de traducciones de un módulo para UN idioma (`locales/<lang>.json`, ADR-0055). El
/// runtime solo resuelve `name` y `navigation[].label`; el bloque `ui` lo consume el Web Component
/// (lo hornea el toolkit en el `dist`), por eso aquí se ignora.
#[derive(Debug, Clone, Default, serde::Deserialize)]
pub struct ModuleLocale {
    #[serde(default)]
    pub name: Option<String>,
    #[serde(default)]
    pub navigation: HashMap<String, NavLocale>,
}

/// Traducción de una entrada de navegación (`navigation.<id>` en el locale del módulo).
#[derive(Debug, Clone, Default, serde::Deserialize)]
pub struct NavLocale {
    #[serde(default)]
    pub label: Option<String>,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_module_static_files_folder() {
        let json = r#"{
            "id": "verifactu",
            "name": "VeriFactu",
            "version": "1.2.3",
            "static_files": { "folder": "verifactu" }
        }"#;

        let manifest: Manifest = serde_json::from_str(json).expect("manifest parses");
        let storage = manifest.static_files.expect("static_files present");
        assert_eq!(storage.folder, "verifactu");
    }

    /// Lo que el USUARIO puede hacer desde `/files` con los ficheros de un módulo (ADR-0172).
    /// Por defecto: solo ver y descargar. El módulo tiene que pedir explícitamente lo demás.
    /// (El propio módulo sigue escribiendo por `ModuleStorage`: esto no le limita a él.)
    #[test]
    fn static_files_are_read_only_for_the_user_unless_the_module_opts_in() {
        let json = r#"{
            "id": "verifactu",
            "name": "VeriFactu",
            "version": "1.2.3",
            "static_files": { "folder": "verifactu" }
        }"#;

        let manifest: Manifest = serde_json::from_str(json).expect("manifest parses");
        let storage = manifest.static_files.expect("static_files present");
        assert!(storage.user_actions.is_empty(), "el default es solo-lectura");
        assert!(!storage.allows(UserFileAction::Delete));
        assert!(!storage.allows(UserFileAction::Rename));
        assert!(!storage.allows(UserFileAction::Upload));
    }

    #[test]
    fn a_module_can_open_up_its_folder_action_by_action() {
        let json = r#"{
            "id": "scans",
            "name": "Scans",
            "version": "1.0.0",
            "static_files": { "folder": "scans", "user_actions": ["upload", "delete"] }
        }"#;

        let manifest: Manifest = serde_json::from_str(json).expect("manifest parses");
        let storage = manifest.static_files.expect("static_files present");
        assert!(storage.allows(UserFileAction::Upload));
        assert!(storage.allows(UserFileAction::Delete));
        // Lo que no se pide, no se concede.
        assert!(!storage.allows(UserFileAction::Rename));
    }

    /// Un manifest con una acción desconocida no debe "colar" como si fuese válida ni tumbar la
    /// instalación entera: se ignora lo que el host no entiende (compatibilidad hacia adelante).
    #[test]
    fn unknown_user_actions_are_ignored_not_granted() {
        let json = r#"{
            "id": "scans",
            "name": "Scans",
            "version": "1.0.0",
            "static_files": { "folder": "scans", "user_actions": ["delete", "encrypt"] }
        }"#;

        let manifest: Manifest = serde_json::from_str(json).expect("manifest parses");
        let storage = manifest.static_files.expect("static_files present");
        assert!(storage.allows(UserFileAction::Delete));
        assert!(!storage.allows(UserFileAction::Rename));
    }

    /// Parsea un manifest con un bloque `widgets` (uno por la vía declarativa `kind`+`query` y
    /// uno por el escape hatch `component`) y verifica que se deserializa y RE-SERIALIZA sin
    /// perder campos (ADR-0054).
    #[test]
    fn parses_and_roundtrips_widgets_block() {
        let json = r#"{
            "id": "sales",
            "name": "Sales",
            "version": "1.2.3",
            "queries": {
                "sales.metrics.today": { "permission": "sales.read", "sql": "SELECT 1" }
            },
            "widgets": {
                "sales.today": {
                    "title": "Ventas de hoy",
                    "icon": "trending-up-outline",
                    "category": "Ventas",
                    "size": "md",
                    "permission": "sales.read",
                    "sectors": ["hosteleria", "retail"],
                    "default": true,
                    "kind": "kpi",
                    "query": "sales.metrics.today",
                    "params": { "period": "day" },
                    "map": { "value": "total", "delta": "delta_pct", "trend": "trend" },
                    "options": { "label": "Hoy", "format": "currency", "currency": "EUR" },
                    "refresh_on": ["sale.completed", "sale.voided"]
                },
                "sales.live_feed": {
                    "title": "Actividad en vivo",
                    "size": "lg",
                    "component": "erp-sales-live-feed"
                }
            }
        }"#;

        let manifest: Manifest = serde_json::from_str(json).expect("manifest parses");
        assert_eq!(manifest.widgets.len(), 2);

        let kpi = manifest
            .widgets
            .get("sales.today")
            .expect("kpi widget present");
        assert_eq!(kpi.title, "Ventas de hoy");
        assert_eq!(kpi.size, WidgetSize::Md);
        assert_eq!(kpi.kind, Some(WidgetKind::Kpi));
        assert_eq!(kpi.query.as_deref(), Some("sales.metrics.today"));
        assert!(kpi.default);
        assert_eq!(
            kpi.sectors,
            vec!["hosteleria".to_string(), "retail".to_string()]
        );
        assert_eq!(
            kpi.refresh_on,
            vec!["sale.completed".to_string(), "sale.voided".to_string()]
        );
        assert!(kpi.component.is_none());
        assert!(kpi.options.is_some());
        assert!(kpi.map.is_some());

        let custom = manifest
            .widgets
            .get("sales.live_feed")
            .expect("component widget present");
        assert_eq!(custom.size, WidgetSize::Lg);
        assert_eq!(custom.component.as_deref(), Some("erp-sales-live-feed"));
        assert!(custom.kind.is_none());
        assert!(custom.query.is_none());

        // Re-serializa y vuelve a parsear: ningún campo del contrato se pierde en el round-trip.
        let serialized = serde_json::to_value(&manifest.widgets).expect("widgets serialize");
        let kpi_json = &serialized["sales.today"];
        assert_eq!(kpi_json["title"], "Ventas de hoy");
        assert_eq!(kpi_json["kind"], "kpi");
        assert_eq!(kpi_json["size"], "md");
        assert_eq!(kpi_json["query"], "sales.metrics.today");
        assert_eq!(kpi_json["default"], true);
        assert_eq!(kpi_json["sectors"][0], "hosteleria");
        assert_eq!(kpi_json["options"]["currency"], "EUR");
        assert_eq!(kpi_json["map"]["value"], "total");
        // El refresco en vivo (refresh_on, ADR-0054 T1) sobrevive el round-trip: sin el campo en
        // el struct, serde lo DESCARTA en silencio y este assert cae (Null != "sale.completed").
        assert_eq!(kpi_json["refresh_on"][0], "sale.completed");
        assert_eq!(kpi_json["refresh_on"][1], "sale.voided");

        let custom_json = &serialized["sales.live_feed"];
        assert_eq!(custom_json["component"], "erp-sales-live-feed");
        assert_eq!(custom_json["size"], "lg");
        // `bar-list` se serializa con su rename, no como `barlist`.
        assert_eq!(
            serde_json::to_value(WidgetKind::BarList).unwrap(),
            serde_json::Value::String("bar-list".to_string())
        );
    }

    /// hub#351 (paso 2b): a module declares its own business roles on top of the frozen base
    /// catalogue. The three fields land verbatim; `extends` says which base role it hangs from.
    #[test]
    fn parses_the_declared_roles_block() {
        let json = r#"{
            "id": "kitchen",
            "name": "Kitchen",
            "version": "2.3.1",
            "roles": [
                { "key": "kitchen", "label": "Kitchen", "extends": "employee" },
                { "key": "shift_lead", "label": "Shift lead", "extends": "manager" }
            ],
            "role_permissions": {
                "kitchen": ["kitchen.view_ticket", "kitchen.bump_ticket"]
            }
        }"#;

        let manifest: Manifest = serde_json::from_str(json).expect("manifest parses");
        assert_eq!(manifest.roles.len(), 2);
        assert_eq!(manifest.roles[0].key, "kitchen");
        assert_eq!(manifest.roles[0].label, "Kitchen");
        assert_eq!(manifest.roles[0].extends, "employee");
        assert_eq!(manifest.roles[1].key, "shift_lead");
        assert_eq!(manifest.roles[1].extends, "manager");
        // The block is additive: `role_permissions` keeps working exactly as before, and may now
        // grant to a declared key as well as to the three base ones.
        assert_eq!(manifest.role_permissions["kitchen"].len(), 2);
    }

    /// The ~24 published modules do NOT carry a `roles` block, and adding the field must not make
    /// a single one of them unparseable: absent = the module declares no role of its own.
    #[test]
    fn a_manifest_without_the_roles_block_declares_none() {
        let json = r#"{
            "id": "inventory",
            "name": "Inventory",
            "version": "1.0.0",
            "role_permissions": {
                "admin": ["*"],
                "manager": ["inventory.view_product"],
                "employee": ["inventory.view_product"]
            }
        }"#;

        let manifest: Manifest = serde_json::from_str(json).expect("manifest parses");
        assert!(
            manifest.roles.is_empty(),
            "no `roles` block = no declared role, never a parse error"
        );
        assert_eq!(manifest.role_permissions.len(), 3);
    }

    /// A role is `key` + `label` + `extends`, the three of them: the struct mirrors the `required`
    /// of `schemas/module.schema.json`, so a half-declared role never reaches the validation — it
    /// dies at parse time with an error that names the missing field.
    #[test]
    fn a_role_missing_one_of_its_three_fields_does_not_parse() {
        let json = r#"{
            "id": "kitchen",
            "name": "Kitchen",
            "version": "2.3.1",
            "roles": [{ "key": "kitchen", "extends": "employee" }]
        }"#;

        let error = serde_json::from_str::<Manifest>(json)
            .expect_err("a role without `label` is not a role")
            .to_string();
        assert!(
            error.contains("label"),
            "the error must name the missing field: {error}"
        );
    }

    /// hub#131/#145: `internal: true` parsea (aditivo, opcional) y `is_internal()` lo detecta
    /// aunque el nombre del command NO lleve prefijo `_`.
    #[test]
    fn command_internal_flag_parses_and_is_internal_true_without_underscore() {
        let json = r#"{
            "id": "pricing",
            "name": "Pricing",
            "version": "1.0.0",
            "commands": {
                "pricing.reindex_catalog": {
                    "permission": "pricing.write",
                    "sql": ["UPDATE x SET y = 1"],
                    "internal": true
                }
            }
        }"#;
        let manifest: Manifest = serde_json::from_str(json).expect("manifest parses");
        let cmd = &manifest.commands["pricing.reindex_catalog"];
        assert!(cmd.internal, "`internal: true` debe parsear a true");
        assert!(
            cmd.is_internal("pricing.reindex_catalog"),
            "internal:true → is_internal() aunque el nombre no lleve `_`"
        );
    }

    /// Un manifest legacy que NO declara `internal` sigue considerando interno un command cuyo
    /// ÚLTIMO segmento namespaced empieza por `_` (convenio ya en uso: `cash_register._reverse_sale`),
    /// y NO interno el resto — el campo por defecto es `false` (aditivo, no rompe manifests viejos).
    #[test]
    fn command_internal_defaults_false_and_underscore_suffix_is_internal_by_convention() {
        let json = r#"{
            "id": "cash_register",
            "name": "Cash register",
            "version": "1.0.0",
            "commands": {
                "cash_register._reverse_sale": {
                    "permission": "cash_register.write",
                    "sql": ["UPDATE x SET y = 1"]
                },
                "cash_register.movement.add": {
                    "permission": "cash_register.write",
                    "sql": ["INSERT INTO x VALUES (1)"]
                }
            }
        }"#;
        let manifest: Manifest = serde_json::from_str(json).expect("manifest parses");

        let internal_cmd = &manifest.commands["cash_register._reverse_sale"];
        assert!(!internal_cmd.internal, "el campo `internal` no se declaró: default false");
        assert!(
            internal_cmd.is_internal("cash_register._reverse_sale"),
            "el último segmento empieza por `_` → interno por convención, sin migrar el manifest"
        );

        let public_cmd = &manifest.commands["cash_register.movement.add"];
        assert!(
            !public_cmd.is_internal("cash_register.movement.add"),
            "sin prefijo `_` ni `internal:true` → NO es interno"
        );
    }
}
