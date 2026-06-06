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

/// Tope duro de `limit` (defensa: una página no puede pedir filas ilimitadas).
const MAX_LIMIT: u64 = 500;

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
    let q = registry
        .get_query(name)
        .ok_or_else(|| RuntimeError::QueryNotFound(name.to_string()))?;
    permissions::check(ctx, &q.def.permission)?;
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
    let limit = p
        .get("limit")
        .and_then(|v| v.as_u64())
        .unwrap_or(spec.page_size)
        .clamp(1, MAX_LIMIT);
    let offset = p.get("offset").and_then(|v| v.as_u64()).unwrap_or(0);
    p.insert("limit".into(), json!(limit));
    p.insert("offset".into(), json!(offset));

    // ── condiciones WHERE (búsqueda + filtros por columna) ──────────────────────────────────
    // Centinela `IS NULL`: un parámetro ausente lo bindea el adapter como NULL ⇒ la condición
    // se cumple ⇒ "sin filtro". Así los valores numéricos/fecha se comparan con su tipo real
    // (no hace falta el truco `= ''`, que rompe en columnas no-texto).
    let mut conds: Vec<String> = Vec::new();

    // `CAST(... AS TEXT)` en búsqueda/eq/like: la UI (inputs/selects HTML) manda strings, y la
    // nube es Postgres (estricto: `integer = text` da error). Comparar como texto en ambos lados
    // hace que un `'1'` de un <select> case con una columna entera en SQLite **y** Postgres.
    // `range` NO castea: compara con el tipo real (numérico o fecha ISO como texto), que es lo
    // correcto para `>=`/`<=` (un cast a texto rompería el orden numérico).
    if !spec.search.is_empty() {
        let likes: Vec<String> = spec
            .search
            .iter()
            .filter(|c| is_ident(c))
            .map(|c| format!("CAST(sub.{c} AS TEXT) LIKE '%' || :search || '%'"))
            .collect();
        if !likes.is_empty() {
            conds.push(format!("(:search IS NULL OR {})", likes.join(" OR ")));
        }
    }

    for (col, f) in &spec.filters {
        if !is_ident(col) {
            continue;
        }
        match f.op {
            FilterOp::Eq => {
                conds.push(format!(
                    "(:f_{col} IS NULL OR CAST(sub.{col} AS TEXT) = CAST(:f_{col} AS TEXT))"
                ));
            }
            FilterOp::Like => {
                conds.push(format!(
                    "(:f_{col} IS NULL OR CAST(sub.{col} AS TEXT) LIKE '%' || CAST(:f_{col} AS TEXT) || '%')"
                ));
            }
            FilterOp::Range => {
                conds.push(format!("(:f_{col}_from IS NULL OR sub.{col} >= :f_{col}_from)"));
                conds.push(format!("(:f_{col}_to IS NULL OR sub.{col} <= :f_{col}_to)"));
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
