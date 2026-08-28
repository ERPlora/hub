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
///
/// 🔴 **Esta lista de brazos es la LISTA MAESTRA de capabilities del core.** Si añades uno aquí,
/// añádelo también al espejo `apps/web/src/lib/module-capabilities.ts` **con su `breaksKey`** (qué
/// deja de funcionar si el permiso no se concede, hub#1174) y sus cadenas `en` + `es`. No es una
/// convención: `apps/web/src/lib/module-capabilities.test.ts` lee ESTE fichero, compara la lista y
/// falla nombrando la capability que se quedó sin espejo o sin «qué se rompe».
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
        // hub#1096 / ADR-0196: el Bridge se retiró (hub#339/#340). La impresión va por la cola del
        // runtime del Hub (`crates/runtime/src/print_queue.rs`), que drena erplora-app por
        // `GET /ws/print` como host de impresión registrado. Espejo en
        // `apps/web/src/lib/module-capabilities.ts` — un test de vitest clava que digan lo mismo.
        "printer" => (
            "Impresora",
            "Permite imprimir en las impresoras de ticket/cocina a través de la cola de impresión del Hub, que drena erplora-app como host de impresión.",
        ),
        "notify" => (
            "Notificaciones",
            "Permite enviar notificaciones por email, SMS o WhatsApp.",
        ),
        // hub#714. La descripción dice lo que el dueño arriesga, no el nombre técnico: quien
        // administra flujos consigue que el hub actúe cuando no hay nadie delante.
        "manage_flows" => (
            "Administrar automatizaciones",
            "Permite crear, editar y borrar los flujos del hub, sus permisos y sus secretos. Un flujo ejecuta acciones en tu negocio sin nadie delante, así que concédelo solo al módulo con el que quieras editarlos.",
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

// ── Identidad fiscal hacia el SaaS (ADR-0201 decisión 5, 7/11 — hub#333) ───────────────────────

/// Campos de `hub_settings` que forman la identidad que ERPlora factura. Es una COPIA: el NIF del
/// negocio se queda aquí (es con quién factura el cliente a los suyos); el del `BillingProfile` es
/// a quién factura ERPlora. Dos NIF conceptualmente distintos que no se leen entre sí.
fn fiscal_identity_payload(settings: &Value) -> Option<Map<String, Value>> {
    let get = |k: &str| {
        settings
            .get(k)
            .and_then(|v| v.as_str())
            .unwrap_or("")
            .trim()
            .to_string()
    };
    let tax_id = get("business_tax_id");
    if tax_id.is_empty() {
        return None; // sin NIF no hay nada que publicar: el SaaS lo rechazaría igualmente
    }
    let mut body = Map::new();
    body.insert("tax_id".into(), Value::String(tax_id));
    body.insert(
        "billing_name".into(),
        Value::String(get("business_legal_name")),
    );
    body.insert(
        "billing_address".into(),
        Value::String(get("business_address")),
    );
    body.insert("billing_country".into(), Value::String(get("country_code")));
    Some(body)
}

/// POST /api/business/fiscal-identity — publica la identidad fiscal del negocio en el SaaS, que
/// crea/actualiza el `BillingProfile` que paga este hub (ADR-0201 decisión 5).
///
/// Es la casilla *"usar estos datos también para mi factura de ERPlora"* de Ajustes → Negocio: el
/// dato se escribió UNA vez aquí y la copia SUBE. Sin marcarla, el perfil se rellena aparte en el
/// SaaS (el caso de la gestoría que paga los hubs de sus clientes).
///
/// **La llamada la hace el runtime**: el `cloud_api_token` es secreto del hub y nunca cruza al
/// navegador (ADR-0003). Auth = sesión admin, porque la identidad fiscal es del dueño del negocio.
pub async fn publish_fiscal_identity(State(st): State<AppState>, headers: HeaderMap) -> Response {
    let arc = match st.runtime_for(&st.hub_id()).await {
        Ok(rt) => rt,
        Err(e) => return crate::tenant_rejected(e),
    };
    let settings = {
        let rt = arc.lock().await;
        if let Err(e) = auth::require_admin_session(&headers, &st.config, &rt).await {
            return unauthorized(e);
        }
        match rt.get_settings().await {
            Ok(s) => s,
            Err(e) => return crate::err_response(e),
        }
    };

    let Some(body) = fiscal_identity_payload(&settings) else {
        return (
            axum::http::StatusCode::BAD_REQUEST,
            Json(serde_json::json!({
                "ok": false,
                "error": "business_tax_id_required",
                "message": "Fill in the business tax id before sharing it with ERPlora",
            })),
        )
            .into_response();
    };

    let Some(machine) = auth::machine_auth(&st) else {
        return (
            axum::http::StatusCode::SERVICE_UNAVAILABLE,
            Json(serde_json::json!({ "ok": false, "error": "hub_not_enrolled" })),
        )
            .into_response();
    };

    let req = cloud_client::CloudClient::new(&st.config.cloud_base_url).fiscal_identity(&machine);
    let mut request = reqwest::Client::new().post(&req.url).json(&body);
    for (name, value) in req.headers {
        request = request.header(name, value);
    }
    match request.send().await {
        Ok(response) if response.status().is_success() => {
            Json(serde_json::json!({ "ok": true })).into_response()
        }
        Ok(response) => (
            axum::http::StatusCode::BAD_GATEWAY,
            Json(serde_json::json!({
                "ok": false,
                "error": "cloud_rejected",
                "status": response.status().as_u16(),
            })),
        )
            .into_response(),
        Err(e) => (
            axum::http::StatusCode::BAD_GATEWAY,
            Json(serde_json::json!({ "ok": false, "error": e.to_string() })),
        )
            .into_response(),
    }
}

#[cfg(test)]
mod capability_meta_tests {
    use super::*;

    /// hub#1096 / ADR-0196: the standalone Bridge is retired (hub#339/#340). The copy the owner
    /// reads to DECIDE whether to grant the printer permission must not name it: whoever goes
    /// looking for «el bridge» to install it hits a dead end (the one printing#12 closed). Today
    /// printing goes through the Hub's print queue, drained by erplora-app as the print host.
    #[test]
    fn printer_description_names_the_print_queue_not_the_retired_bridge() {
        let (label, desc) = capability_meta("printer");
        assert_eq!(label, "Impresora");
        assert!(
            !desc.to_lowercase().contains("bridge"),
            "still names the retired bridge: {desc}"
        );
        assert!(
            desc.contains("cola de impresión"),
            "must say printing goes through the Hub's print queue: {desc}"
        );
        assert!(
            desc.contains("erplora-app"),
            "must name erplora-app as the print host: {desc}"
        );
    }
}

#[cfg(test)]
mod fiscal_identity_tests {
    use super::*;
    use serde_json::json;

    /// The payload is a COPY of what the user already wrote once in `/setup`.
    #[test]
    fn it_maps_the_business_identity_onto_the_billing_profile_fields() {
        let settings = json!({
            "business_tax_id": " B12345674 ",
            "business_legal_name": "Bar Manolo SL",
            "business_address": "Calle Falsa 123",
            "country_code": "ES",
            "business_phone": "600000000",
        });
        let body = fiscal_identity_payload(&settings).expect("a filled-in identity publishes");

        assert_eq!(body["tax_id"], json!("B12345674"), "trimmed");
        assert_eq!(body["billing_name"], json!("Bar Manolo SL"));
        assert_eq!(body["billing_address"], json!("Calle Falsa 123"));
        assert_eq!(body["billing_country"], json!("ES"));
        assert!(
            !body.contains_key("stripe_customer_id"),
            "the hub sends identity, never billing plumbing: {body:?}"
        );
        assert!(
            !body.contains_key("business_phone"),
            "only the invoice identity travels: {body:?}"
        );
    }

    /// No tax id, nothing to publish — the SaaS would reject it anyway, and a round trip to say
    /// «you left the field empty» is a worse error than the one the form can give right away.
    #[test]
    fn without_a_tax_id_there_is_nothing_to_publish() {
        assert!(fiscal_identity_payload(&json!({ "business_legal_name": "Bar Manolo SL" })).is_none());
        assert!(fiscal_identity_payload(&json!({ "business_tax_id": "   " })).is_none());
    }
}
