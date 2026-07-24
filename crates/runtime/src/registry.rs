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

/// Observador de eventos del runtime. El server lo implementa con un canal
/// broadcast para reenviar los eventos por WebSocket (ARQUITECTURA.md §7.7).
pub trait EventSink: Send + Sync + std::fmt::Debug {
    fn emit(&self, event: &str, payload: &serde_json::Value);
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
    /// Transporte de `host.backup_upload` (ADR-0040): el cliente real que pide la credencial STS/
    /// presignada al Cloud y sube el blob cifrado del backup a S3. Lo inyecta el host al arrancar
    /// (`Runtime::set_backup_transport`). `None` = la capacidad `host.backup_upload` no está
    /// disponible (los eventos `backup.requested` se entregan a sus listeners de módulo, pero el
    /// listener-host no sube nada). Espejo de `notify_transport`. Ver `outbox.rs`.
    pub backup_transport: Option<std::sync::Arc<dyn crate::host_backup::BackupTransport>>,
    /// Backend de `static_files` declarado por módulos. Lo inyecta el host y resuelve a disco
    /// Local o Cloud→S3 sin exponer paths físicos al módulo.
    pub module_storage: Option<std::sync::Arc<dyn crate::module_storage::ModuleStorage>>,
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
    pub fn exposed_commands<'a>(
        &'a self,
        module_id: &str,
    ) -> Vec<(&'a str, &'a RegisteredCommand)> {
        if !self.is_active(module_id) {
            return Vec::new();
        }
        self.commands
            .iter()
            .filter(|(_, c)| c.module_id == module_id && c.def.expose_api)
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

    /// Espejo de [`is_query_exposed`] para commands (`POST /api/v1/{module}/c/{command}`).
    pub fn is_command_exposed(&self, module_id: &str, name: &str) -> bool {
        self.get_command(name)
            .map(|c| c.module_id == module_id && c.def.expose_api)
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
        }
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
