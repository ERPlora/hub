//! erplora-server — servidor Axum del runtime del tenant en modo cloud (ARQUITECTURA.md §7.5).
//!
//! Expone `execute_query`/`execute_command` por HTTP, los eventos por WebSocket (`/ws`), y la
//! **gestión de módulos** (listar / instalar / activar / desactivar / desinstalar = hot-plug).
//!
//! Rutas:
//!   GET  /healthz
//!   GET  /api/navigation                     menú de módulos ACTIVOS
//!   GET  /api/modules                        módulos instalados + estado
//!   POST /api/modules/install   {dir}        instala desde carpeta (extraída por erplora-source)
//!   POST /api/modules/:id/activate
//!   POST /api/modules/:id/deactivate
//!   POST /api/modules/:id/uninstall
//!   POST /api/query   {name, params}
//!   POST /api/command {name, payload}
//!   GET  /ws                                 stream de eventos (solo push)

use axum::extract::ws::{Message, WebSocket, WebSocketUpgrade};
use axum::extract::{Path, State};
use axum::http::{HeaderMap, StatusCode};
use axum::response::{IntoResponse, Response};
use axum::routing::{get, post};
use axum::{Json, Router};
use serde::Deserialize;
use serde_json::{json, Map, Value};

pub mod auth;
pub mod state;
pub mod session;

pub use state::{AppState, WsEvent};

/// Construye el router con todas las rutas montadas sobre `state`.
pub fn app(state: AppState) -> Router {
    Router::new()
        .route("/healthz", get(healthz))
        .route("/api/navigation", get(navigation))
        .route("/api/modules", get(list_modules))
        .route("/api/modules/install", post(install_module))
        .route("/api/modules/:id/activate", post(activate_module))
        .route("/api/modules/:id/deactivate", post(deactivate_module))
        .route("/api/modules/:id/uninstall", post(uninstall_module))
        .route("/api/query", post(query))
        .route("/api/command", post(command))
        .route("/ws", get(ws_upgrade))
        .with_state(state)
}

async fn healthz() -> &'static str {
    "ok"
}

#[derive(Deserialize)]
struct QueryReq {
    name: String,
    #[serde(default)]
    params: Map<String, Value>,
}

#[derive(Deserialize)]
struct CommandReq {
    name: String,
    #[serde(default)]
    payload: Map<String, Value>,
}

#[derive(Deserialize)]
struct InstallReq {
    /// Ruta a la carpeta del módulo ya extraída (la prepara erplora-source desde el S3 zip).
    dir: String,
}

fn err_response(e: erplora_runtime::RuntimeError) -> Response {
    use erplora_runtime::RuntimeError as E;
    let (status, code) = match &e {
        E::PermissionDenied(_) => (StatusCode::FORBIDDEN, "permission_denied"),
        E::QueryNotFound(_) | E::CommandNotFound(_) => (StatusCode::NOT_FOUND, "not_found"),
        E::NotImplemented(_) => (StatusCode::NOT_IMPLEMENTED, "not_implemented"),
        _ => (StatusCode::BAD_REQUEST, "error"),
    };
    let body = json!({ "ok": false, "error": { "code": code, "message": e.to_string() } });
    (status, Json(body)).into_response()
}

async fn navigation(State(st): State<AppState>) -> Response {
    let rt = st.runtime.lock().await;
    let items: Vec<Value> = rt
        .navigation()
        .iter()
        .map(|n| {
            json!({
                "module_id": n.module_id, "id": n.nav.id, "label": n.nav.label,
                "icon": n.nav.icon, "component": n.nav.component,
            })
        })
        .collect();
    Json(json!({ "ok": true, "data": items })).into_response()
}

async fn list_modules(State(st): State<AppState>) -> Response {
    let rt = st.runtime.lock().await;
    Json(json!({ "ok": true, "data": rt.modules() })).into_response()
}

async fn install_module(State(st): State<AppState>, Json(req): Json<InstallReq>) -> Response {
    let mut rt = st.runtime.lock().await;
    match rt.install_from_dir(std::path::Path::new(&req.dir)).await {
        Ok(id) => Json(json!({ "ok": true, "data": { "module_id": id } })).into_response(),
        Err(e) => err_response(e),
    }
}

async fn activate_module(State(st): State<AppState>, Path(id): Path<String>) -> Response {
    let mut rt = st.runtime.lock().await;
    match rt.activate(&id).await {
        Ok(()) => Json(json!({ "ok": true })).into_response(),
        Err(e) => err_response(e),
    }
}

async fn deactivate_module(State(st): State<AppState>, Path(id): Path<String>) -> Response {
    let mut rt = st.runtime.lock().await;
    match rt.deactivate(&id).await {
        Ok(()) => Json(json!({ "ok": true })).into_response(),
        Err(e) => err_response(e),
    }
}

async fn uninstall_module(State(st): State<AppState>, Path(id): Path<String>) -> Response {
    let mut rt = st.runtime.lock().await;
    match rt.uninstall(&id).await {
        Ok(()) => Json(json!({ "ok": true })).into_response(),
        Err(e) => err_response(e),
    }
}

async fn query(State(st): State<AppState>, headers: HeaderMap, Json(req): Json<QueryReq>) -> Response {
    let ctx = auth::context_from_headers(&headers);
    let rt = st.runtime.lock().await;
    // Queries de lista (con bloque `list`) devuelven `{rows,total,limit,offset}` para el pager;
    // el resto devuelve el array de filas tal cual (compat con get/stats/settings).
    if rt.is_list_query(&req.name) {
        match rt.execute_query_page(&req.name, &req.params, &ctx).await {
            Ok(page) => Json(json!({ "ok": true, "data": page })).into_response(),
            Err(e) => err_response(e),
        }
    } else {
        match rt.execute_query(&req.name, &req.params, &ctx).await {
            Ok(rows) => Json(json!({ "ok": true, "data": rows })).into_response(),
            Err(e) => err_response(e),
        }
    }
}

async fn command(State(st): State<AppState>, headers: HeaderMap, Json(req): Json<CommandReq>) -> Response {
    let ctx = auth::context_from_headers(&headers);
    let rt = st.runtime.lock().await;
    match rt.execute_command(&req.name, &req.payload, &ctx).await {
        Ok(data) => Json(json!({ "ok": true, "data": data })).into_response(),
        Err(e) => err_response(e),
    }
}

async fn ws_upgrade(State(st): State<AppState>, ws: WebSocketUpgrade) -> Response {
    ws.on_upgrade(move |socket| ws_loop(socket, st))
}

async fn ws_loop(mut socket: WebSocket, st: AppState) {
    let mut rx = st.events.subscribe();
    loop {
        match rx.recv().await {
            Ok(ev) => {
                let text = serde_json::to_string(&ev).unwrap_or_else(|_| "{}".into());
                if socket.send(Message::Text(text)).await.is_err() {
                    break;
                }
            }
            Err(tokio::sync::broadcast::error::RecvError::Lagged(_)) => continue,
            Err(_) => break,
        }
    }
}
