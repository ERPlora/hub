//! Ejecución de queries declarativas (SELECT). ARQUITECTURA.md §4.
//!
//! Dos modos:
//! - **Simple** (sin bloque `list`): ejecuta el SQL tal cual y devuelve las filas.
//! - **Lista/paginada** (con bloque `list`): el runtime envuelve el SELECT base como
//!   subconsulta y compone, de forma genérica, búsqueda global + filtro por columna +
//!   orden por whitelist (anti-inyección) + `LIMIT/OFFSET`, y devuelve `{rows,total,limit,
//!   offset}` (§8.2). El módulo no escribe nada de esto a mano: lo declara en `module.json`.
use erplora_db::{DatabaseAdapter, Params};
use serde_json::{json, Value as Json};

use crate::errors::{Result, RuntimeError};
use crate::manifest::{FilterOp, ListSpec};
use crate::permissions;
use crate::registry::{Registry, RequestContext};


/// Resultado de una query de lista: la página de filas + el total filtrado (para el pager).
/// Es lo que viaja en `data` del envelope para queries paginadas (§7.6, §8.2).
#[derive(Debug, Clone, serde::Serialize)]
pub struct QueryPage {
    pub rows: Vec<Json>,
    pub total: u64,
    pub limit: u64,
    pub offset: u64,
}

/// Ejecuta `name(params)` y devuelve **solo las filas** (compat: lista ⇒ filas de la página).
pub async fn execute(
    db: &dyn DatabaseAdapter,
    registry: &Registry,
    name: &str,
    params: &Params,
    ctx: &RequestContext,
) -> Result<Vec<Json>> {
    Ok(execute_page(db, registry, name, params, ctx).await?.rows)
}

/// Ejecuta `name(params)` devolviendo la página completa (`rows` + `total` + `limit`/`offset`).
/// Para queries sin bloque `list`, `total` = nº de filas y `offset` = 0 (no hay paginación).
pub async fn execute_page(
    db: &dyn DatabaseAdapter,
    registry: &Registry,
    name: &str,
    params: &Params,
    ctx: &RequestContext,
) -> Result<QueryPage> {
    // **Namespace reservado del core** (ADR-0192): `hub.*` no pertenece a ningún módulo — lo sirve
    // el propio runtime. Un módulo no puede pegar a las rutas HTTP del core (el contrato es
    // WC → SDK → dispatcher), así que la identidad del hub se ofrece como una query más, con el
    // mismo gate de permisos. Va ANTES del registry: ningún módulo puede suplantarla.
    if let Some(rest) = name.strip_prefix(crate::hub_users::CORE_NAMESPACE) {
        let rows = crate::hub_users::core_query(db, registry, &ctx.hub_id, name, rest, ctx, params).await?;
        let total = rows.len() as u64;
        return Ok(QueryPage { rows, total, limit: total, offset: 0 });
    }
    let q = registry.get_query(name).ok_or_else(|| {
        // Tres ausencias distintas, tres errores (ADR-0127/0128): módulo NO instalado y módulo
        // DESACTIVADO son ausencias que `queryOptional` perdona; una query inexistente en un
        // módulo activo es un CONTRATO ROTO y explota.
        let owner = name.split('.').next().unwrap_or("");
        if owner.is_empty() || !registry.installed.iter().any(|m| m.id == owner) {
            return RuntimeError::ModuleNotInstalled { module: owner.to_string(), operation: name.to_string() };
        }
        if !registry.is_active(owner) {
            return RuntimeError::ModuleInactive { module: owner.to_string(), operation: name.to_string() };
        }
        RuntimeError::QueryNotFound(name.to_string())
    })?;
    permissions::check(ctx, &q.def.permission)?;

    // Validación del payload contra el JSON Schema declarado (compilado al instalar y
    // cacheado en el Registry): rechaza ANTES de tocar la BD (hub#27).
    if let Some(schema) = &q.schema {
        schema
            .validate(&Json::Object(params.clone()))
            .map_err(|detail| RuntimeError::InvalidPayload { name: name.to_string(), detail })?;
    }

    // Identidad de NEGOCIO GLOBAL del hub (fuente única país-agnóstica, `hub_settings` — ADR-0061) →
    // contexto, igual que en `commands::execute` (depth 0). El path de queries NO la cargaba, así que
    // `system_params` inyectaba `:business_tax_id`/`:business_legal_name`/`:business_address` VACÍOS y
    // un `config_get` (p.ej. VeriFactu) no podía resolver el obligado global hasta el siguiente save.
    // Enriquecemos aquí cuando falte, para que TODA query (no solo los commands) vea la identidad EN
    // VIVO. Degrada a vacío si los settings fallan.
    let enriched_ctx;
    let ctx = if ctx.business_tax_id.is_empty() {
        let f = crate::settings::get_all(db, &ctx.hub_id).await.unwrap_or(Json::Null);
        let get = |k: &str| f.get(k).and_then(|v| v.as_str()).unwrap_or("").to_string();
        // Same reader as `commands::execute` and as the ⛔ arm of `setup_status`, on purpose: the
        // own certificate if there is one, otherwise ERPlora's delegated one (ADR-0202 §2.1,
        // hub#319). Degrading to `false` keeps the ADR-0203 gate failing CLOSED.
        let has_cert = crate::certificate::can_sign(db, &ctx.hub_id)
            .await
            .unwrap_or(false);
        enriched_ctx = ctx
            .clone()
            .with_business(
                get("business_tax_id"),
                get("business_legal_name"),
                get("business_address"),
            )
            .with_certificate(has_cert);
        &enriched_ctx
    } else {
        ctx
    };

    let bound = crate::system_params(params, ctx);

    match &q.def.list {
        // Query simple: SQL tal cual; sin paginación.
        None => {
            let rows = db.query(&q.sql, &bound).await?.rows;
            let total = rows.len() as u64;
            Ok(QueryPage { rows, total, limit: total, offset: 0 })
        }
        // Query de lista: compone el SQL paginado de forma genérica.
        Some(spec) => run_list(db, &q.sql, spec, &bound).await,
    }
}

/// Compone y ejecuta el SQL paginado a partir del SELECT base y el `ListSpec`.
async fn run_list(
    db: &dyn DatabaseAdapter,
    base_sql: &str,
    spec: &ListSpec,
    bound: &Params,
) -> Result<QueryPage> {
    let mut p = bound.clone();

    // ── orden (whitelist + anti-inyección) ────────────────────────────────────────────────
    // `sort` recibido solo se acepta si está en la whitelist `spec.sort` (y es identificador
    // seguro). Si no, cae al `default_sort`, luego a la primera columna ordenable.
    let requested = p.get("sort").and_then(|v| v.as_str()).map(str::to_string);
    let sort_col = requested
        .filter(|s| spec.sort.iter().any(|c| c == s))
        .or_else(|| spec.default_sort.clone())
        .or_else(|| spec.sort.first().cloned())
        .filter(|c| is_ident(c));
    let dir = match p.get("dir").and_then(|v| v.as_str()) {
        Some(d) if d.eq_ignore_ascii_case("desc") => "DESC",
        Some(d) if d.eq_ignore_ascii_case("asc") => "ASC",
        _ if spec.default_dir.as_deref() == Some("desc") => "DESC",
        _ => "ASC",
    };

    // ── límite / offset ────────────────────────────────────────────────────────────────────
    // El `limit` que pides es el que recibes. Aquí hubo un tope duro (`clamp(1, 500)`) y era un
    // fallo, no una defensa: un hub con 800 productos pedía 800, recibía 500, y la respuesta no
    // decía nada — el TPV se quedaba sin la mitad del catálogo en silencio. Quien sabe cuántas
    // filas necesita es quien llama (una tabla quiere una página; un TPV quiere TODO su catálogo).
    // Sin `limit`, manda el `page_size` que el módulo declara en su manifest.
    let limit = p.get("limit").and_then(|v| v.as_u64()).unwrap_or(spec.page_size);
    let offset = p.get("offset").and_then(|v| v.as_u64()).unwrap_or(0);
    p.insert("limit".into(), json!(limit));
    p.insert("offset".into(), json!(offset));

    // ── condiciones WHERE (búsqueda + filtros por columna) ──────────────────────────────────
    // Un parámetro opcional AUSENTE (o null) NO genera condición ⇒ "sin filtro". No se usa el
    // centinela `(:p IS NULL OR …)`: Postgres fija el tipo del parámetro en su PRIMERA
    // aparición y `IS NULL` no aporta tipo ⇒ `could not determine data type of parameter`
    // (42P08) al preparar — TODA lista fallaba en Hub Cloud (decisión 2026-07-05). El SQL ya
    // se compone por llamada, así que emitir solo las condiciones provistas es equivalente.
    let mut conds: Vec<String> = Vec::new();
    let has = |k: &str| p.get(k).is_some_and(|v| !v.is_null());

    // `CAST(... AS TEXT)` en búsqueda/eq/like: la UI (inputs/selects HTML) manda strings, y la
    // nube es Postgres (estricto: `integer = text` da error). Comparar como texto en ambos lados
    // hace que un `'1'` de un <select> case con una columna entera en SQLite **y** Postgres.
    // `range` NO castea: compara con el tipo real (numérico o fecha ISO como texto), que es lo
    // correcto para `>=`/`<=` (un cast a texto rompería el orden numérico).
    if !spec.search.is_empty() && has("search") {
        let likes: Vec<String> = spec
            .search
            .iter()
            .filter(|c| is_ident(c))
            .map(|c| format!("CAST(sub.{c} AS TEXT) LIKE '%' || CAST(:search AS TEXT) || '%'"))
            .collect();
        if !likes.is_empty() {
            conds.push(format!("({})", likes.join(" OR ")));
        }
    }

    for (col, f) in &spec.filters {
        if !is_ident(col) {
            continue;
        }
        match f.op {
            FilterOp::Eq => {
                if has(&format!("f_{col}")) {
                    conds.push(format!("CAST(sub.{col} AS TEXT) = CAST(:f_{col} AS TEXT)"));
                }
            }
            FilterOp::Like => {
                if has(&format!("f_{col}")) {
                    conds.push(format!(
                        "CAST(sub.{col} AS TEXT) LIKE '%' || CAST(:f_{col} AS TEXT) || '%'"
                    ));
                }
            }
            FilterOp::Range => {
                if has(&format!("f_{col}_from")) {
                    conds.push(format!("sub.{col} >= :f_{col}_from"));
                }
                if has(&format!("f_{col}_to")) {
                    conds.push(format!("sub.{col} <= :f_{col}_to"));
                }
            }
        }
    }

    let where_clause = if conds.is_empty() {
        String::new()
    } else {
        format!(" WHERE {}", conds.join(" AND "))
    };
    let order_clause = match &sort_col {
        Some(c) => format!(" ORDER BY sub.{c} {dir}"),
        None => String::new(),
    };

    // El SELECT base se envuelve como tabla derivada; se le quita su `;` final si lo tuviera.
    let base = base_sql.trim().trim_end_matches(';').trim_end();
    let sql = format!(
        "SELECT sub.*, COUNT(*) OVER() AS _total FROM ( {base} ) AS sub{where_clause}{order_clause} LIMIT :limit OFFSET :offset"
    );

    let result = db.query(&sql, &p).await?;
    let total = result
        .rows
        .first()
        .and_then(|r| r.get("_total"))
        .and_then(|v| v.as_u64())
        .unwrap_or(0);
    let rows = result
        .rows
        .into_iter()
        .map(|mut r| {
            if let Some(obj) = r.as_object_mut() {
                obj.remove("_total");
            }
            r
        })
        .collect();

    Ok(QueryPage { rows, total, limit, offset })
}

/// ¿Es un identificador SQL seguro (`[A-Za-z_][A-Za-z0-9_]*`)? Solo estos se interpolan en el
/// SQL (columnas de `sort`/`filters` vienen del manifest de confianza; esto es defensa en
/// profundidad frente a un manifest malformado).
fn is_ident(s: &str) -> bool {
    let mut chars = s.chars();
    matches!(chars.next(), Some(c) if c.is_ascii_alphabetic() || c == '_')
        && s.chars().all(|c| c.is_ascii_alphanumeric() || c == '_')
}
