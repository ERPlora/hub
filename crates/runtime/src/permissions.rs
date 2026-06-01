//! Comprobación de permisos. El gate es el mismo para UI, API y AI tools (ARQUITECTURA.md §9.2).
//! La autoridad real es siempre el runtime (Rust), nunca la UI.
use crate::errors::{Result, RuntimeError};
use crate::registry::RequestContext;

/// Verifica que el contexto tenga el permiso requerido (o el comodín `*`).
pub fn check(ctx: &RequestContext, required: &str) -> Result<()> {
    if ctx.permissions.contains("*") || ctx.permissions.contains(required) {
        Ok(())
    } else {
        Err(RuntimeError::PermissionDenied(required.to_string()))
    }
}
