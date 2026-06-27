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
    #[serde(default)]
    pub navigation: Vec<Nav>,
    #[serde(default)]
    pub migrations: Migrations,
    #[serde(default)]
    pub queries: HashMap<String, QueryDef>,
    #[serde(default)]
    pub commands: HashMap<String, CommandDef>,
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
    /// Categorías fiscales que el módulo NECESITA que existan en el catálogo del hub (ADR-0085):
    /// claves canónicas (`tax_category_key`) tipo `["restaurant.food", "restaurant.drink"]`. El
    /// sistema garantiza que existan (las canónicas del módulo `taxes` + el seed por país). Permite
    /// que un módulo de marketplace enlace productos por categoría sabiendo que la categoría existe.
    /// Vacío/ausente = el módulo no requiere ninguna categoría concreta.
    #[serde(default)]
    pub required_tax_categories: Vec<String>,
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

/// Bloque `agent` del manifest: descripción del módulo (en inglés) para el routing del
/// asistente y palabras clave opcionales para pre-filtro léxico. ARQUITECTURA.md §9.2b.
#[derive(Debug, Clone, serde::Deserialize)]
pub struct Agent {
    pub description: String,
    #[serde(default)]
    pub keywords: Vec<String>,
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
    /// Queries que el runtime **pre-ejecuta** e **inyecta** en `context.reads[<query>]` antes de
    /// invocar el handler (WASM/nativo), para que la lógica del sandbox —que NO puede leer la BD ni
    /// otros módulos— disponga de filas de confianza (ADR-0069, el "keystone" del impuesto). Cada
    /// nombre es una query namespaced (`modulo.entidad.accion`). **Alcance**: queries del propio
    /// módulo o de los declarados en `depends_on` (gateado por la **dependencia**, no por permiso de
    /// usuario); una read fuera de alcance se **omite con warn**. **Ejecución interna**: como el
    /// sistema (el permiso del command ya se comprobó; las reads son contrato vouched por el autor),
    /// **sin params** y **sin re-gatear por permiso de usuario** por-query. Una read que falle se
    /// omite (el handler degrada con su fallback al `payload`). Por defecto vacío → ningún cambio para
    /// los commands existentes (backward-compat). Ver `commands::preload_reads`.
    #[serde(default)]
    pub reads: Vec<String>,
    /// Ruta (relativa a la carpeta del módulo) del JSON Schema del payload. Si está
    /// presente, el runtime valida el payload del llamador contra él ANTES de ejecutar
    /// (se compila una vez al instalar y se cachea en el `Registry`). §5.2, hub#27.
    #[serde(default)]
    pub schema: Option<String>,
    #[serde(default)]
    pub emit: Vec<String>,
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
                    "options": { "label": "Hoy", "format": "currency", "currency": "EUR" }
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

        let kpi = manifest.widgets.get("sales.today").expect("kpi widget present");
        assert_eq!(kpi.title, "Ventas de hoy");
        assert_eq!(kpi.size, WidgetSize::Md);
        assert_eq!(kpi.kind, Some(WidgetKind::Kpi));
        assert_eq!(kpi.query.as_deref(), Some("sales.metrics.today"));
        assert!(kpi.default);
        assert_eq!(kpi.sectors, vec!["hosteleria".to_string(), "retail".to_string()]);
        assert!(kpi.component.is_none());
        assert!(kpi.options.is_some());
        assert!(kpi.map.is_some());

        let custom = manifest.widgets.get("sales.live_feed").expect("component widget present");
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

        let custom_json = &serialized["sales.live_feed"];
        assert_eq!(custom_json["component"], "erp-sales-live-feed");
        assert_eq!(custom_json["size"], "lg");
        // `bar-list` se serializa con su rename, no como `barlist`.
        assert_eq!(
            serde_json::to_value(WidgetKind::BarList).unwrap(),
            serde_json::Value::String("bar-list".to_string())
        );
    }
}
