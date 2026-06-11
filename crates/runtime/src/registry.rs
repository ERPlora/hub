//! Registro en memoria de las capacidades de los módulos instalados + contexto de petición.
//! ARQUITECTURA.md §4. Soporta ciclo de vida: un módulo instalado puede estar ACTIVO o
//! INACTIVO; solo los activos exponen menú/queries/commands/eventos (hot-plug, §4 paso 11).
use std::collections::{HashMap, HashSet};

use crate::manifest::{CommandDef, Manifest, Nav, QueryDef};

/// Estado de un módulo instalado en este hub (equivalente a la tabla `hub_module`, §2.5).
#[derive(Debug, Clone, Copy, PartialEq, Eq, serde::Serialize)]
#[serde(rename_all = "lowercase")]
pub enum ModuleStatus {
    Active,
    Inactive,
}

/// Una query registrada: su definición + el SQL ya leído de disco + el módulo que la aporta.
#[derive(Debug, Clone)]
pub struct RegisteredQuery {
    pub module_id: String,
    pub def: QueryDef,
    pub sql: String,
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
    /// Observador opcional de eventos (lo pone el server para el WS).
    pub event_sink: Option<std::sync::Arc<dyn EventSink>>,
    /// Plugins **nativos first-party** (ADR-0009): `module_id` → motor horneado en el
    /// runtime. Los registra el host (server/Tauri) al arrancar, no la instalación.
    pub native: HashMap<String, std::sync::Arc<dyn crate::native::NativeHandler>>,
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

    /// Query registrada, **solo si su módulo está activo** (hot-plug).
    pub fn get_query(&self, name: &str) -> Option<&RegisteredQuery> {
        self.queries.get(name).filter(|q| self.is_active(&q.module_id))
    }

    /// Command registrado, **solo si su módulo está activo**.
    pub fn get_command(&self, name: &str) -> Option<&RegisteredCommand> {
        self.commands.get(name).filter(|c| self.is_active(&c.module_id))
    }

    /// Commands suscritos a un evento, **solo de módulos activos**.
    pub fn listeners_for(&self, event: &str) -> Vec<String> {
        self.listeners
            .get(event)
            .map(|cmds| {
                cmds.iter()
                    .filter(|name| {
                        self.commands.get(*name).map(|c| self.is_active(&c.module_id)).unwrap_or(false)
                    })
                    .cloned()
                    .collect()
            })
            .unwrap_or_default()
    }

    /// Menú dinámico: entradas de navegación **solo de módulos activos**.
    pub fn active_navigation(&self) -> Vec<&NavEntry> {
        self.navigation.iter().filter(|n| self.is_active(&n.module_id)).collect()
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
        }
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
