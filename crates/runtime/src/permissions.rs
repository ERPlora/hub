//! Comprobación de permisos. El gate es el mismo para UI, API y AI tools (ARQUITECTURA.md §9.2).
//! La autoridad real es siempre el runtime (Rust), nunca la UI.
use crate::errors::{Result, RuntimeError};
use crate::registry::RequestContext;

/// Verifica que el contexto tenga el permiso requerido (o el comodín `*`).
pub fn check(ctx: &RequestContext, required: &str) -> Result<()> {
    if has(ctx, required) {
        Ok(())
    } else {
        Err(RuntimeError::PermissionDenied(required.to_string()))
    }
}

/// Same question as [`check`], asked without turning a "no" into an error.
///
/// It exists for the places that FILTER instead of rejecting — `hub.setup.status` only offers a
/// checklist item to whoever could act on it. Sharing the predicate keeps that filter and the real
/// gate from ever disagreeing about what a permission means.
pub fn has(ctx: &RequestContext, required: &str) -> bool {
    ctx.permissions.contains("*") || ctx.permissions.contains(required)
}
