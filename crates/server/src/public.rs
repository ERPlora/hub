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
//! Sobre esa frontera:
//!  - `POST /api/public/query` — endpoint **anónimo** de solo lectura. Puerta ÚNICA = el flag
//!    `public: true` del manifest de la query (default-deny; el `permission` NO gatea, no hay
//!    usuario). El `hub_id` lo inyecta el runtime (contexto de sistema), nunca el cliente.
//!  - `GET /p/<path>` — sirve la página pública: lee el JSON de bloques de `hub_settings`
//!    (`public.page.<path>`), ejecuta únicamente las `reads` marcadas `public` en el manifest y lo
//!    renderiza a HTML seguro con [`crate::public_render`] (NUNCA ejecuta JS del usuario). Sin
//!    página para ese path → 404, como antes. Emite ETag del HTML final.

use axum::extract::{Path, State};
use axum::http::{header, HeaderMap, HeaderValue, StatusCode};
use axum::response::{IntoResponse, Response};
use axum::routing::{get, post};
use axum::{Json, Router};
use erplora_runtime::RequestContext;
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::time::Duration;

use crate::state::AppState;

const MAX_PAGE_BYTES: usize = 512 * 1024;
const MAX_PAGE_BLOCKS: usize = 200;

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
    path == "/"
        || path.starts_with("/p/")
        || path.starts_with("/api/public/")
        || path.starts_with("/files/pages/")
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
        .route("/files/pages/*path", get(crate::media::public_page_media))
        .route("/api/public/query", post(public_query))
        .layer(SetResponseHeaderLayer::overriding(
            header::CONTENT_SECURITY_POLICY,
            HeaderValue::from_static(PUBLIC_CSP),
        ))
}

/// Normaliza el path de autoría. Se permiten segmentos URL legibles; no se admiten claves vacías,
/// `.`/`..` ni caracteres capaces de escapar del namespace `public.page.*`.
fn normalized_page_path(raw: &str) -> Option<String> {
    let path = raw.trim_matches('/');
    if path.is_empty() || path.len() > 120 {
        return None;
    }
    let valid = path.split('/').all(|segment| {
        !segment.is_empty()
            && segment != "."
            && segment != ".."
            && segment
                .chars()
                .all(|c| c.is_ascii_alphanumeric() || matches!(c, '-' | '_'))
    });
    valid.then(|| path.to_ascii_lowercase())
}

fn valid_editor_document(doc: &Value) -> bool {
    let Some(blocks) = doc.get("blocks").and_then(Value::as_array) else {
        return false;
    };
    blocks.len() <= MAX_PAGE_BLOCKS
        && doc.to_string().len() <= MAX_PAGE_BYTES
        && blocks.iter().all(|block| {
            block.get("type").and_then(Value::as_str).is_some()
                && block.get("data").is_some_and(Value::is_object)
        })
}

fn editor_bad_request(message: &str) -> Response {
    (
        StatusCode::UNPROCESSABLE_ENTITY,
        Json(json!({ "ok": false, "error": message })),
    )
        .into_response()
}

/// GET /api/public-pages/*path — fuente JSON de una página para el editor autenticado.
pub async fn get_page_source(
    State(st): State<AppState>,
    headers: HeaderMap,
    Path(path): Path<String>,
) -> Response {
    let Some(path) = normalized_page_path(&path) else {
        return editor_bad_request("path público inválido");
    };
    let rt = st.runtime.lock().await;
    if let Err(error) = crate::auth::require_admin_session(&headers, &st.config, &rt).await {
        return (
            StatusCode::UNAUTHORIZED,
            Json(json!({ "ok": false, "error": error.message() })),
        )
            .into_response();
    }
    match rt.get_public_page(&path).await {
        Ok(doc) => Json(json!({
            "ok": true,
            "data": doc.unwrap_or_else(|| json!({ "blocks": [] })),
        }))
        .into_response(),
        Err(error) => crate::err_response(error),
    }
}

/// PUT /api/public-pages/*path — persiste JSON de bloques Editor.js. Solo owner/admin; el JSON se
/// valida y acota antes de tocar la BD. El renderer Rust sigue siendo la frontera final default-deny.
pub async fn put_page_source(
    State(st): State<AppState>,
    headers: HeaderMap,
    Path(path): Path<String>,
    Json(doc): Json<Value>,
) -> Response {
    let Some(path) = normalized_page_path(&path) else {
        return editor_bad_request("path público inválido");
    };
    if !valid_editor_document(&doc) {
        return editor_bad_request("documento Editor.js inválido o demasiado grande");
    }
    let rt = st.runtime.lock().await;
    let admin = match crate::auth::require_admin_session(&headers, &st.config, &rt).await {
        Ok(admin) => admin,
        Err(error) => {
            return (
                StatusCode::UNAUTHORIZED,
                Json(json!({ "ok": false, "error": error.message() })),
            )
                .into_response()
        }
    };
    let updated_by = format!("hub_user:{}", admin.id);
    match rt.set_public_page(&path, &doc, &updated_by).await {
        Ok(()) => Json(json!({ "ok": true, "data": doc })).into_response(),
        Err(error) => crate::err_response(error),
    }
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
/// Si el módulo declara la ruta en `public_pages[]`, sus `reads` se ejecutan server-side solo cuando
/// la query conserva `public: true`; una referencia privada/rota se omite (default-deny).
async fn page(
    State(st): State<AppState>,
    headers: HeaderMap,
    Path(path): Path<String>,
) -> Response {
    // Resuelve el runtime del hub (single-tenant, o el pool de la org en cloud compartido). El hub_id
    // es el del despliegue (contexto de sistema), NUNCA aportado por el cliente.
    let Ok(arc) = st.runtime_for(&st.hub_id()).await else {
        return page_not_found();
    };
    let rt = arc.lock().await;
    match rt.get_public_page(&path).await {
        Ok(Some(doc)) => {
            let definition = rt.public_page_definition(&path);
            let mut main = crate::public_render::render_blocks(&doc);
            if let Some((_, page)) = &definition {
                let ctx = RequestContext::new(
                    rt.hub_id().to_string(),
                    String::new(),
                    ["*".to_string()],
                );
                for query in &page.reads {
                    // Doble default-deny: `reads` solo es una referencia; el flag de la query
                    // sigue siendo la autoridad. Un typo o una query privada se omite sin filtrar
                    // si existe ni degradar el contenido estático de la página.
                    if !rt.is_query_public(query) {
                        continue;
                    }
                    if let Ok(rows) = rt.execute_query(query, &serde_json::Map::new(), &ctx).await {
                        main.push_str(&render_public_rows(query, &rows));
                    }
                }
            }
            let title = definition.as_ref().map(|(_, page)| page.title.as_str());
            cacheable_html(&headers, page_html(&st.public, title, &main))
        }
        // Sin página para ese path (o JSON corrupto) → 404, como antes.
        _ => page_not_found(),
    }
}

/// Render genérico y sin scripts de las `reads` vivas declaradas por el módulo. La forma del dato
/// es deliberadamente transparente (JSON en `<pre>`); un renderer de dominio puede evolucionar
/// después sin que esta frontera ejecute HTML/JS aportado por el tenant.
fn render_public_rows(query: &str, rows: &[Value]) -> String {
    let data = serde_json::to_string_pretty(rows).unwrap_or_else(|_| "[]".to_string());
    format!(
        "<section class=\"public-data\" data-query=\"{}\"><h2>{}</h2><pre>{}</pre></section>",
        escape_html(query),
        escape_html(query),
        escape_html(&data),
    )
}

/// ETag fuerte del HTML final. `304` conserva el ETag y evita retransferir páginas sin cambios.
fn cacheable_html(request_headers: &HeaderMap, html: String) -> Response {
    let etag = format!("\"{:x}\"", Sha256::digest(html.as_bytes()));
    if request_headers
        .get(header::IF_NONE_MATCH)
        .and_then(|value| value.to_str().ok())
        .is_some_and(|value| value.split(',').any(|candidate| candidate.trim() == etag))
    {
        return Response::builder()
            .status(StatusCode::NOT_MODIFIED)
            .header(header::ETAG, etag)
            .body(axum::body::Body::empty())
            .unwrap_or_else(|_| page_not_found());
    }
    Response::builder()
        .status(StatusCode::OK)
        .header(header::CONTENT_TYPE, "text/html; charset=utf-8")
        .header(header::ETAG, etag)
        .body(axum::body::Body::from(html))
        .unwrap_or_else(|_| page_not_found())
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
    // Lectura anónima: cuota conservadora por hub+query. No hay commands públicos en v1, así que
    // Turnstile no se introduce en un flujo que no escribe; cualquier `public_write` sigue ausente.
    if let Err(retry_after) = st.rate_limits.check(
        format!("public:{}:{}", st.hub_id(), req.query),
        120,
        Duration::from_secs(60),
    ) {
        return Response::builder()
            .status(StatusCode::TOO_MANY_REQUESTS)
            .header(header::RETRY_AFTER, retry_after.to_string())
            .header(header::CONTENT_TYPE, "application/json")
            .body(axum::body::Body::from(
                json!({ "ok": false, "error": { "code": "rate_limited" } }).to_string(),
            ))
            .unwrap_or_else(|_| public_query_denied());
    }
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
fn page_html(snap: &PublicSnapshot, page_title: Option<&str>, main: &str) -> String {
    let name = snap.business_name.trim();
    let name = if name.is_empty() { "ERPlora" } else { name };
    let title = page_title
        .filter(|title| !title.trim().is_empty())
        .map(|title| format!("{} · {}", title.trim(), name))
        .unwrap_or_else(|| name.to_string());
    let title = escape_html(&title);
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
        assert!(is_public_path("/files/pages/menu/foto.png"));
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

    #[test]
    fn editor_paths_and_documents_are_bounded() {
        assert_eq!(normalized_page_path("/Carta/Verano/"), Some("carta/verano".into()));
        assert_eq!(normalized_page_path("../secreto"), None);
        assert!(valid_editor_document(&json!({
            "blocks": [{ "type": "paragraph", "data": { "text": "hola" } }]
        })));
        assert!(!valid_editor_document(&json!({ "blocks": [{ "type": "paragraph" }] })));
    }
}
