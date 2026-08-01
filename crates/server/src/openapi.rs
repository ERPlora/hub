//! Generador **OpenAPI 3.1 dinámico per-hub** (ADR-0057, `public-api.md` §4, refinado 2026-06-24).
//!
//! No se escribe a mano: recorre el `Registry` y emite un `path` por cada query/command marcado
//! `expose_api` de los módulos ACTIVOS. Como **OpenAPI 3.1 usa JSON Schema directamente**, el
//! `schema` del command → `requestBody` casi 1:1, y el `listSpec` de la query → los `parameters`
//! de filtro/orden/paginación. El spec refleja EXACTAMENTE los módulos instalados en este hub
//! (instalar un módulo amplía la API; desinstalarlo la reduce) — sin recompilar nada.
//!
//! **El server ya NO sirve Swagger UI.** El refinamiento de ADR-0057 (2026-06-24) mueve la doc a una
//! **vista Vue interna del Hub** (`apps/web` → `ApiDocsPage.vue`, que importa `swagger-ui-dist` de
//! npm y le pasa el spec por `spec:`), no una ruta HTML pública. Aquí queda SOLO el generador y
//! `GET /api/v1/openapi.json`, que ahora **exige una sesión de usuario válida** (interno, no
//! público): sin login no hay spec, y el principal API-key tampoco lo obtiene por aquí. La vista lo
//! pide con el fetch autenticado del web app (`X-Hub-Session`), así que Swagger nunca hace su propio
//! fetch sin auth.
use axum::extract::State;
use axum::http::{header, HeaderMap, StatusCode};
use axum::response::{IntoResponse, Response};
use axum::Json;
use serde_json::{json, Map, Value};

use erplora_runtime::manifest::{FilterOp, ListSpec};
use erplora_runtime::Registry;

use crate::auth;
use crate::state::AppState;

/// GET /api/v1/openapi.json — spec OpenAPI 3.1 de los módulos activos de este hub.
///
/// **Doble gate** (ADR-0057 §4 refinado + setting `api_docs_enabled`):
///  1. **Setting `api_docs_enabled`** (defensa en profundidad, server-side): si está en `false`
///     (su default) la ruta devuelve **404** — la API de docs no existe para el cliente, sea cual
///     sea su sesión. El toggle dejó de ser client-side: el server lo hace cumplir.
///  2. **Sesión de usuario** (cuando está enabled): cualquier usuario logueado puede leer el spec,
///     pero el anónimo recibe 401 y el principal API-key también (ver [`auth::require_user_session`]).
///
/// El `hub_id` viene del despliegue (config), no del header.
pub async fn openapi_json(State(st): State<AppState>, headers: HeaderMap) -> Response {
    let rt = st.runtime.lock().await;
    // 1) Gate server-side por setting: docs deshabilitadas → 404 (la ruta "no existe").
    if !api_docs_enabled(&rt).await {
        return (
            StatusCode::NOT_FOUND,
            Json(json!({ "ok": false, "error": "API docs deshabilitadas (setting `api_docs_enabled`)" })),
        )
            .into_response();
    }
    // 2) Gate por sesión (interno, no público).
    if let Err(e) = auth::require_user_session(&headers, &st.config, &rt).await {
        return (
            StatusCode::UNAUTHORIZED,
            Json(json!({ "ok": false, "error": e.message() })),
        )
            .into_response();
    }
    let spec = build_spec(rt.registry(), &st.hub_id());
    (
        StatusCode::OK,
        [(header::CONTENT_TYPE, "application/json")],
        Json(spec),
    )
        .into_response()
}

/// `true` si el setting `api_docs_enabled` del hub está activo. Lee el store de settings (tabla
/// `hub_settings` ∪ defaults); ante cualquier fallo de lectura cae a `false` (cerrado por defecto:
/// si no se puede confirmar que las docs están habilitadas, no se sirven).
async fn api_docs_enabled(rt: &erplora_runtime::Runtime) -> bool {
    rt.get_settings()
        .await
        .ok()
        .and_then(|s| s.get("api_docs_enabled").and_then(|v| v.as_bool()))
        .unwrap_or(false)
}

/// Construye el documento OpenAPI 3.1 completo a partir del `Registry`.
pub fn build_spec(reg: &Registry, hub_id: &str) -> Value {
    let mut paths = Map::new();
    let mut tags: Vec<Value> = Vec::new();

    for module in reg.modules_with_public_api() {
        let module_name = reg.module_display_name(&module);
        tags.push(json!({ "name": module, "description": module_name }));

        // Queries expuestas → POST /api/v1/{module}/q/{query} (lectura; params en el body).
        let mut queries = reg.exposed_queries(&module);
        queries.sort_by(|a, b| a.0.cmp(b.0));
        for (name, q) in queries {
            let op = name.strip_prefix(&format!("{module}.")).unwrap_or(name);
            let route = format!("/api/v1/{module}/q/{op}");
            paths.insert(
                route,
                json!({ "post": query_operation(&module, name, q.def.list.as_ref()) }),
            );
        }

        // Commands expuestos → POST /api/v1/{module}/c/{command} (escritura; payload en el body).
        let mut commands = reg.exposed_commands(&module);
        commands.sort_by(|a, b| a.0.cmp(b.0));
        for (name, c) in commands {
            let op = name.strip_prefix(&format!("{module}.")).unwrap_or(name);
            let route = format!("/api/v1/{module}/c/{op}");
            let body_schema = c.schema.as_ref().map(|s| (*s.raw).clone());
            paths.insert(
                route,
                json!({ "post": command_operation(&module, name, body_schema.clone()) }),
            );
            let webhook_route = format!("/webhook/{module}/{op}");
            paths.insert(
                webhook_route,
                json!({ "post": webhook_operation(&module, name, body_schema) }),
            );
        }
    }

    json!({
        "openapi": "3.1.0",
        "info": {
            "title": "ERPlora Hub — Public API",
            "version": "v1",
            "description": format!(
                "API pública REST de los módulos instalados en el hub `{hub_id}`. Cada operación es \
                 un query (lectura) o command (escritura) marcado `expose_api`. Autenticación: \
                 `Authorization: Bearer erpl_live_…` (API key del hub)."
            ),
        },
        // El servidor es same-origin; se deja relativo para no fijar host (proxies/ALB).
        "servers": [{ "url": "/" }],
        "tags": tags,
        "paths": paths,
        "components": {
            "securitySchemes": {
                "ApiKey": {
                    "type": "http",
                    "scheme": "bearer",
                    "bearerFormat": "erpl_live_<id>_<secret>",
                    "description": "API key del hub (ADR-0057). Se genera en Usuarios → API keys."
                }
            }
        },
        // Toda la API exige la API key (cada operación la hereda).
        "security": [{ "ApiKey": [] }]
    })
}

/// Operación OpenAPI de una **query**. El `listSpec` (si lo hay) se traduce a `parameters` de
/// filtro/orden/paginación; el body lleva los mismos como objeto `params` (la ruta del Hub recibe
/// `{params}` en el body, no query-string, así que también se documentan en el requestBody).
fn query_operation(module: &str, name: &str, list: Option<&ListSpec>) -> Value {
    let params_schema = list
        .map(list_params_schema)
        .unwrap_or_else(|| json!({ "type": "object" }));
    json!({
        "tags": [module],
        "operationId": name,
        "summary": format!("Query {name}"),
        "description": "Lectura declarativa del módulo (execute_query). Devuelve filas; si es una lista paginada, `{rows,total,limit,offset}`.",
        "requestBody": {
            "required": false,
            "content": {
                "application/json": {
                    "schema": {
                        "type": "object",
                        "properties": { "params": params_schema },
                        "additionalProperties": false
                    }
                }
            }
        },
        "responses": {
            "200": { "description": "OK", "content": { "application/json": { "schema": query_response_schema() } } },
            "401": { "description": "API key ausente, inválida o revocada" },
            "403": { "description": "La key no tiene el permiso de esta operación" },
            "404": { "description": "Operación inexistente o no expuesta (`expose_api`)" }
        }
    })
}

/// Operación OpenAPI de un **command**. El `schema` del payload (JSON Schema crudo) va directo al
/// `requestBody` (OpenAPI 3.1 = JSON Schema); si el command no declara schema, un objeto libre.
fn command_operation(module: &str, name: &str, body_schema: Option<Value>) -> Value {
    let payload_schema = body_schema.unwrap_or_else(|| json!({ "type": "object" }));
    json!({
        "tags": [module],
        "operationId": name,
        "summary": format!("Command {name}"),
        "description": "Mutación declarativa del módulo (execute_command). El payload se valida contra el JSON Schema del command.",
        "requestBody": {
            "required": true,
            "content": {
                "application/json": {
                    "schema": {
                        "type": "object",
                        "properties": { "payload": payload_schema },
                        "required": ["payload"],
                        "additionalProperties": false
                    }
                }
            }
        },
        "responses": {
            "200": { "description": "OK", "content": { "application/json": { "schema": command_response_schema() } } },
            "401": { "description": "API key ausente, inválida o revocada" },
            "403": { "description": "La key no tiene el permiso de esta operación" },
            "404": { "description": "Operación inexistente o no expuesta (`expose_api`)" },
            "422": { "description": "Payload inválido (no cumple el JSON Schema del command)" }
        }
    })
}

fn webhook_operation(module: &str, name: &str, body_schema: Option<Value>) -> Value {
    let payload_schema = body_schema.unwrap_or_else(|| json!({ "type": "object" }));
    json!({
        "tags": [module],
        "operationId": format!("webhook.{name}"),
        "summary": format!("Inbound webhook → {name}"),
        "description": "Envelope idempotente autenticado. `id` se deduplica por API key; el payload pasa al mismo execute_command y JSON Schema del módulo.",
        "requestBody": {
            "required": true,
            "content": {
                "application/json": {
                    "schema": {
                        "type": "object",
                        "required": ["id", "payload"],
                        "additionalProperties": false,
                        "properties": {
                            "id": { "type": "string", "minLength": 1, "maxLength": 128, "pattern": "^[A-Za-z0-9_.:-]+$" },
                            "occurred_at": { "type": "string", "format": "date-time" },
                            "payload": payload_schema
                        }
                    }
                }
            }
        },
        "responses": {
            "200": { "description": "Procesado o replay idempotente" },
            "400": { "description": "Envelope inválido" },
            "401": { "description": "API key ausente, inválida o revocada" },
            "403": { "description": "Scope insuficiente" },
            "409": { "description": "Id en proceso o reutilizado para otro command" },
            "429": { "description": "Cuota por minuto agotada; incluye Retry-After" }
        }
    })
}

/// Traduce el `listSpec` a un schema JSON de los `params` aceptados (búsqueda + orden + filtros +
/// paginación), espejo del motor de listas del runtime (`queries.rs`).
fn list_params_schema(spec: &ListSpec) -> Value {
    let mut props = Map::new();
    if !spec.search.is_empty() {
        props.insert(
            "search".into(),
            json!({ "type": "string", "description": format!("Búsqueda global sobre: {}", spec.search.join(", ")) }),
        );
    }
    if !spec.sort.is_empty() {
        props.insert(
            "sort".into(),
            json!({ "type": "string", "enum": spec.sort, "description": "Columna de orden (whitelist)." }),
        );
        props.insert(
            "dir".into(),
            json!({ "type": "string", "enum": ["asc", "desc"], "description": "Dirección de orden." }),
        );
    }
    // Filtros por columna: eq/like → un parámetro `f_<col>`; range → `f_<col>_from`/`_to`.
    for (col, filter) in &spec.filters {
        match filter.op {
            FilterOp::Eq | FilterOp::Like => {
                props.insert(
                    format!("f_{col}"),
                    json!({ "description": format!("Filtro `{:?}` por `{col}`.", filter.op) }),
                );
            }
            FilterOp::Range => {
                props.insert(
                    format!("f_{col}_from"),
                    json!({ "description": format!("Inicio del rango de `{col}`.") }),
                );
                props.insert(
                    format!("f_{col}_to"),
                    json!({ "description": format!("Fin del rango de `{col}`.") }),
                );
            }
        }
    }
    props.insert(
        "limit".into(),
        json!({ "type": "integer", "minimum": 1, "maximum": 500, "default": spec.page_size, "description": "Tamaño de página (clamp [1,500])." }),
    );
    props.insert(
        "offset".into(),
        json!({ "type": "integer", "minimum": 0, "default": 0 }),
    );
    json!({ "type": "object", "properties": props, "additionalProperties": false })
}

/// Forma de la respuesta de una query (filas simples o página paginada).
fn query_response_schema() -> Value {
    json!({
        "type": "object",
        "properties": {
            "ok": { "type": "boolean" },
            "data": {
                "oneOf": [
                    { "type": "array", "items": { "type": "object" }, "description": "Query simple: filas." },
                    {
                        "type": "object",
                        "description": "Query de lista: página paginada.",
                        "properties": {
                            "rows": { "type": "array", "items": { "type": "object" } },
                            "total": { "type": "integer" },
                            "limit": { "type": "integer" },
                            "offset": { "type": "integer" }
                        }
                    }
                ]
            }
        }
    })
}

/// Forma de la respuesta de un command (`{ok, data}`).
fn command_response_schema() -> Value {
    json!({
        "type": "object",
        "properties": { "ok": { "type": "boolean" }, "data": {} }
    })
}
