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

/// Ceiling for a whole-set read, so a runaway loop cannot eat the process alive (hub#650).
///
/// It is deliberately far above any catalogue this is meant for — tax rules, payment methods,
/// recipients — and hitting it is a LOUD error, never a quiet truncation. Silence is the exact
/// failure this function stopped having.
const WHOLE_SET_CAP: usize = 100_000;

/// Ejecuta `name(params)` y devuelve **todas las filas** que la query da para esos `params`.
///
/// hub#650 — antes devolvía `execute_page(...).rows`, es decir **una sola página**, y ese era el
/// contrato equivocado: quien llama aquí quiere un CONJUNTO, no una pantalla. Quien quiere una
/// página llama a [`execute_page`], que es lo que hace la capa HTTP de las listas. Los que pasaban
/// por aquí son justo los que no pueden trabajar con la mitad de los datos:
///
///   - el bloque `reads` de un command (`sales.complete_sale` precarga `taxes.rules.list`, que
///     declara `page_size: 50`) — un impuesto calculado contra un catálogo truncado sale MAL;
///   - el `guard_query` de un command — un guard que solo ve 50 filas tiene un agujero;
///   - el `recipient_query` de `host.notify` — a los de la fila 51 no se les avisa nunca.
///
/// **Un `limit` explícito sigue mandando**: es el tope que puso el llamador, y es la misma regla
/// que ya seguía `queryAll` en el SDK del cliente. Sin ella, «dame todo» no tendría contrario.
pub async fn execute(
    db: &dyn DatabaseAdapter,
    registry: &Registry,
    name: &str,
    params: &Params,
    ctx: &RequestContext,
) -> Result<Vec<Json>> {
    // El llamador puso su propio tope: se respeta tal cual, en un solo viaje.
    if params.get("limit").and_then(|v| v.as_u64()).is_some() {
        return Ok(execute_page(db, registry, name, params, ctx).await?.rows);
    }

    // La PRIMERA página se pide con los `params` TAL CUAL llegaron, sin añadir nada.
    //
    // Esto no es una optimización, es corrección: muchas queries validan su payload contra un JSON
    // Schema con `additionalProperties: false`, así que meterles un `offset` que no declaran las
    // hace fallar. Y fallaba justo donde más duele — el `settings_query` de un `protects` se
    // saltaba con «guard skipped (open)», o sea que el arreglo ABRÍA un guard que debía denegar.
    let first = execute_page(db, registry, name, params, ctx).await?;
    let total = first.total;
    let mut offset = first.offset + first.rows.len() as u64;
    let mut out = first.rows;

    // Una query SIN bloque `list` devuelve todo de una y `total` = nº de filas: sale por aquí sin
    // un segundo viaje y sin haber visto jamás un `offset`. Solo se pagina lo que de verdad pagina.
    while !out.is_empty() && offset < total {
        if out.len() > WHOLE_SET_CAP {
            return Err(crate::RuntimeError::Other(format!(
                "query `{name}`: más de {WHOLE_SET_CAP} filas para una lectura completa; \
                 acota con `limit` en vez de cargarlas todas"
            )));
        }
        let mut page_params = params.clone();
        page_params.insert("offset".into(), serde_json::json!(offset));
        let page = execute_page(db, registry, name, &page_params, ctx).await?;
        if page.rows.is_empty() {
            break; // el `total` mentía; parar es mejor que girar en vacío
        }
        offset += page.rows.len() as u64;
        out.extend(page.rows);
    }
    Ok(out)
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
        // The core decides the page shape itself: whole-set for the small catalogues, a real page
        // for `approvals.list` (hub#884), which runs through `run_list` like any module list.
        return crate::hub_users::core_query(db, registry, &ctx.hub_id, name, rest, ctx, params)
            .await;
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
    let coerced;
    let params = if let Some(schema) = &q.schema {
        schema
            .validate(&Json::Object(params.clone()))
            .map_err(|detail| RuntimeError::InvalidPayload { name: name.to_string(), detail })?;
        // hub#1092: los números se bindean con la FORMA que el schema declara (`number`→f64,
        // `integer`→i64), no con la del valor accidental — un filtro numérico enviado como `3`
        // y luego como `3.5` no debe re-preparar (ni corromper) la misma sentencia.
        let mut p = params.clone();
        schema.coerce_declared_number_shapes(&mut p);
        coerced = p;
        &coerced
    } else {
        params
    };

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
            // EL RELOJ y EL IDIOMA (hub#1022/hub#1098), misma resolución que `commands::execute`:
            // sin esto, un SELECT que binde `:timezone`/`:caller_lang` vería los fallbacks UTC/`es`
            // aunque el hub hubiera declarado otra cosa — y cada módulo volvería a resolvérselo en
            // SQL (lo que taxes#38 hizo y taxes#40 rompió).
            .with_timezone(
                crate::settings::timezone_of(db, &ctx.hub_id)
                    .await
                    .map(|tz| tz.name().to_string())
                    .unwrap_or_else(|_| "UTC".to_string()),
            )
            .with_caller_lang(crate::effective_caller_lang(db, &f, &ctx.hub_id, &ctx.user_id).await)
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
        // hub#1173: the vocabulary check runs on the params the CALLER sent, never on `bound` —
        // `system_params` injects `:hub_id`, `:now`, `:caller_lang`… into every call, and checking
        // the enriched map would refuse the runtime's own context on the first request.
        Some(spec) => {
            reject_undeclared_params(name, &q.sql, spec, params)?;
            run_list(db, name, &q.sql, spec, &bound).await
        }
    }
}

// ── vocabulario de una lista (hub#1173) ──────────────────────────────────────────────────────

/// Los nombres de parámetro que una query de lista ACEPTA, en el orden en que un autor los busca.
///
/// Son exactamente los tres sitios donde una lista declara algo que se pueda pasar:
///
///  1. el vocabulario del propio motor — `limit`/`offset`/`search`/`sort`/`dir`;
///  2. un `f_<col>` por cada filtro `eq`/`like` del bloque `list`, y el par `f_<col>_from` /
///     `f_<col>_to` por cada `range` — que es la forma que el SDK pone en el cable
///     (`buildListParams` aplana `filters` a `f_<col>` **diga lo que diga el manifest**, así que
///     una columna no declarada llega bien prefijada y hay que cazarla igual);
///  3. cualquier bind que su SQL base referencie (`:cart_id`) — que es donde una lista declara sus
///     params de contexto (hub#1086), y por eso se lee del SQL y no de una segunda lista.
///
/// Los params de sistema NO entran: no los manda el llamador, los inyecta
/// [`crate::system_params`] después. Ver [`reject_undeclared_params`].
pub(crate) fn accepted_params(base_sql: &str, spec: &ListSpec) -> Vec<String> {
    let mut out: Vec<String> = ["limit", "offset", "search", "sort", "dir"]
        .iter()
        .map(|s| (*s).to_string())
        .collect();
    for (col, f) in &spec.filters {
        match f.op {
            FilterOp::Range => {
                out.push(format!("f_{col}_from"));
                out.push(format!("f_{col}_to"));
            }
            FilterOp::Eq | FilterOp::Like => out.push(format!("f_{col}")),
        }
    }
    out.extend(all_binds(base_sql));
    out.sort();
    out.dedup();
    out
}

/// Rechaza el primer parámetro que la query de lista no declara (hub#1173).
///
/// El fallo que cierra es el «éxito silencioso»: un filtro que la query no tiene se ignoraba y la
/// página respondía `200 ok` **con la lista entera**, indistinguible de un filtro que corrió y no
/// casó nada. Se refuta en vez de avisar porque el barrido de los 27 repos de módulo
/// (`origin/main`, 25/08/2026) encontró **dos** llamadas en el catálogo entero fuera del
/// vocabulario de su query, y las dos eran este mismo fallo vivo: `payments.methods.list` con
/// `active_only` (que solo existe en un COMENTARIO de su SQL — el cajero ve los métodos de pago
/// desactivados) y `services.services.list` con `page_size` (el param que el propio SDK documenta
/// como inexistente). No hay llamador legítimo al que romper.
///
/// Se rechaza UNO, el primero en orden estable: un error nombra el parámetro que hay que
/// arreglar, no una lista que hay que leer entera.
pub(crate) fn reject_undeclared_params(
    query: &str,
    base_sql: &str,
    spec: &ListSpec,
    params: &Params,
) -> Result<()> {
    let accepted = accepted_params(base_sql, spec);
    let mut sent: Vec<&String> = params.keys().collect();
    sent.sort();
    for name in sent {
        if !accepted.iter().any(|a| a == name) {
            return Err(RuntimeError::UnknownFilter {
                query: query.to_string(),
                param: name.clone(),
                accepted,
            });
        }
    }
    Ok(())
}

/// Todos los binds `:name` que un SQL referencia, con las MISMAS reglas de lectura que
/// [`required_binds`] (`::` no es bind, literales y comentarios verbatim) — pero sin la distinción
/// COALESCE, que aquí no aplica: un bind opcional que el módulo guardó él mismo sigue siendo un
/// bind que su SQL declara, y por lo tanto vocabulario.
fn all_binds(sql: &str) -> Vec<String> {
    let bytes = sql.as_bytes();
    let mut out: Vec<String> = Vec::new();
    for (start, end) in code_spans(bytes) {
        let seg = &sql[start..end];
        let b = seg.as_bytes();
        let mut i = 0usize;
        while i < seg.len() {
            if b[i] == b':' {
                if b.get(i + 1) == Some(&b':') {
                    i += 2;
                    continue;
                }
                let mut j = i + 1;
                while j < seg.len() && (b[j].is_ascii_alphanumeric() || b[j] == b'_') {
                    j += 1;
                }
                if j > i + 1 {
                    let name = &seg[i + 1..j];
                    if !out.iter().any(|n| n == name) {
                        out.push(name.to_string());
                    }
                    i = j;
                    continue;
                }
            }
            i += 1;
        }
    }
    out
}

/// Compone y ejecuta el SQL paginado a partir del SELECT base y el `ListSpec`.
/// `pub(crate)`: el core lo reutiliza para `hub.approvals.list` (hub#884) — mismo motor, mismo
/// contrato, sin un segundo paginador.
pub(crate) async fn run_list(
    db: &dyn DatabaseAdapter,
    query: &str,
    base_sql: &str,
    spec: &ListSpec,
    bound: &Params,
) -> Result<QueryPage> {
    // ── binds obligatorios (hub#1086) ─────────────────────────────────────────────────────
    // Un bind que el SQL base referencia FUERA de un `COALESCE(:p, …)` no puede ser opcional:
    // ligarlo como NULL convierte `col = :param` en un filtro que no casa nada y la página
    // responde total: 0 CON CREDIBILIDAD — el caso real fue un arqueo de caja asegurando que no
    // había movimientos con los movimientos escritos (`cart_checkout.items.list`,
    // `cash_register.movements.list`, QA 21/08/2026). La distinción está en el propio SQL:
    // lo que el módulo envolvió en COALESCE es un default DECLARADO (el idioma
    // `include_archived` de `services.services.list`, services#44) y sigue siendo opcional;
    // lo demás se exige presente y no-null, con un error que nombra el parámetro.
    for name in required_binds(base_sql) {
        if !bound.get(&name).is_some_and(|v| !v.is_null()) {
            return Err(RuntimeError::MissingRequiredParam {
                query: query.to_string(),
                param: name,
            });
        }
    }

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


// ── binds obligatorios de un SQL de lista (hub#1086) ─────────────────────────────────────

/// Vocabulario del PROPIO motor de listas: `limit`/`offset` (paginación), `search` (buscador
/// global), `sort`/`dir` (orden) y `f_*` (filtros por columna del bloque `list`). Un filtro
/// ausente significa «sin condición» — es opcional POR DISEÑO, nunca un bind obligatorio.
fn is_engine_bind(name: &str) -> bool {
    name.starts_with("f_") || matches!(name, "limit" | "offset" | "search" | "sort" | "dir")
}

/// Binds que el SQL base referencia de forma NO tolerante a NULL (hub#1086).
///
/// «No tolerante» = el bind aparece AL MENOS UNA VEZ fuera del primer argumento de un
/// `COALESCE(<…bind…>, default)`. La regla es textual a propósito: es el módulo quien ESCRIBIÓ
/// su manejo del NULL en el SQL, y ese es hoy el único idioma de bind opcional que existe en
/// los manifests publicados (verificado contra los 25 módulos, 22/08/2026: el único bind
/// opcional en un SQL de lista es el `include_archived` de `services.services.list`, envuelto
/// en COALESCE). Un bind COALESCE-guardado ausente llega como NULL a propósito — default
/// declarado, no accidente.
///
/// El escaneo replica las reglas de `translate` (nombres `:name`, `::` cast nunca es bind,
/// strings `'…'` y comentarios `--`/`/* */` verbatim), porque la guarda tiene que ver EXACTAMENTE
/// los nombres que el traductor bajará a `$n`.
pub(crate) fn required_binds(sql: &str) -> Vec<String> {
    let bytes = sql.as_bytes();
    let code = code_spans(bytes);
    let coalesced = coalesce_first_arg_spans(bytes, &code);

    let mut required: Vec<String> = Vec::new();
    for (start, end) in &code {
        let seg = &sql[*start..*end];
        let mut i = 0usize;
        while i < seg.len() {
            // `::` es el cast de Postgres, no un parámetro.
            if seg.as_bytes()[i] == b':' {
                if seg.as_bytes().get(i + 1) == Some(&b':') {
                    i += 2;
                    continue;
                }
                let mut j = i + 1;
                while j < seg.len()
                    && (seg.as_bytes()[j].is_ascii_alphanumeric() || seg.as_bytes()[j] == b'_')
                {
                    j += 1;
                }
                if j > i + 1 {
                    let name = &seg[i + 1..j];
                    let abs = start + i + 1; // posición del nombre (byte absoluto)
                    let in_coalesce = coalesced.iter().any(|(s, e)| abs >= *s && abs < *e);
                    if !in_coalesce && !required.iter().any(|n| n == name) {
                        required.push(name.to_string());
                    }
                    i = j;
                    continue;
                }
            }
            i += 1;
        }
    }
    // Un bind entra en `required` por su PRIMERA aparición fuera de COALESCE, y ya no sale:
    // si aparece además dentro de un COALESCE, su aparición desprotegida manda (ligarla como
    // NULL mintió igual). El bind cuyas apariciones están TODAS protegidas nunca entró.
    required.retain(|name| !is_engine_bind(name));
    required
}

/// Tramos de `bytes` que son CÓDIGO: fuera de literales `'…'` y de comentarios `-- …` / `/* … */`.
/// Mismas reglas que `translate`/`shim_functions` en erplora-db (hub#1026): un apóstrofe en
/// prosa no abre un literal fantasma.
fn code_spans(bytes: &[u8]) -> Vec<(usize, usize)> {
    let mut spans: Vec<(usize, usize)> = Vec::new();
    let mut i = 0usize;
    let mut start = 0usize;
    let mut in_string = false;
    while i < bytes.len() {
        let c = bytes[i];
        if in_string {
            if c == b'\'' {
                in_string = false;
                i += 1;
                start = i; // el tramo de código siguiente empieza TRAS el literal
            } else {
                i += 1;
            }
            continue;
        }
        match c {
            b'\'' => {
                spans.push((start, i));
                in_string = true;
                i += 1;
            }
            b'-' if bytes.get(i + 1) == Some(&b'-') => {
                spans.push((start, i));
                let mut j = i;
                while j < bytes.len() && bytes[j] != b'\n' {
                    j += 1;
                }
                i = j;
                start = j; // el salto de línea es código (blanco)
            }
            b'/' if bytes.get(i + 1) == Some(&b'*') => {
                spans.push((start, i));
                let mut j = i + 2;
                while j < bytes.len() && !(bytes[j] == b'*' && bytes.get(j + 1) == Some(&b'/')) {
                    j += 1;
                }
                i = (j + 2).min(bytes.len());
                start = i;
            }
            _ => {
                i += 1;
            }
        }
    }
    spans.push((start, bytes.len()));
    spans.retain(|(a, b)| a < b);
    spans
}

/// Tramos (en bytes absolutos) del PRIMER argumento de cada llamada `COALESCE(…)`: desde tras
/// el `(` hasta la coma a profundidad 1 o el `)` de cierre, contando strings para que una coma
/// dentro de un literal no corte el argumento. Case-insensitive y con frontera de palabra.
fn coalesce_first_arg_spans(bytes: &[u8], code: &[(usize, usize)]) -> Vec<(usize, usize)> {
    let needle = b"COALESCE";
    let mut spans = Vec::new();
    for (start, end) in code {
        let seg = &bytes[*start..*end];
        let mut i = 0usize;
        while i < seg.len() {
            if seg[i..].len() >= needle.len()
                && seg[i..i + needle.len()].eq_ignore_ascii_case(needle)
            {
                let prev_ident = i > 0
                    && (seg[i - 1].is_ascii_alphanumeric() || seg[i - 1] == b'_');
                let after = i + needle.len();
                let next_ident = seg
                    .get(after)
                    .is_some_and(|b| b.is_ascii_alphanumeric() || *b == b'_');
                if !prev_ident && !next_ident {
                    // saltar espacios hasta el `(` ; si no viene, no es una llamada.
                    let mut j = after;
                    while j < seg.len() && (seg[j] as char).is_whitespace() {
                        j += 1;
                    }
                    if seg.get(j) == Some(&b'(') {
                        let open = j;
                        let mut depth = 0usize;
                        let mut k = open;
                        let mut in_str = false;
                        while k < seg.len() {
                            let c = seg[k];
                            if in_str {
                                if c == b'\'' {
                                    in_str = false;
                                }
                                k += 1;
                                continue;
                            }
                            match c {
                                b'\'' => in_str = true,
                                b'(' => depth += 1,
                                b')' => {
                                    depth -= 1;
                                    if depth == 0 {
                                        break;
                                    }
                                }
                                b',' if depth == 1 => break,
                                _ => {}
                            }
                            k += 1;
                        }
                        let end_rel = (k + 1).min(seg.len()); // incluye la coma/paréntesis de corte
                        spans.push((start + open + 1, start + end_rel));
                        i = end_rel;
                        continue;
                    }
                }
            }
            i += 1;
        }
    }
    spans
}
/// ¿Es un identificador SQL seguro (`[A-Za-z_][A-Za-z0-9_]*`)? Solo estos se interpolan en el
/// SQL (columnas de `sort`/`filters` vienen del manifest de confianza; esto es defensa en
/// profundidad frente a un manifest malformado).
fn is_ident(s: &str) -> bool {
    let mut chars = s.chars();
    matches!(chars.next(), Some(c) if c.is_ascii_alphabetic() || c == '_')
        && s.chars().all(|c| c.is_ascii_alphanumeric() || c == '_')
}

#[cfg(test)]
mod tests {
    use super::{code_spans, coalesce_first_arg_spans, required_binds};

    // ── hub#1086: el escáner de binds obligatorios ───────────────────────────────────────────
    // La regla: un bind es obligatorio iff aparece AL MENOS UNA VEZ fuera del primer argumento
    // de un COALESCE. Es la distinción que el issue pide: filtro ausente = no filtrar (legítimo,
    // vocabulario del motor) VERSUS contexto ausente = página que miente (requerido).

    #[test]
    fn bare_bind_is_required() {
        let sql = "SELECT * FROM t WHERE hub_id = :hub_id AND cart_id = :cart_id";
        // `hub_id` también sale: el escáner refleja lo que el SQL EXIGE; que el runtime lo
        // inyecte siempre es cosa de la guarda (lo verá presente y pasará).
        assert_eq!(required_binds(sql), vec!["hub_id", "cart_id"]);
    }

    #[test]
    fn coalesce_wrapped_bind_is_optional() {
        // El idioma de services.services.list (services#44): ausente = NULL = alcance default.
        let sql = "SELECT * FROM c WHERE hub_id = :hub_id \
                   AND (COALESCE(CAST(:include_archived AS TEXT), '0') IN ('1', 'true') \
                        OR c.archived = 0)";
        assert_eq!(
            required_binds(sql),
            vec!["hub_id"],
            "include_archived queda OPCIONAL por el COALESCE; hub_id es del sistema"
        );
    }

    #[test]
    fn bind_in_both_places_is_required() {
        // El idioma de appointments.list (simple, no list): el sentinel `(COALESCE(:p,'')='' OR
        // col = :p)`. La SEGUNDA aparición no está protegida — para el motor de listas manda
        // como requerido: es la lectura conservadora de un bind medio protegido.
        let sql = "SELECT * FROM t WHERE (COALESCE(CAST(:status AS text), '') = '' OR status = :status)";
        assert_eq!(required_binds(sql), vec!["status"]);
    }

    #[test]
    fn engine_vocabulary_is_never_required() {
        let sql = "SELECT * FROM t WHERE name LIKE '%' || :search || '%' \
                   ORDER BY :sort LIMIT :limit OFFSET :offset AND name = :f_name";
        assert!(
            required_binds(sql).is_empty(),
            "limit/offset/search/sort/f_* son vocabulario del motor: opcionales por diseño"
        );
    }

    #[test]
    fn strings_comments_and_casts_are_not_binds() {
        let sql = "-- el :cart_id de la prosa no cuenta\n\
                   SELECT ':cart_id' AS lit, t.id::int FROM t /* :ghost */ WHERE 1 = 1";
        assert!(required_binds(sql).is_empty());
    }

    #[test]
    fn repeated_bind_is_listed_once() {
        let sql = "SELECT * FROM t WHERE a = :x OR b = :x";
        assert_eq!(required_binds(sql), vec!["x"]);
    }
}
