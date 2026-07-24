//! Settings del hub — capa HTTP del store key/value de **sistema** (tabla `hub_settings`, migración
//! v4; lógica en `erplora_runtime::settings`).
//!
//! Dos endpoints, ambos montados en [`crate::app`]:
//!  - `GET /api/settings` → objeto con TODAS las claves conocidas (fila ∪ defaults). Auth =
//!    **cualquier sesión de usuario válida** (`require_user_session`): leer la config es inofensivo.
//!  - `PUT /api/settings` → body `{ currency?, language?, api_docs_enabled?, … }` (parcial). Valida
//!    y persiste. Auth = **sesión admin** (owner/admin, `require_admin_session`). Devuelve el objeto
//!    completo actualizado.
//!
//! El `hub_id` viene del despliegue (config, no spoofable); el runtime de la petición se resuelve
//! por org vía `runtime_for` (ADR-0005), igual que `api_keys.rs`. La validación de claves conocidas
//! la hace el runtime; aquí solo se mapea auth + errores a HTTP.
use axum::extract::Path;
use axum::extract::State;
use axum::http::{HeaderMap, StatusCode};
use axum::response::{IntoResponse, Response};
use axum::Json;
use serde_json::{json, Map, Value};

use crate::auth;
use crate::state::AppState;

/// `401` para fallo de auth (sin sesión / sesión inválida / rol insuficiente).
fn unauthorized(e: auth::AuthError) -> Response {
    (
        StatusCode::UNAUTHORIZED,
        Json(json!({ "ok": false, "error": e.message() })),
    )
        .into_response()
}

/// GET /api/settings — objeto con todas las claves conocidas (fila ∪ defaults). Auth = sesión de
/// usuario válida (cualquier rol). Devuelve `{ currency, language, api_docs_enabled, … }` **plano**
/// (no envuelto en `{ok,data}`): es el contrato directo que consume el frontend.
pub async fn get_settings(State(st): State<AppState>, headers: HeaderMap) -> Response {
    let arc = match st.runtime_for(&st.hub_id()).await {
        Ok(rt) => rt,
        Err(e) => return crate::tenant_rejected(e),
    };
    let rt = arc.lock().await;
    if let Err(e) = auth::require_user_session(&headers, &st.config, &rt).await {
        return unauthorized(e);
    }
    match rt.get_settings().await {
        Ok(settings) => Json(settings).into_response(),
        Err(e) => crate::err_response(e),
    }
}

/// PUT /api/settings — aplica un mapa parcial de settings (valida cada clave; rechaza desconocidas o
/// valores inválidos → 422). Auth = sesión admin (owner/admin). Body = objeto plano
/// `{ "currency": "USD", "language": "en", … }`. Devuelve el objeto completo actualizado (plano).
pub async fn put_settings(
    State(st): State<AppState>,
    headers: HeaderMap,
    body: Option<Json<Map<String, Value>>>,
) -> Response {
    let updates = body.map(|b| b.0).unwrap_or_default();
    let arc = match st.runtime_for(&st.hub_id()).await {
        Ok(rt) => rt,
        Err(e) => return crate::tenant_rejected(e),
    };
    let rt = arc.lock().await;
    let admin = match auth::require_admin_session(&headers, &st.config, &rt).await {
        Ok(u) => u,
        Err(e) => return unauthorized(e),
    };
    // Auditoría: quién cambió la config (el `hub_user` admin de la sesión).
    let updated_by = format!("hub_user:{}", admin.id);
    match rt.set_settings(&updates, &updated_by).await {
        Ok(settings) => Json(settings).into_response(),
        Err(e) => crate::err_response(e),
    }
}

// ── Capabilities de módulo (ADR-0079) ───────────────────────────────────────────────────────────

/// Catálogo legible (ES) de las capabilities conocidas. El server es la autoridad de las etiquetas;
/// el frontend las pinta tal cual (con un fallback local).
fn capability_meta(id: &str) -> (&'static str, &'static str) {
    match id {
        "network" => (
            "Acceso a internet",
            "Permite al módulo conectarse a servidores externos (solo a los hosts declarados).",
        ),
        "certificate" => (
            "Certificado del negocio (firma fiscal)",
            "Permite usar el certificado de la empresa para firmar y transmitir documentos (p.ej. a Hacienda). La clave privada nunca sale del Hub.",
        ),
        "printer" => (
            "Impresora",
            "Permite imprimir en las impresoras de ticket/cocina a través del bridge.",
        ),
        "notify" => (
            "Notificaciones",
            "Permite enviar notificaciones por email, SMS o WhatsApp.",
        ),
        _ => ("Permiso", "Permiso solicitado por el módulo."),
    }
}

/// Forma del contrato `{ module_id, capabilities: [{ id, label, description, requested, granted }] }`.
fn caps_json(module_id: &str, caps: Vec<(String, bool)>) -> Value {
    let items: Vec<Value> = caps
        .into_iter()
        .map(|(id, granted)| {
            let (label, desc) = capability_meta(&id);
            json!({ "id": id, "label": label, "description": desc, "requested": true, "granted": granted })
        })
        .collect();
    json!({ "module_id": module_id, "capabilities": items })
}

/// GET /api/modules/:id/capabilities — capabilities que el módulo DECLARA + su estado de grant
/// (ADR-0079). Auth = sesión de usuario (cualquier rol), como `GET /api/settings`.
pub async fn get_module_capabilities(
    State(st): State<AppState>,
    headers: HeaderMap,
    Path(module_id): Path<String>,
) -> Response {
    let arc = match st.runtime_for(&st.hub_id()).await {
        Ok(rt) => rt,
        Err(e) => return crate::tenant_rejected(e),
    };
    let rt = arc.lock().await;
    if let Err(e) = auth::require_user_session(&headers, &st.config, &rt).await {
        return unauthorized(e);
    }
    match rt.module_capabilities(&module_id).await {
        Ok(caps) => Json(caps_json(&module_id, caps)).into_response(),
        Err(e) => crate::err_response(e),
    }
}

/// PUT /api/modules/:id/capabilities — concede/revoca capabilities. Body
/// `{ "grants": { "network": true, "certificate": false } }`. Auth = sesión admin (owner/admin).
/// Devuelve el estado actualizado (misma forma que GET).
pub async fn put_module_capabilities(
    State(st): State<AppState>,
    headers: HeaderMap,
    Path(module_id): Path<String>,
    body: Option<Json<Map<String, Value>>>,
) -> Response {
    let updates = body.map(|b| b.0).unwrap_or_default();
    let grants = updates
        .get("grants")
        .and_then(|v| v.as_object())
        .cloned()
        .unwrap_or_default();
    let arc = match st.runtime_for(&st.hub_id()).await {
        Ok(rt) => rt,
        Err(e) => return crate::tenant_rejected(e),
    };
    let rt = arc.lock().await;
    let admin = match auth::require_admin_session(&headers, &st.config, &rt).await {
        Ok(u) => u,
        Err(e) => return unauthorized(e),
    };
    let by = format!("hub_user:{}", admin.id);
    for (cap, val) in &grants {
        let granted = val.as_bool().unwrap_or(false);
        if let Err(e) = rt
            .set_module_capability(&module_id, cap, granted, &by)
            .await
        {
            return crate::err_response(e);
        }
    }
    match rt.module_capabilities(&module_id).await {
        Ok(caps) => Json(caps_json(&module_id, caps)).into_response(),
        Err(e) => crate::err_response(e),
    }
}

// ── Certificado fiscal del negocio (ADR-0079) ───────────────────────────────────────────────────

/// GET /api/business/certificate — estado del certificado del negocio (presente/ausente + metadatos,
/// SIN bytes ni contraseña). Auth = sesión de usuario (cualquier rol).
pub async fn get_business_certificate(State(st): State<AppState>, headers: HeaderMap) -> Response {
    let arc = match st.runtime_for(&st.hub_id()).await {
        Ok(rt) => rt,
        Err(e) => return crate::tenant_rejected(e),
    };
    let rt = arc.lock().await;
    if let Err(e) = auth::require_user_session(&headers, &st.config, &rt).await {
        return unauthorized(e);
    }
    match rt.business_certificate_status().await {
        Ok(s) => Json(s).into_response(),
        Err(e) => crate::err_response(e),
    }
}

/// PUT /api/business/certificate — sube/reemplaza el `.p12`. Body `{ pkcs12_b64, password }`.
/// Auth = sesión admin (owner/admin). Devuelve el estado actualizado.
pub async fn put_business_certificate(
    State(st): State<AppState>,
    headers: HeaderMap,
    body: Option<Json<Map<String, Value>>>,
) -> Response {
    let updates = body.map(|b| b.0).unwrap_or_default();
    let b64 = updates
        .get("pkcs12_b64")
        .and_then(|v| v.as_str())
        .unwrap_or("")
        .to_string();
    let password = updates
        .get("password")
        .and_then(|v| v.as_str())
        .unwrap_or("")
        .to_string();
    if b64.trim().is_empty() {
        return (
            StatusCode::UNPROCESSABLE_ENTITY,
            Json(json!({ "ok": false, "error": "falta pkcs12_b64 (base64 del .p12)" })),
        )
            .into_response();
    }
    let arc = match st.runtime_for(&st.hub_id()).await {
        Ok(rt) => rt,
        Err(e) => return crate::tenant_rejected(e),
    };
    let rt = arc.lock().await;
    let admin = match auth::require_admin_session(&headers, &st.config, &rt).await {
        Ok(u) => u,
        Err(e) => return unauthorized(e),
    };
    let by = format!("hub_user:{}", admin.id);
    if let Err(e) = rt.set_business_certificate(&b64, &password, &by).await {
        return crate::err_response(e);
    }
    match rt.business_certificate_status().await {
        Ok(s) => Json(s).into_response(),
        Err(e) => crate::err_response(e),
    }
}

/// DELETE /api/business/certificate — elimina el certificado del negocio. Auth = sesión admin.
pub async fn delete_business_certificate(
    State(st): State<AppState>,
    headers: HeaderMap,
) -> Response {
    let arc = match st.runtime_for(&st.hub_id()).await {
        Ok(rt) => rt,
        Err(e) => return crate::tenant_rejected(e),
    };
    let rt = arc.lock().await;
    if let Err(e) = auth::require_admin_session(&headers, &st.config, &rt).await {
        return unauthorized(e);
    }
    if let Err(e) = rt.delete_business_certificate().await {
        return crate::err_response(e);
    }
    match rt.business_certificate_status().await {
        Ok(s) => Json(s).into_response(),
        Err(e) => crate::err_response(e),
    }
}
