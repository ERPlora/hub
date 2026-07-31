//! Reset del hub — volver el hub a cero (ADR-0166).
//!
//! **Espejo del export**: reutiliza su mismo inventario de tablas (`table_owner` por prefijo más
//! largo, FKs leídas del catálogo) recorrido al revés. Así lo que el hub sabe exportar es
//! exactamente lo que sabe borrar, y un módulo nuevo no hay que darlo de alta en dos sitios.
//!
//! Reglas duras (fijadas por los e2e `tests/reset_test.rs`):
//!   - `DELETE ... WHERE hub_id = :hub_id` SIEMPRE. Nunca `TRUNCATE`, nunca `DROP`: la BD es
//!     **compartida por organización** (`tenancy.md`) y un reset mal acotado se llevaría los hubs
//!     hermanos.
//!   - **Borrado duro**, no `is_deleted=1`: el soft-delete masivo rompería los índices únicos
//!     `(hub_id, …)` al reimportar.
//!   - **Una sola transacción** (`execute_tx`): al revés que el import, que es best-effort a
//!     propósito, un reset a medias no deja ni seguir ni volver.
//!   - **Las filas propiedad del módulo sobreviven** (mismo criterio que `is_module_seeded` del
//!     export): las siembra el módulo al instalarse y no las re-siembra.
//!   - **Nadie se auto-expulsa**: el usuario que ejecuta el reset nunca se borra.

use serde::{Deserialize, Serialize};

use crate::Runtime;

/// Qué secciones se borran. Todo `false`/vacío por defecto: el reset nunca hace de más.
#[derive(Debug, Clone, Default)]
pub struct ResetSelection {
    /// Settings del hub (`hub_settings`).
    pub settings: bool,
    /// Empleados (`hub_user`) — MENOS quien ejecuta el reset.
    pub users: bool,
    /// Ficheros del gestor media. El runtime solo lo registra; los bytes los borra el server.
    pub media: bool,
    /// Configuración fiscal + certificado. Bloqueada si hay facturas remitidas a la AEAT.
    pub fiscal: bool,
    /// Ids de módulos instalados cuyos datos de usuario se borran.
    pub modules: Vec<String>,
}

/// Una sección en el **dry-run**: cuántas filas se llevaría y si algo la bloquea.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct SectionPlan {
    /// `hub_settings` · `hub_users` · `media` · `fiscal` · `modules/<id>`.
    pub section: String,
    /// Filas reales que se borrarían (la UI pinta cifras, no adjetivos).
    pub rows: i64,
    /// Motivo legible por el que la sección NO se puede borrar (p. ej. facturas remitidas a la
    /// AEAT). `Some` ⇒ la UI la deshabilita y el server la rechaza aunque el cliente insista.
    pub blocked_by: Option<String>,
}

/// Dry-run completo: lo que el panel de «Restablecer» pinta antes de que nadie confirme.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq, Default)]
pub struct ResetPlan {
    pub sections: Vec<SectionPlan>,
}

/// Lo que el reset hizo en una sección.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct SectionOutcome {
    pub section: String,
    pub rows_deleted: i64,
}

/// Informe final del reset (contrato JSON que la UI pinta tal cual).
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq, Default)]
pub struct ResetReport {
    pub sections: Vec<SectionOutcome>,
}

/// **Dry-run**: inventaría las secciones del hub con el número de filas que se borrarían y los
/// bloqueos aplicables. No escribe nada — se ejecuta con solo abrir el panel.
pub async fn plan_reset(_rt: &Runtime, _hub_id: &str) -> crate::Result<ResetPlan> {
    unimplemented!("ADR-0166 Fase 1: plan_reset")
}

/// Borra las secciones seleccionadas del hub `hub_id`, en una sola transacción y en orden
/// topológico inverso de FK. `actor_user_id` nunca se borra (no te puedes auto-expulsar).
pub async fn execute_reset(
    _rt: &Runtime,
    _hub_id: &str,
    _selection: &ResetSelection,
    _actor_user_id: &str,
) -> crate::Result<ResetReport> {
    unimplemented!("ADR-0166 Fase 1: execute_reset")
}
