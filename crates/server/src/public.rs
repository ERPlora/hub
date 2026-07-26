//! Capa web **PÚBLICA** del Hub (ADR-0160, F0 — la frontera).
//!
//! El Hub es hoy 100% autenticado (`require_machine_registration` responde 428 a todo salvo salud +
//! contexto). Esta capa abre una superficie anónima MÍNIMA — una landing server-side del negocio —
//! **solo** cuando el dueño la activa con el setting `public.landing.visible` (default `false`).
//!
//! Invariante (Ioan): con el flag **desactivado** NO hay parte pública; `/`, `/p/*` y `/api/public/*`
//! se comportan EXACTAMENTE como hoy. El flag se lee del [`PublicSnapshot`] cacheado en el `AppState`
//! al arrancar (NO se pega a `hub_settings` en cada request). Cambiarlo requiere reiniciar (F0: sin
//! hot-reload por diseño).
//!
//! Alcance F0: frontera del gate + router público montado ANTES del fallback SPA + CSP estricta SOLO
//! en el árbol público.
//!
//! Alcance Wave 2 (esto): sobre esa frontera,
//!  - `POST /api/public/query` — endpoint **anónimo** de solo lectura. Puerta ÚNICA = el flag
//!    `public: true` del manifest de la query (default-deny; el `permission` NO gatea, no hay
//!    usuario). El `hub_id` lo inyecta el runtime (contexto de sistema), nunca el cliente.
//!  - `GET /p/<path>` — sirve la página pública: lee el JSON de bloques de `hub_settings`
//!    (`public.page.<path>`) y lo renderiza a HTML seguro con [`crate::public_render`] (NUNCA ejecuta
//!    JS del usuario). Sin página para ese path → 404, como antes.

use axum::extract::{Path, State};
use axum::http::{header, HeaderValue, StatusCode};
use axum::response::{IntoResponse, Response};
use axum::routing::{get, post};
use axum::{Json, Router};
use erplora_runtime::RequestContext;
use serde_json::{json, Value};

use crate::state::AppState;

/// CSP MÁS estricta del proyecto, aplicada SOLO al árbol público (columna de seguridad; ADR-0160):
/// nada de scripts, estilos solo self, imágenes self + `data:`. El árbol público no ejecuta JS.
pub const PUBLIC_CSP: &str =
    "default-src 'none'; script-src 'none'; style-src 'self'; img-src 'self' data:; \
     base-uri 'none'; form-action 'self'";

/// Snapshot INMUTABLE de los settings públicos del hub, cacheado en [`AppState`] al arrancar. Evita
/// leer `hub_settings` en cada request del gate/landing. Se carga UNA vez tras `ensure_system_tables`
/// (ver `crate::serve`); sin hot-reload (cambiar el flag requiere reiniciar el proceso — F0).
#[derive(Clone, Debug, Default)]
pub struct PublicSnapshot {
    /// Flag maestro `public.landing.visible` (default `false`). Con `false` la capa pública no existe.
    pub landing_visible: bool,
    /// Nombre visible del negocio (`business_legal_name` de `hub_settings`). Vacío ⇒ se omite/degrada.
    pub business_name: String,
    /// Dirección del negocio (`business_address` de `hub_settings`). Vacío ⇒ se omite.
    pub business_address: String,
}

impl PublicSnapshot {
    /// Construye el snapshot desde el objeto de settings (`hub_settings` ∪ defaults, tal cual lo
    /// devuelve `Runtime::get_settings`). Toma solo lo que la landing pública necesita; una clave
    /// ausente cae a su valor neutro (flag `false`, textos vacíos).
    pub fn from_settings(settings: &Value) -> Self {
        let str_of = |k: &str| {
            settings
                .get(k)
                .and_then(|v| v.as_str())
                .unwrap_or("")
                .to_string()
        };
        Self {
            landing_visible: settings
                .get("public.landing.visible")
                .and_then(|v| v.as_bool())
                .unwrap_or(false),
            business_name: str_of("business_legal_name"),
            business_address: str_of("business_address"),
        }
    }
}

/// ¿La ruta pertenece al árbol PÚBLICO? Exactamente `/`, lo que empieza por `/p/` y lo que empieza
/// por `/api/public/` (ADR-0160 F0). El gate deja pasar estas rutas SIN 428 cuando el flag está on.
pub fn is_public_path(path: &str) -> bool {
    path == "/" || path.starts_with("/p/") || path.starts_with("/api/public/")
}

/// Rutas del árbol público montadas ANTES del fallback SPA (rutas EXPLÍCITAS → no caen al
/// `index.html`). Llevan su [`PUBLIC_CSP`] propia vía un layer `overriding`: es autoritaria frente a
/// la CSP global de la app (aplicada con `if_not_present`, ver `crate::with_csp`), así el árbol
/// público nunca hereda una CSP más laxa. Se montan solo si el flag está activo (ver `crate::app`).
pub fn routes() -> Router<AppState> {
    use tower_http::set_header::SetResponseHeaderLayer;
    Router::new()
        .route("/", get(root))
        .route("/p/*path", get(page))
        .route("/api/public/query", post(public_query))
        .layer(SetResponseHeaderLayer::overriding(
            header::CONTENT_SECURITY_POLICY,
            HeaderValue::from_static(PUBLIC_CSP),
        ))
}

/// `GET /` (flag on) — landing HTML MÍNIMA server-side con los datos que ya hay en `hub_settings`.
async fn root(State(st): State<AppState>) -> Response {
    (
        StatusCode::OK,
        [(header::CONTENT_TYPE, "text/html; charset=utf-8")],
        render_landing(&st.public),
    )
        .into_response()
}

/// `GET /p/*path` (flag on) — sirve la página pública `path`. Lee el JSON de bloques guardado en
/// `hub_settings` (`public.page.<path>`) y lo renderiza a HTML seguro con [`crate::public_render`].
/// Sin página para ese path (o contenido corrupto) → 404 server-side (nunca la SPA).
///
/// TODO(datos dinámicos): las secciones alimentadas por `reads` (queries `public`) NO se ejecutan
/// aún server-side; esta fase mínima solo renderiza los bloques estáticos. Cablear los `reads` de
/// `public_pages[]` es un follow-up (usaría `Runtime::execute_query` con el mismo contexto de sistema
/// que `POST /api/public/query`).
async fn page(State(st): State<AppState>, Path(path): Path<String>) -> Response {
    // Resuelve el runtime del hub (single-tenant, o el pool de la org en cloud compartido). El hub_id
    // es el del despliegue (contexto de sistema), NUNCA aportado por el cliente.
    let Ok(arc) = st.runtime_for(&st.hub_id()).await else {
        return page_not_found();
    };
    let rt = arc.lock().await;
    match rt.get_public_page(&path).await {
        Ok(Some(doc)) => {
            let main = crate::public_render::render_blocks(&doc);
            (
                StatusCode::OK,
                [(header::CONTENT_TYPE, "text/html; charset=utf-8")],
                page_html(&st.public, &main),
            )
                .into_response()
        }
        // Sin página para ese path (o JSON corrupto) → 404, como antes.
        _ => page_not_found(),
    }
}

/// Body de `POST /api/public/query`: `{ "query": "<module>.<name>", "params": { … } }`.
#[derive(serde::Deserialize)]
struct PublicQueryReq {
    query: String,
    #[serde(default)]
    params: serde_json::Map<String, Value>,
}

/// `POST /api/public/query` (flag on) — endpoint **anónimo** de solo lectura (ADR-0160).
///
/// Puerta ÚNICA: la query debe estar marcada `public: true` en su manifest. NO se usa el `permission`
/// (no hay usuario). Cualquier otra query —aunque exista— o un command → 404, sin revelar existencia
/// (default-deny). El `hub_id` lo inyecta el runtime (contexto de sistema), NUNCA el cliente. Solo
/// `queries`, jamás `commands` (el dispatcher de queries no ejecuta escrituras).
async fn public_query(State(st): State<AppState>, Json(req): Json<PublicQueryReq>) -> Response {
    let Ok(arc) = st.runtime_for(&st.hub_id()).await else {
        return public_query_denied();
    };
    let rt = arc.lock().await;
    // Default-deny: solo queries `public: true`. Un command jamás casa (solo mira queries).
    if !rt.is_query_public(&req.query) {
        return public_query_denied();
    }
    // Contexto de SISTEMA: hub_id del despliegue + comodín de permisos (la puerta es el flag `public`,
    // no el `permission`). Mismo patrón que los `reads` (ADR-0069) / el scheduler: sin usuario.
    let ctx = RequestContext::new(rt.hub_id().to_string(), String::new(), ["*".to_string()]);
    match rt.execute_query(&req.query, &req.params, &ctx).await {
        Ok(rows) => Json(json!({ "ok": true, "data": rows })).into_response(),
        // Un fallo de ejecución no filtra la estructura interna al anónimo.
        Err(_) => public_query_denied(),
    }
}

/// 404 estable del endpoint público de queries (no revela si la query existe pero es privada).
fn public_query_denied() -> Response {
    (
        StatusCode::NOT_FOUND,
        Json(json!({ "ok": false, "error": { "code": "not_found" } })),
    )
        .into_response()
}

/// 404 HTML del árbol público para `/p/*` (path sin página guardada).
fn page_not_found() -> Response {
    (
        StatusCode::NOT_FOUND,
        [(header::CONTENT_TYPE, "text/html; charset=utf-8")],
        placeholder_html(),
    )
        .into_response()
}

/// HTML de la landing: título + nombre del negocio y, si existen, dirección. Sin CSS inline ni JS
/// (la [`PUBLIC_CSP`] prohíbe `style-src 'unsafe-inline'` y `script-src`). Todo dato de negocio va
/// escapado (viene de `hub_settings`, controlado por el dueño, pero se sirve anónimo).
pub fn render_landing(snap: &PublicSnapshot) -> String {
    let name = snap.business_name.trim();
    let name = if name.is_empty() { "ERPlora" } else { name };
    let title = escape_html(name);

    let mut main = format!("<h1>{title}</h1>");
    let address = snap.business_address.trim();
    if !address.is_empty() {
        main.push_str(&format!("<p class=\"address\">{}</p>", escape_html(address)));
    }

    format!(
        "<!doctype html>\n\
         <html lang=\"es\">\n\
         <head>\n\
         <meta charset=\"utf-8\">\n\
         <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n\
         <title>{title}</title>\n\
         </head>\n\
         <body>\n\
         <main>{main}</main>\n\
         </body>\n\
         </html>\n"
    )
}

/// Envuelve el HTML YA SANEADO del renderer de bloques en el shell de página pública. Sin CSS/JS
/// inline (la [`PUBLIC_CSP`] prohíbe `style-src 'unsafe-inline'` y `script-src`); el `main` viene del
/// renderer seguro ([`crate::public_render::render_blocks`]), así que se inserta tal cual. El título
/// sale del nombre del negocio (escapado), con fallback genérico.
fn page_html(snap: &PublicSnapshot, main: &str) -> String {
    let name = snap.business_name.trim();
    let name = if name.is_empty() { "ERPlora" } else { name };
    let title = escape_html(name);
    format!(
        "<!doctype html>\n\
         <html lang=\"es\">\n\
         <head>\n\
         <meta charset=\"utf-8\">\n\
         <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n\
         <title>{title}</title>\n\
         </head>\n\
         <body>\n\
         <main>{main}</main>\n\
         </body>\n\
         </html>\n"
    )
}

/// HTML del placeholder 404 de `/p/*` (F0).
fn placeholder_html() -> String {
    "<!doctype html>\n\
     <html lang=\"es\">\n\
     <head>\n\
     <meta charset=\"utf-8\">\n\
     <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n\
     <title>Página no encontrada</title>\n\
     </head>\n\
     <body>\n\
     <main><h1>Página no encontrada</h1></main>\n\
     </body>\n\
     </html>\n"
        .to_string()
}

/// Escapa los metacaracteres HTML de un texto (anti-inyección en el árbol público).
fn escape_html(s: &str) -> String {
    let mut out = String::with_capacity(s.len());
    for c in s.chars() {
        match c {
            '&' => out.push_str("&amp;"),
            '<' => out.push_str("&lt;"),
            '>' => out.push_str("&gt;"),
            '"' => out.push_str("&quot;"),
            '\'' => out.push_str("&#39;"),
            _ => out.push(c),
        }
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn is_public_path_matches_only_the_public_tree() {
        assert!(is_public_path("/"));
        assert!(is_public_path("/p/menu"));
        assert!(is_public_path("/api/public/query"));
        // NO públicas: la API autenticada, la SPA, y prefijos que solo "parecen" públicos.
        assert!(!is_public_path("/api/settings"));
        assert!(!is_public_path("/dashboard"));
        assert!(!is_public_path("/p")); // debe empezar por "/p/"
        assert!(!is_public_path("/pizza")); // "/p" no es "/p/"
        assert!(!is_public_path("/api/publications")); // no es "/api/public/"
    }

    #[test]
    fn from_settings_reads_flag_and_business_fields() {
        let settings = json!({
            "public.landing.visible": true,
            "business_legal_name": "Bar Pepe",
            "business_address": "Calle Mayor 1",
            "currency": "EUR",
        });
        let snap = PublicSnapshot::from_settings(&settings);
        assert!(snap.landing_visible);
        assert_eq!(snap.business_name, "Bar Pepe");
        assert_eq!(snap.business_address, "Calle Mayor 1");
    }

    #[test]
    fn from_settings_defaults_when_missing() {
        let snap = PublicSnapshot::from_settings(&json!({}));
        assert!(!snap.landing_visible, "flag ausente ⇒ capa pública cerrada");
        assert_eq!(snap.business_name, "");
        assert_eq!(snap.business_address, "");
    }

    #[test]
    fn render_landing_includes_business_data_escaped() {
        let snap = PublicSnapshot {
            landing_visible: true,
            business_name: "Bar <b>Pepe</b>".into(),
            business_address: "Calle & Co".into(),
        };
        let html = render_landing(&snap);
        assert!(html.contains("Bar &lt;b&gt;Pepe&lt;/b&gt;"), "nombre escapado");
        assert!(html.contains("Calle &amp; Co"), "dirección escapada");
        // Nunca el texto crudo peligroso.
        assert!(!html.contains("<b>Pepe</b>"));
    }

    #[test]
    fn render_landing_falls_back_to_generic_name_when_empty() {
        let html = render_landing(&PublicSnapshot::default());
        assert!(html.contains("ERPlora"), "sin nombre ⇒ título genérico, no vacío");
    }
}
