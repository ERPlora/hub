//! Ejecución de queries declarativas (SELECT). ARQUITECTURA.md §4.
use erplora_db::{DatabaseAdapter, Params};
use serde_json::Value as Json;

use crate::errors::{Result, RuntimeError};
use crate::permissions;
use crate::registry::{Registry, RequestContext};

/// Ejecuta `name(params)` con el contexto dado y devuelve las filas como JSON.
pub fn execute(
    db: &dyn DatabaseAdapter,
    registry: &Registry,
    name: &str,
    params: &Params,
    ctx: &RequestContext,
) -> Result<Vec<Json>> {
    let q = registry
        .get_query(name)
        .ok_or_else(|| RuntimeError::QueryNotFound(name.to_string()))?;
    permissions::check(ctx, &q.def.permission)?;
    let bound = crate::system_params(params, ctx);
    Ok(db.query(&q.sql, &bound)?)
}
