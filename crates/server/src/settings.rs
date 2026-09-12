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

use erplora_runtime::manifest::CapabilityKind;
use erplora_runtime::producer_facts::{DeclarationReference, ProducerFacts, ProducerFactsCache};

use crate::auth;
use crate::gateway_enrolment;
use crate::state::AppState;

/// `401` para fallo de auth (sin sesión / sesión inválida / rol insuficiente).
///
/// Lleva el **código** junto al mensaje (hub#1801). Esta es la puerta que el shell usa para
/// confirmar que una sesión está muerta (`probeSessionDead` en `apps/web/src/lib/runtime.ts` pide
/// `GET /api/settings` justo porque acepta cualquier rol), así que es el sitio donde el hub tiene
/// que poder decir **por qué**: sin el código, a un desalojo por el límite de dispositivos del plan
/// y a una sesión caducada por tiempo les queda la misma respuesta, y la pantalla de entrada solo
/// puede callarse. Va como campo **hermano** de `error`, que sigue siendo una cadena: los demás
/// consumidores de esta puerta no se enteran.
fn unauthorized(e: auth::AuthError) -> Response {
    (
        StatusCode::UNAUTHORIZED,
        Json(json!({ "ok": false, "error": e.message(), "code": e.code() })),
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
    let rt = arc.read().await;
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
///
/// Si el guardado toca la identidad fiscal, la **publica** en el SaaS (hub#1306) por el mismo
/// camino que la casilla de compartir: ver [`push_fiscal_identity`]. Fallar ahí NO cuesta el
/// guardado —los ajustes ya están escritos— pero tampoco se traga: viaja como
/// `fiscal_identity_publish_error` (código estable) en el objeto que se devuelve.
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
    // El guard del runtime se suelta ANTES de hablar con el SaaS: una llamada de red con el
    // mutex del hub en la mano bloquearía la caja entera mientras el control plane tarda.
    let mut settings = {
        let rt = arc.read().await;
        let admin = match auth::require_admin_session(&headers, &st.config, &rt).await {
            Ok(u) => u,
            Err(e) => return unauthorized(e),
        };
        // Auditoría: quién cambió la config (el `hub_user` admin de la sesión).
        let updated_by = format!("hub_user:{}", admin.id);
        match rt.set_settings(&updates, &updated_by).await {
            Ok(settings) => settings,
            Err(e) => return crate::err_response(e),
        }
    };

    if touches_fiscal_identity(&updates) {
        if let Err(failure) = push_fiscal_identity(&st, &settings).await {
            if let Some(code) = failure.reportable_code() {
                tracing::warn!(
                    code,
                    detail = %failure.detail(),
                    "settings: the fiscal identity was saved but could not be published to the control plane"
                );
                if let Some(object) = settings.as_object_mut() {
                    object.insert("fiscal_identity_publish_error".into(), json!(code));
                }
            }
        }
    }
    Json(settings).into_response()
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
    let rt = arc.read().await;
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
    let rt = arc.read().await;
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

/// El **sobre** que lee `unwrap(env)` de `@erplora/module-sdk` (hub#1688).
///
/// Estas tres puertas las abrió el shell, que hace su propio `fetch` y leía el cuerpo pelado. Desde
/// hub#1844 también las llama la PANTALLA del módulo de cumplimiento —el certificado es del negocio
/// pero su pantalla es del país, y el hub es país-agnóstico (ADR-0424)—, y el SDK solo sabe leer
/// `{ok, data}`: un cuerpo fuera del sobre le llega como `unknown error`, con lo que dijera de
/// verdad ya arrancado. Una sola forma para los dos llamantes, no dos.
fn enveloped<T: serde::Serialize>(data: T) -> Response {
    Json(json!({ "ok": true, "data": data })).into_response()
}

/// La mitad de MÓDULO del gate, en las tres puertas del certificado (hub#1844).
///
/// Quien **no** nombra módulo pasa: el shell no es un módulo y no nombra ninguno. Quien lo nombra
/// necesita `certificate` declarada en su manifest y concedida por el dueño (ADR-0079) — que es la
/// misma concesión que ya necesita para firmar con esa clave, así que esto no abre ninguna puerta
/// nueva a nadie. Sin este gate, darle la superficie al SDK se la habría dado a **todos** los
/// módulos instalados: cualquiera podría haber borrado el certificado del negocio y dejado sus
/// facturas sin salida, con un admin logueado y sin que nadie lo pidiera.
async fn certificate_capability(
    headers: &HeaderMap,
    rt: &erplora_runtime::Runtime,
) -> Result<(), Response> {
    crate::flows_api::require_module_capability(headers, rt, CapabilityKind::Certificate)
        .await
        .map(|_| ())
}

/// GET /api/business/certificate — estado del certificado del negocio (presente/ausente + metadatos,
/// SIN bytes ni contraseña). Auth = sesión de usuario (cualquier rol) **+ la capability
/// `certificate`** si quien llama nombra un módulo (hub#1844).
pub async fn get_business_certificate(State(st): State<AppState>, headers: HeaderMap) -> Response {
    let arc = match st.runtime_for(&st.hub_id()).await {
        Ok(rt) => rt,
        Err(e) => return crate::tenant_rejected(e),
    };
    let rt = arc.read().await;
    if let Err(e) = auth::require_user_session(&headers, &st.config, &rt).await {
        return crate::auth_rejected(e);
    }
    if let Err(response) = certificate_capability(&headers, &rt).await {
        return response;
    }
    match rt.business_certificate_status().await {
        Ok(s) => enveloped(s),
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
        // hub#1844: el código va DENTRO de `error`, que es donde `unwrap(env)` del `module-sdk` lo
        // busca. Sin él, la pantalla del módulo que sube el fichero recibe `unknown error` y no
        // puede decir cuál de los dos campos falta.
        return (
            StatusCode::UNPROCESSABLE_ENTITY,
            Json(json!({ "ok": false, "error": {
                "code": "invalid_field",
                "field": "pkcs12_b64",
                "message": "falta pkcs12_b64 (base64 del .p12)",
            }})),
        )
            .into_response();
    }
    let arc = match st.runtime_for(&st.hub_id()).await {
        Ok(rt) => rt,
        Err(e) => return crate::tenant_rejected(e),
    };
    let rt = arc.read().await;
    let admin = match auth::require_admin_session(&headers, &st.config, &rt).await {
        Ok(u) => u,
        Err(e) => return crate::auth_rejected(e),
    };
    if let Err(response) = certificate_capability(&headers, &rt).await {
        return response;
    }
    let by = format!("hub_user:{}", admin.id);
    if let Err(e) = rt.set_business_certificate(&b64, &password, &by).await {
        return crate::err_response(e);
    }
    match rt.business_certificate_status().await {
        Ok(s) => enveloped(s),
        Err(e) => crate::err_response(e),
    }
}

/// GET /api/business/gateway-identity — estado de la identidad de MÁQUINA para la pasarela
/// fiscal (hub#1432): nombres y fechas, nunca material de clave. Auth = sesión de usuario.
pub async fn get_gateway_identity(State(st): State<AppState>, headers: HeaderMap) -> Response {
    let arc = match st.runtime_for(&st.hub_id()).await {
        Ok(rt) => rt,
        Err(e) => return crate::tenant_rejected(e),
    };
    let rt = arc.read().await;
    if let Err(e) = auth::require_user_session(&headers, &st.config, &rt).await {
        return unauthorized(e);
    }
    match erplora_runtime::gateway_identity::status(rt.db(), &st.hub_id()).await {
        Ok(s) => Json(json!({
            "has_key": s.has_key,
            "has_certificate": s.has_certificate,
            "common_name": s.common_name,
            "not_after": s.not_after,
        }))
        .into_response(),
        Err(e) => crate::err_response(e),
    }
}

/// POST /api/business/gateway-identity/csr — genera (si no existe) la clave EN el hub y devuelve
/// el CSR para que el operador lo firme con la CA fiscal interna. Idempotente: repetirlo
/// re-deriva el CSR de la MISMA clave. Auth = sesión admin.
pub async fn post_gateway_identity_csr(State(st): State<AppState>, headers: HeaderMap) -> Response {
    let arc = match st.runtime_for(&st.hub_id()).await {
        Ok(rt) => rt,
        Err(e) => return crate::tenant_rejected(e),
    };
    let rt = arc.read().await;
    if let Err(e) = auth::require_admin_session(&headers, &st.config, &rt).await {
        return unauthorized(e);
    }
    let hub_id = st.hub_id();
    match erplora_runtime::gateway_identity::ensure_key_and_csr(rt.db(), &hub_id).await {
        Ok(csr_pem) => Json(json!({
            "csr_pem": csr_pem,
            "common_name": erplora_runtime::gateway_identity::common_name(&hub_id),
        }))
        .into_response(),
        Err(e) => crate::err_response(e),
    }
}

/// PUT /api/business/gateway-identity/certificate — instala el certificado firmado por el
/// operador + la CA interna. Body `{ certificate_pem, ca_pem }`. Auth = sesión admin.
pub async fn put_gateway_identity_certificate(
    State(st): State<AppState>,
    headers: HeaderMap,
    body: Option<Json<Map<String, Value>>>,
) -> Response {
    let updates = body.map(|b| b.0).unwrap_or_default();
    let certificate_pem = updates
        .get("certificate_pem")
        .and_then(|v| v.as_str())
        .unwrap_or("")
        .to_string();
    let ca_pem = updates
        .get("ca_pem")
        .and_then(|v| v.as_str())
        .unwrap_or("")
        .to_string();
    if certificate_pem.trim().is_empty() || ca_pem.trim().is_empty() {
        return (
            StatusCode::UNPROCESSABLE_ENTITY,
            Json(json!({ "ok": false, "error": "faltan certificate_pem y/o ca_pem (PEM)" })),
        )
            .into_response();
    }
    let arc = match st.runtime_for(&st.hub_id()).await {
        Ok(rt) => rt,
        Err(e) => return crate::tenant_rejected(e),
    };
    let rt = arc.read().await;
    if let Err(e) = auth::require_admin_session(&headers, &st.config, &rt).await {
        return unauthorized(e);
    }
    match erplora_runtime::gateway_identity::install_certificate(
        rt.db(),
        &st.hub_id(),
        &certificate_pem,
        &ca_pem,
    )
    .await
    {
        Ok(s) => Json(json!({
            "has_key": s.has_key,
            "has_certificate": s.has_certificate,
            "common_name": s.common_name,
            "not_after": s.not_after,
        }))
        .into_response(),
        Err(e) => crate::err_response(e),
    }
}

/// POST /api/business/gateway-identity/enrol — **el alta, de punta a punta y sin operador**
/// (hub#1457): presenta el CSR en el expediente legal del hub y recoge el certificado firmado.
///
/// Idempotente: repetirlo mientras la solicitud está pendiente no abre una segunda revisión (el
/// plano de control deduplica los MISMOS bytes) y, una vez aprobada, instala. Auth = sesión admin:
/// al otro lado viaja el `X-Hub-Token`, que es secreto del runtime (ADR-0003).
///
/// Un rechazo, un presupuesto agotado o una nube inalcanzable son **respuestas con código**
/// (ADR-0055) — la pantalla del módulo programa contra el código, nunca contra la prosa.
pub async fn post_gateway_identity_enrol(
    State(st): State<AppState>,
    headers: HeaderMap,
) -> Response {
    let arc = match st.runtime_for(&st.hub_id()).await {
        Ok(rt) => rt,
        Err(e) => return crate::tenant_rejected(e),
    };
    let rt = arc.read().await;
    if let Err(e) = auth::require_admin_session(&headers, &st.config, &rt).await {
        return unauthorized(e);
    }
    let Some(machine) = auth::machine_auth(&st) else {
        // Sin credencial de máquina el bootstrap no terminó: el hub no puede hablar con su nube.
        return (
            StatusCode::UNPROCESSABLE_ENTITY,
            Json(json!({
                "ok": false,
                "code": "enrolment.no_machine_credential",
                "detail": "este hub no tiene credencial de máquina: el bootstrap no ha terminado",
            })),
        )
            .into_response();
    };

    let hub_id = st.hub_id();
    let budget = gateway_enrolment::hourly_budget();
    let outcome = gateway_enrolment::enrol_once(
        &st.http,
        &st.config.cloud_base_url,
        &machine,
        rt.db(),
        &hub_id,
        &budget,
    )
    .await;

    let status = match erplora_runtime::gateway_identity::status(rt.db(), &hub_id).await {
        Ok(s) => s,
        Err(e) => return crate::err_response(e),
    };
    let mut body = json!({
        "common_name": status.common_name,
        "has_key": status.has_key,
        "has_certificate": status.has_certificate,
        "not_after": status.not_after,
    });
    match outcome {
        Ok(outcome) => {
            let (state, extra) = match outcome {
                gateway_enrolment::EnrolmentOutcome::Filed { version } => {
                    ("filed", json!({ "version": version }))
                }
                gateway_enrolment::EnrolmentOutcome::AwaitingReview { version } => {
                    ("awaiting_review", json!({ "version": version }))
                }
                gateway_enrolment::EnrolmentOutcome::Installed { not_after } => {
                    ("installed", json!({ "not_after": not_after }))
                }
                gateway_enrolment::EnrolmentOutcome::Rejected { version, reason } => (
                    "rejected",
                    json!({ "version": version, "rejected_reason": reason }),
                ),
                gateway_enrolment::EnrolmentOutcome::OutOfBudget => ("out_of_budget", json!({})),
            };
            body["state"] = json!(state);
            if let (Some(target), Some(extra)) = (body.as_object_mut(), extra.as_object()) {
                for (key, value) in extra {
                    target.insert(key.clone(), value.clone());
                }
            }
            Json(body).into_response()
        }
        Err(refusal) => (
            StatusCode::UNPROCESSABLE_ENTITY,
            Json(json!({
                "ok": false,
                "code": refusal.code,
                "detail": refusal.detail,
                "common_name": status.common_name,
                "has_certificate": status.has_certificate,
            })),
        )
            .into_response(),
    }
}

/// DELETE /api/business/gateway-identity — olvida la identidad entera (clave incluida), el
/// camino de rotación del operador. Auth = sesión admin.
pub async fn delete_gateway_identity(State(st): State<AppState>, headers: HeaderMap) -> Response {
    let arc = match st.runtime_for(&st.hub_id()).await {
        Ok(rt) => rt,
        Err(e) => return crate::tenant_rejected(e),
    };
    let rt = arc.read().await;
    if let Err(e) = auth::require_admin_session(&headers, &st.config, &rt).await {
        return unauthorized(e);
    }
    if let Err(e) = erplora_runtime::gateway_identity::delete(rt.db(), &st.hub_id()).await {
        return crate::err_response(e);
    }
    match erplora_runtime::gateway_identity::status(rt.db(), &st.hub_id()).await {
        Ok(s) => Json(json!({
            "has_key": s.has_key,
            "has_certificate": s.has_certificate,
            "common_name": s.common_name,
            "not_after": s.not_after,
        }))
        .into_response(),
        Err(e) => crate::err_response(e),
    }
}

/// DELETE /api/business/certificate — elimina el certificado del negocio. Auth = sesión admin
/// **+ la capability `certificate`** si quien llama nombra un módulo (hub#1844).
pub async fn delete_business_certificate(
    State(st): State<AppState>,
    headers: HeaderMap,
) -> Response {
    let arc = match st.runtime_for(&st.hub_id()).await {
        Ok(rt) => rt,
        Err(e) => return crate::tenant_rejected(e),
    };
    let rt = arc.read().await;
    if let Err(e) = auth::require_admin_session(&headers, &st.config, &rt).await {
        return crate::auth_rejected(e);
    }
    if let Err(response) = certificate_capability(&headers, &rt).await {
        return response;
    }
    if let Err(e) = rt.delete_business_certificate().await {
        return crate::err_response(e);
    }
    match rt.business_certificate_status().await {
        Ok(s) => enveloped(s),
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

/// Claves de `hub_settings` que dicen QUIÉN es el obligado tributario. Un guardado que toca
/// cualquiera de ellas republica la identidad; cualquier otro deja al SaaS en paz — si publicara en
/// cada guardado, apagar la doc de la API mandaría una identidad fiscal.
const FISCAL_IDENTITY_KEYS: [&str; 4] = [
    "business_tax_id",
    "business_legal_name",
    "business_address",
    "country_code",
];

fn touches_fiscal_identity(updates: &Map<String, Value>) -> bool {
    FISCAL_IDENTITY_KEYS
        .iter()
        .any(|key| updates.contains_key(*key))
}

/// Cuánto espera el hub al SaaS antes de rendirse con una publicación. Para cuando se llega aquí
/// el guardado YA está escrito: esto es una cortesía, y una caja no puede quedarse girando por
/// ella. Sin este límite, `reqwest` esperaría indefinidamente.
const PUBLISH_TIMEOUT: std::time::Duration = std::time::Duration::from_secs(5);

/// Por qué la identidad fiscal no llegó al SaaS. Códigos ESTABLES (ADR-0055): la pantalla se
/// explica contra ellos, nunca contra la prosa del error.
pub(crate) enum PublishFailure {
    /// Aún no hay NIF guardado: no hay identidad que publicar.
    NoTaxId,
    /// Este hub no tiene credencial de máquina (un `pnpm dev` local): no hay a quién avisar.
    NotEnrolled,
    /// El SaaS contestó, y dijo que no.
    Rejected(u16),
    /// No se pudo hablar con el SaaS (red, DNS, timeout).
    Unreachable(String),
}

impl PublishFailure {
    fn code(&self) -> &'static str {
        match self {
            Self::NoTaxId => "business_tax_id_required",
            Self::NotEnrolled => "hub_not_enrolled",
            Self::Rejected(_) => "cloud_rejected",
            Self::Unreachable(_) => "cloud_unreachable",
        }
    }

    /// El detalle para el LOG, nunca para la respuesta: el mensaje de `reqwest` lleva la URL
    /// interna del control plane (`error_redaction_door`).
    fn detail(&self) -> String {
        match self {
            Self::Rejected(status) => format!("control plane answered {status}"),
            Self::Unreachable(e) => e.clone(),
            other => other.code().to_string(),
        }
    }

    /// El código que se le CUENTA a quien guardó, o `None` si no hay nada que contar: sin NIF no
    /// había identidad, y sin credencial de máquina no había destinatario. Ninguna de las dos es
    /// un fallo del guardado, y avisar de ellas en cada guardado sería ruido que se aprende a
    /// ignorar — justo lo que hace invisible al fallo que sí importa.
    fn reportable_code(&self) -> Option<&'static str> {
        match self {
            Self::NoTaxId | Self::NotEnrolled => None,
            other => Some(other.code()),
        }
    }

    /// La respuesta HTTP de la puerta explícita (`POST /api/business/fiscal-identity`).
    fn into_response(self) -> Response {
        // 🔴 Ninguna rama es `5xx` (hub#1763). El hub es el ORIGEN: un `502`/`503` acuñado aquí es
        // indistinguible del que acuña el borde, que SUSTITUYE el cuerpo por su página — y con él
        // se va el `code` que la pantalla de identidad fiscal traduce (y el `status` del SaaS, que
        // es justo lo que convierte «no se pudo» en algo accionable). `424 Failed Dependency`
        // cruza cualquier proxy con el cuerpo intacto.
        let status = match self {
            Self::NoTaxId => axum::http::StatusCode::BAD_REQUEST,
            Self::NotEnrolled | Self::Rejected(_) | Self::Unreachable(_) => {
                crate::cloud_proxy::CLOUD_FAILED
            }
        };
        let mut body = Map::new();
        body.insert("ok".into(), json!(false));
        body.insert("error".into(), json!(self.code()));
        match self {
            Self::NoTaxId => {
                body.insert(
                    "message".into(),
                    json!("Fill in the business tax id before sharing it with ERPlora"),
                );
            }
            Self::Rejected(upstream) => {
                body.insert("status".into(), json!(upstream));
            }
            _ => {}
        }
        (status, Json(Value::Object(body))).into_response()
    }
}

/// **El único camino** por el que la identidad fiscal del negocio sube al SaaS, que crea/actualiza
/// el `BillingProfile` que paga este hub (ADR-0201 decisión 5) y **espeja el NIF del obligado**
/// para el otorgamiento del Anexo I (saas#1741). Lo comparten sus dos puertas: la casilla explícita
/// ([`publish_fiscal_identity`]) y el guardado de Ajustes → Negocio ([`put_settings`], hub#1306).
///
/// La llamada la hace el runtime porque el `cloud_api_token` es secreto del hub y nunca cruza al
/// navegador (ADR-0003).
pub(crate) async fn push_fiscal_identity(
    st: &AppState,
    settings: &Value,
) -> Result<(), PublishFailure> {
    let Some(body) = fiscal_identity_payload(settings) else {
        return Err(PublishFailure::NoTaxId);
    };
    let Some(machine) = auth::machine_auth(st) else {
        return Err(PublishFailure::NotEnrolled);
    };

    let req = cloud_client::CloudClient::new(&st.config.cloud_base_url).fiscal_identity(&machine);
    let client = reqwest::Client::builder()
        .timeout(PUBLISH_TIMEOUT)
        .build()
        .map_err(|e| PublishFailure::Unreachable(e.to_string()))?;
    let mut request = client.post(&req.url).json(&body);
    for (name, value) in req.headers {
        request = request.header(name, value);
    }
    match request.send().await {
        Ok(response) if response.status().is_success() => Ok(()),
        Ok(response) => Err(PublishFailure::Rejected(response.status().as_u16())),
        Err(e) => Err(PublishFailure::Unreachable(e.to_string())),
    }
}

/// POST /api/business/fiscal-identity — publica la identidad fiscal del negocio en el SaaS.
///
/// Es la casilla *"usar estos datos también para mi factura de ERPlora"* de Ajustes → Negocio: el
/// dato se escribió UNA vez aquí y la copia SUBE. Sin marcarla, el perfil se rellena aparte en el
/// SaaS (el caso de la gestoría que paga los hubs de sus clientes). **No es la única puerta**: el
/// propio guardado del NIF publica desde hub#1306, porque el SaaS necesita al obligado para el
/// otorgamiento del Anexo I, no solo para su factura.
///
/// Auth = sesión admin, porque la identidad fiscal es del dueño del negocio.
pub async fn publish_fiscal_identity(State(st): State<AppState>, headers: HeaderMap) -> Response {
    let arc = match st.runtime_for(&st.hub_id()).await {
        Ok(rt) => rt,
        Err(e) => return crate::tenant_rejected(e),
    };
    let settings = {
        let rt = arc.read().await;
        if let Err(e) = auth::require_admin_session(&headers, &st.config, &rt).await {
            return unauthorized(e);
        }
        match rt.get_settings().await {
            Ok(s) => s,
            Err(e) => return crate::err_response(e),
        }
    };

    match push_fiscal_identity(&st, &settings).await {
        Ok(()) => Json(json!({ "ok": true })).into_response(),
        Err(failure) => {
            tracing::warn!(
                code = failure.code(),
                detail = %failure.detail(),
                "settings: the fiscal identity could not be published to the control plane"
            );
            failure.into_response()
        }
    }
}

// ── Responsible declaration inside the product (art. 13.2 RRSIF — hub#528) ─────────────────────

/// `GET /api/system/declaration` — the *declaración responsable* of the version this hub is
/// running, from inside the product.
///
/// Art. 13.2 of the RRSIF (RD 1007/2023) requires the producer's declaration to be «por escrito y
/// de modo visible en el propio sistema informático **en cada una de sus versiones**». The public
/// archive on the control plane covers the other half of that article (the customer and the
/// reseller at the moment of acquisition); this door covers the in-product one, so a business
/// inspected by the AEAT can show it **from its own till**, offline from any browser bookmark.
///
/// Auth = any signed-in hub user, like `GET /api/system`. Not public: which version a hub runs is a
/// map of its attack surface, and «visible in the system» means visible to whoever uses the system.
pub async fn get_responsible_declaration(
    State(st): State<AppState>,
    headers: HeaderMap,
) -> Response {
    let arc = match st.runtime_for(&st.hub_id()).await {
        Ok(rt) => rt,
        Err(e) => return crate::tenant_rejected(e),
    };
    let rt = arc.read().await;
    if let Err(e) = auth::require_user_session(&headers, &st.config, &rt).await {
        return unauthorized(e);
    }
    Json(declaration_payload(
        ProducerFactsCache::global().current().as_ref(),
        ProducerFactsCache::global().current_declaration().as_ref(),
        crate::version::HUB_VERSION,
        &st.hub_id(),
        &st.config.cloud_base_url,
    ))
    .into_response()
}

/// What the panel shows — and it is the **same `SistemaInformatico` block that travels inside every
/// record** (ADR-0202 §5.1, hub#323), never a copy of it.
///
/// Nine elements with two owners: the control plane declares the manufacturer's seven (identity,
/// product, declared modality, `IndicadorMultiplesOT`) and this hub declares the two only it can —
/// `Version`, the binary it is actually running, and `NumeroInstalacion`, its own `hub_id`. The
/// keys keep the AEAT's literal Spanish spelling because that is what the XML carries: a
/// camelCase transliteration would invent a second name for a legal element, and the whole point of
/// this screen is that an inspector can put it next to a record and read the same strings.
///
/// **Nothing here is a constant.** A panel that printed `ERPLORA CLOUD SL / EC / 1.0.0` from
/// literals looks identical to this one until the day the control plane corrects the block — and
/// then the till certifies one identity while every invoice declares another, which is exactly what
/// makes the declaration sanctionable. `crates/server/tests/responsible_declaration.rs` cross-checks
/// every value against a real envelope built by the fiscal engine.
///
/// `facts = None` is a hub nobody has told yet (it has never reached the control plane). There are
/// no defaults for a legal declaration — the engine refuses to build the envelope in that state —
/// so the block comes back `null` and the screen says so, instead of filling the gap.
pub fn declaration_payload(
    facts: Option<&ProducerFacts>,
    declaration: Option<&DeclarationReference>,
    version: &str,
    hub_id: &str,
    cloud_base_url: &str,
) -> Value {
    let sistema_informatico = facts.map(|facts| {
        let mut block = facts.to_json();
        if let Some(fields) = block.as_object_mut() {
            fields.insert("Version".into(), Value::String(version.to_string()));
            fields.insert(
                "NumeroInstalacion".into(),
                Value::String(hub_id.to_string()),
            );
        }
        block
    });
    // hub#1449 / art. 13.3 RRSIF: while a single declaration is in force, the archive's ROOT
    // resolves to it and composing the root worked by coincidence. The day a second one is
    // issued, a hub still running the release the first one covers must keep linking THAT text —
    // only the control plane knows which one that is, and it names it on the heartbeat. The root
    // is a FALLBACK for a control plane that has said nothing (an older SaaS, a hub that has never
    // reached it, or an archive it could not read), never the answer once an exact one is known.
    let declaration_url = match declaration {
        Some(declaration) => declaration.url.clone(),
        None => format!(
            "{}/legal/declaracion-responsable/",
            cloud_base_url.trim_end_matches('/')
        ),
    };
    let mut payload = json!({
        // The two facts this hub owns travel at the top level too: they are what the screen can
        // always show, including on a hub the control plane has never spoken to.
        "version": version,
        "numeroInstalacion": hub_id,
        "declarationUrl": declaration_url,
        "sistemaInformatico": sistema_informatico,
    });
    // hub#1510 / art. 13.3 RRSIF: the link alone does not say WHICH text it points at, and several
    // declarations coexist — one per range of versions. Naming the reference (`v1`, `v2`…) next to
    // it is what lets an inspector standing at the till check that the text they are reading is the
    // one covering this release, without following the URL and comparing folder names.
    //
    // It rides at the TOP level, beside `declarationUrl`: it is a property of the declaration, not
    // one of the nine elements of `SistemaInformatico` that travel inside every record — and it is
    // NOT the binary's `version`, which is the release this hub runs, not the text that covers it.
    //
    // ABSENT, never an empty string: without a reference the link falls back to the archive root,
    // and the root has no version to name. A `""` on the wire would paint an empty label next to
    // the link and read as «this declaration has no version», which is a different claim.
    if let (Some(declaration), Some(fields)) = (declaration, payload.as_object_mut()) {
        fields.insert(
            "declarationVersion".into(),
            Value::String(declaration.version.clone()),
        );
    }
    payload
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
        assert!(
            fiscal_identity_payload(&json!({ "business_legal_name": "Bar Manolo SL" })).is_none()
        );
        assert!(fiscal_identity_payload(&json!({ "business_tax_id": "   " })).is_none());
    }
}
