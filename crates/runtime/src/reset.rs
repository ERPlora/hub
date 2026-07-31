//! Reset del hub — volver el hub a cero (ADR-0170).
//!
//! **Espejo del export**: reutiliza su mismo inventario de tablas (`list_tables`, `table_owner`
//! por prefijo más largo, `foreign_keys` del catálogo) recorrido al revés. Así lo que el hub sabe
//! exportar es exactamente lo que sabe borrar, y un módulo nuevo no hay que darlo de alta en dos
//! sitios.
//!
//! Reglas duras (fijadas por los e2e `tests/reset_test.rs`):
//!   - `DELETE ... WHERE hub_id = :hub_id` SIEMPRE. Nunca `TRUNCATE`, nunca `DROP`: la BD es
//!     **compartida por organización** (`tenancy.md`) y un reset mal acotado se llevaría los hubs
//!     hermanos.
//!   - **Borrado duro**, no `is_deleted=1`: el soft-delete masivo rompería los índices únicos
//!     `(hub_id, …)` al reimportar.
//!   - **Una sola transacción** (`execute_tx`): al revés que el import, que es best-effort a
//!     propósito, un reset a medias no deja ni seguir ni volver.
//!   - **Las filas propiedad del módulo sobreviven** (mismo criterio que `is_module_seeded` del
//!     export, aquí como predicado SQL): las siembra el módulo al instalarse y no las re-siembra.
//!   - **Nadie se auto-expulsa**: el usuario que ejecuta el reset nunca se borra.

use serde::{Deserialize, Serialize};

use crate::export::{foreign_keys, has_column, list_tables, safe_ident, table_owner};
use crate::Runtime;

/// Qué secciones se borran. Todo `false`/vacío por defecto: el reset nunca hace de más.
#[derive(Debug, Clone, Default)]
pub struct ResetSelection {
    /// Settings del hub (`hub_settings`).
    pub settings: bool,
    /// Empleados (`hub_user`) — MENOS quien ejecuta el reset.
    pub users: bool,
    /// Ficheros del gestor media. El runtime solo lo registra; los bytes los borra el server.
    pub media: bool,
    /// Configuración fiscal + certificado. Bloqueada si hay facturas remitidas a la AEAT.
    pub fiscal: bool,
    /// Ids de módulos instalados cuyos datos de usuario se borran.
    pub modules: Vec<String>,
}

/// Una sección en el **dry-run**: cuántas filas se llevaría y si algo la bloquea.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct SectionPlan {
    /// `hub_settings` · `hub_users` · `media` · `fiscal` · `modules/<id>`.
    pub section: String,
    /// Filas reales que se borrarían (la UI pinta cifras, no adjetivos).
    pub rows: i64,
    /// Motivo legible por el que la sección NO se puede borrar (p. ej. facturas remitidas a la
    /// AEAT). `Some` ⇒ la UI la deshabilita y el server la rechaza aunque el cliente insista.
    pub blocked_by: Option<String>,
}

/// Dry-run completo: lo que el panel de «Restablecer» pinta antes de que nadie confirme.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq, Default)]
pub struct ResetPlan {
    pub sections: Vec<SectionPlan>,
}

/// Lo que el reset hizo en una sección.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct SectionOutcome {
    pub section: String,
    pub rows_deleted: i64,
}

/// Informe final del reset (contrato JSON que la UI pinta tal cual).
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq, Default)]
pub struct ResetReport {
    pub sections: Vec<SectionOutcome>,
}

/// **Dry-run**: inventaría las secciones del hub con el número de filas que se borrarían y los
/// bloqueos aplicables. No escribe nada — se ejecuta con solo abrir el panel.
pub async fn plan_reset(rt: &Runtime, hub_id: &str) -> crate::Result<ResetPlan> {
    let db = rt.db();
    let mut sections = Vec::new();

    sections.push(SectionPlan {
        section: "hub_settings".into(),
        rows: count_where(rt, "hub_settings", "TRUE", hub_id).await,
        blocked_by: None,
    });
    // `hub_user` NO lleva `hub_id` (identidad por despliegue, `identity.rs`): se cuenta entera.
    sections.push(SectionPlan {
        section: "hub_users".into(),
        rows: count_raw(rt, "SELECT count(*) AS n FROM hub_user", hub_id).await,
        blocked_by: None,
    });

    // Límite fiscal: se calcula UNA vez y se aplica a todas las secciones que lo sostienen.
    let remitted = remitted_invoices(rt, hub_id).await;

    for module_id in module_ids(rt) {
        let mut rows = 0;
        for table in module_tables(rt, db, &module_id).await {
            rows += count_raw(rt, &table.count_sql(), hub_id).await;
        }
        sections.push(SectionPlan {
            section: format!("modules/{module_id}"),
            rows,
            blocked_by: fiscal_block(&module_id, remitted),
        });
    }
    Ok(ResetPlan { sections })
}

// ── Límite fiscal (RD 1007/2023) ────────────────────────────────────────────────────────

/// Módulos cuyos datos **sostienen** los registros de facturación remitidos: borrarlos dejaría
/// la cadena VeriFactu apuntando a facturas que ya no existen.
const FISCAL_SECTIONS: [&str; 3] = ["verifactu", "invoice", "sales"];

/// Facturas del hub **ya remitidas a la AEAT**: `status` transmitido/aceptado o con CSV de la
/// AEAT. Son **inalterables** (RD 1007/2023). 0 si el módulo `verifactu` no está instalado (la
/// consulta falla y `count_raw` devuelve 0), que es justo el caso «hub sin fiscal».
///
/// El criterio es EXACTO, no heurístico: los datos de demo se quedan en `pending` y sin CSV, así
/// que el caso que motiva el ADR-0170 —probar la demo y borrarla— nunca se bloquea.
async fn remitted_invoices(rt: &Runtime, hub_id: &str) -> i64 {
    count_raw(
        rt,
        "SELECT count(*) AS n FROM verifactu_record WHERE hub_id = :hub_id \
         AND (status IN ('transmitted', 'accepted') OR aeat_csv <> '')",
        hub_id,
    )
    .await
}

/// Motivo del bloqueo de una sección, o `None` si no aplica. El texto lleva la CIFRA y nombra a
/// la AEAT: un bloqueo sin explicación se lee como un fallo del producto, no como la ley.
fn fiscal_block(module_id: &str, remitted: i64) -> Option<String> {
    (remitted > 0 && FISCAL_SECTIONS.contains(&module_id)).then(|| {
        format!(
            "{remitted} facturas remitidas a la AEAT: inalterables por RD 1007/2023, \
             no se pueden borrar"
        )
    })
}

/// Borra las secciones seleccionadas del hub `hub_id`, en una sola transacción y en orden
/// topológico inverso de FK. `actor_user_id` nunca se borra (no te puedes auto-expulsar).
pub async fn execute_reset(
    rt: &Runtime,
    hub_id: &str,
    selection: &ResetSelection,
    actor_user_id: &str,
) -> crate::Result<ResetReport> {
    let db = rt.db();

    // ── Límite fiscal ANTES de tocar nada (el cliente puede venir manipulado) ────────────
    // La UI ya pinta estas secciones deshabilitadas, pero la autoridad es el servidor: un
    // `fetch` a mano no puede saltarse el RD 1007/2023.
    let remitted = remitted_invoices(rt, hub_id).await;
    if remitted > 0 {
        let bloqueada = selection
            .modules
            .iter()
            .find(|m| FISCAL_SECTIONS.contains(&m.as_str()))
            .map(|m| format!("modules/{m}"))
            .or_else(|| selection.fiscal.then(|| "fiscal".to_string()));
        if let Some(section) = bloqueada {
            return Err(crate::RuntimeError::Other(format!(
                "reset: la sección {section} está bloqueada — {}. No se ha borrado nada.",
                fiscal_block("verifactu", remitted).unwrap_or_default()
            )));
        }
    }

    // (sección, tabla, sentencia) — se acumulan TODAS y se aplican en UNA transacción.
    let mut ops: Vec<(String, String, String)> = Vec::new();

    // Solo se emiten sentencias sobre tablas que EXISTEN: una tabla ausente es un no-op, no un
    // motivo para tumbar el reset entero (la transacción es all-or-nothing y un `DELETE` sobre
    // una tabla inexistente abortaría también las secciones que sí se podían borrar).
    let existing = list_tables(db).await.unwrap_or_default();

    if selection.settings && existing.iter().any(|t| t == "hub_settings") {
        ops.push((
            "hub_settings".into(),
            "hub_settings".into(),
            "DELETE FROM hub_settings WHERE hub_id = :hub_id".into(),
        ));
    }
    if selection.users && existing.iter().any(|t| t == "hub_user") {
        // Nunca al actor: un owner no puede quedarse fuera de su propio hub con un clic.
        // `hub_user` no lleva `hub_id` (identidad por despliegue), así que NO se acota por él.
        ops.push((
            "hub_users".into(),
            "hub_user".into(),
            "DELETE FROM hub_user WHERE id <> :actor".into(),
        ));
    }

    for module_id in &selection.modules {
        if !rt.registry().is_installed(module_id) {
            continue; // no instalado → no hay tablas suyas que barrer
        }
        let section = format!("modules/{module_id}");
        for table in module_tables(rt, db, module_id).await {
            ops.push((section.clone(), table.name.clone(), table.delete_sql()));
        }
    }
    if ops.is_empty() {
        return Ok(ResetReport::default());
    }

    // Informe POR SECCIÓN: se cuenta con el MISMO `WHERE` antes de borrar (después ya no hay
    // filas que contar, y `execute_tx` solo devuelve el total agregado).
    let mut planned: Vec<(String, i64)> = Vec::new();
    for (section, _, sql) in &ops {
        let n = count_raw(rt, &count_of(sql), hub_id).await;
        match planned.iter_mut().find(|(s, _)| s == section) {
            Some((_, acc)) => *acc += n,
            None => planned.push((section.clone(), n)),
        }
    }

    // Orden topológico INVERSO de FK: una tabla se borra ANTES que las que referencia, o el
    // DELETE choca contra la constraint (`inventory_product_categories` → `inventory_product`).
    let order = delete_order(db, ops.iter().map(|(_, t, _)| t.clone()).collect()).await;
    ops.sort_by_key(|(_, t, _)| order.iter().position(|o| o == t).unwrap_or(usize::MAX));

    let mut p = hub_params(hub_id);
    p.insert("actor".into(), serde_json::json!(actor_user_id));
    let tx: Vec<(String, erplora_db::Params)> =
        ops.iter().map(|(_, _, sql)| (sql.clone(), p.clone())).collect();
    db.execute_tx(&tx).await.map_err(|e| {
        crate::RuntimeError::Other(format!("reset: la transacción falló, nada se borró: {e}"))
    })?;

    Ok(ResetReport {
        sections: planned
            .into_iter()
            .map(|(section, rows_deleted)| SectionOutcome { section, rows_deleted })
            .collect(),
    })
}

// ── Inventario (espejo del export) ──────────────────────────────────────────────────────

/// Una tabla del hub a barrer, con el `WHERE` que la acota al tenant y a los datos de USUARIO.
struct ResetTable {
    name: String,
    /// Predicado que deja fuera las filas propiedad del módulo (`is_module_seeded` en SQL).
    user_rows: String,
    /// Acotación al tenant: por `hub_id` propio, o por el padre a través de la FK declarada.
    scope: String,
}

impl ResetTable {
    fn delete_sql(&self) -> String {
        format!("DELETE FROM {} WHERE {} AND {}", self.name, self.scope, self.user_rows)
    }
    fn count_sql(&self) -> String {
        format!("SELECT count(*) AS n FROM {} WHERE {} AND {}", self.name, self.scope, self.user_rows)
    }
}

fn module_ids(rt: &Runtime) -> Vec<String> {
    rt.registry().installed.iter().map(|m| m.id.clone()).collect()
}

/// Tablas propiedad de `module_id` (prefijo más largo, igual que el export), cada una con su
/// acotación de tenant y su predicado de datos de usuario ya resueltos contra el catálogo.
async fn module_tables(
    rt: &Runtime,
    db: &dyn erplora_db::DatabaseAdapter,
    module_id: &str,
) -> Vec<ResetTable> {
    let installed = module_ids(rt);
    let all = list_tables(db).await.unwrap_or_default();
    let mut out = Vec::new();
    for name in all {
        if table_owner(&name, &installed).as_deref() != Some(module_id) || !safe_ident(&name) {
            continue;
        }
        let user_rows = user_rows_predicate(db, &name, "").await;
        let scope = match tenant_scope(db, &name).await {
            Some(s) => s,
            // Sin `hub_id` y sin FK a un padre que lo tenga no hay forma de acotar el tenant:
            // NO se toca (borrarla entera se llevaría filas de otros hubs de la org).
            None => continue,
        };
        out.push(ResetTable { name, user_rows, scope });
    }
    out
}

/// Acotación al tenant de una tabla: su propio `hub_id`, o —en los vínculos M2M que no lo
/// llevan— la pertenencia de su PADRE a través de la FK DECLARADA (no se adivinan nombres).
/// Réplica del criterio de `fetch_join_rows` del export.
async fn tenant_scope(db: &dyn erplora_db::DatabaseAdapter, table: &str) -> Option<String> {
    if has_column(db, table, "hub_id").await {
        return Some("hub_id = :hub_id".into());
    }
    for fk in foreign_keys(db, table).await {
        if fk.parent == table || !has_column(db, &fk.parent, "hub_id").await {
            continue; // self-FK o padre sin tenant: no sirve para acotar
        }
        // Solo los vínculos cuyo PADRE se va a borrar: si el padre sobrevive (fila del módulo),
        // su vínculo tampoco puede desaparecer.
        let parent_user_rows = user_rows_predicate(db, &fk.parent, "p.").await;
        let (parent, to, from) = (&fk.parent, &fk.to, &fk.from);
        return Some(format!(
            "EXISTS (SELECT 1 FROM {parent} p WHERE p.{to} = {table}.{from} \
             AND p.hub_id = :hub_id AND {parent_user_rows})"
        ));
    }
    None
}

/// `is_module_seeded` como predicado SQL: deja fuera las filas que siembra el MÓDULO al
/// instalarse (`is_system=1` · `source='shipped'` · `created_by='system'`) y que no vuelve a
/// sembrar. Solo se añade la condición de las columnas que la tabla realmente tiene. `prefix`
/// cualifica las columnas cuando el predicado va dentro de un subquery (`p.`).
async fn user_rows_predicate(
    db: &dyn erplora_db::DatabaseAdapter,
    table: &str,
    prefix: &str,
) -> String {
    let mut conds: Vec<String> = Vec::new();
    if has_column(db, table, "is_system").await {
        conds.push(format!("({prefix}is_system IS NULL OR {prefix}is_system = 0)"));
    }
    if has_column(db, table, "source").await {
        conds.push(format!("({prefix}source IS NULL OR {prefix}source <> 'shipped')"));
    }
    if has_column(db, table, "created_by").await {
        conds.push(format!("({prefix}created_by IS NULL OR {prefix}created_by <> 'system')"));
    }
    if conds.is_empty() {
        "TRUE".into()
    } else {
        conds.join(" AND ")
    }
}

// ── Orden de borrado ────────────────────────────────────────────────────────────────────

/// Orden topológico INVERSO de FK: una tabla va ANTES que todas las que referencia. Kahn sobre
/// el grafo «A referencia a B» ⇒ A se borra antes que B. Las self-FK se ignoran (una tabla no
/// se bloquea a sí misma) y un ciclo residual se emite tal cual: el DELETE fallaría y la
/// transacción revertiría entera, que es la semántica deseada (nunca a medias).
async fn delete_order(db: &dyn erplora_db::DatabaseAdapter, tables: Vec<String>) -> Vec<String> {
    let mut uniq: Vec<String> = Vec::new();
    for t in tables {
        if !uniq.contains(&t) {
            uniq.push(t);
        }
    }
    let mut edges: Vec<(String, String)> = Vec::new(); // (A referencia a B) ⇒ A antes que B
    for t in &uniq {
        for fk in foreign_keys(db, t).await {
            if fk.parent != *t && uniq.contains(&fk.parent) {
                edges.push((t.clone(), fk.parent.clone()));
            }
        }
    }
    // blockers[B] = cuántas tablas del conjunto referencian a B (deben borrarse antes).
    let mut blockers: Vec<(String, usize)> = uniq
        .iter()
        .map(|t| (t.clone(), edges.iter().filter(|(_, b)| b == t).count()))
        .collect();

    let mut out: Vec<String> = Vec::new();
    while let Some(idx) = blockers.iter().position(|(_, n)| *n == 0) {
        let (t, _) = blockers.remove(idx);
        for (_, b) in edges.iter().filter(|(a, _)| *a == t) {
            if let Some(e) = blockers.iter_mut().find(|(name, _)| name == b) {
                e.1 = e.1.saturating_sub(1);
            }
        }
        out.push(t);
    }
    // Restos (ciclo): en cualquier orden — la transacción es all-or-nothing.
    out.extend(blockers.into_iter().map(|(t, _)| t));
    out
}

// ── Utilidades ──────────────────────────────────────────────────────────────────────────

fn hub_params(hub_id: &str) -> erplora_db::Params {
    let mut p = erplora_db::Params::new();
    p.insert("hub_id".into(), serde_json::json!(hub_id));
    p
}

/// `SELECT count(*)` equivalente a un `DELETE FROM … WHERE …` construido aquí: es lo que el
/// informe muestra por sección (contado ANTES de borrar).
fn count_of(delete_sql: &str) -> String {
    match delete_sql.strip_prefix("DELETE FROM ") {
        Some(rest) => format!("SELECT count(*) AS n FROM {rest}"),
        None => "SELECT 0 AS n".into(),
    }
}

/// Ejecuta un `count(*)` ya construido; 0 si la tabla no existe o el SQL falla.
async fn count_raw(rt: &Runtime, sql: &str, hub_id: &str) -> i64 {
    let mut p = hub_params(hub_id);
    // El `:actor` solo aparece en el conteo de `hub_user`; sobra inofensivamente en el resto.
    p.insert("actor".into(), serde_json::json!(""));
    rt.db()
        .query(sql, &p)
        .await
        .ok()
        .and_then(|r| r.rows.first().and_then(|row| row["n"].as_i64()))
        .unwrap_or(0)
}

/// `count(*)` de `table` acotado al tenant y a un predicado extra (0 si no se puede acotar).
async fn count_where(rt: &Runtime, table: &str, extra: &str, hub_id: &str) -> i64 {
    if !safe_ident(table) {
        return 0;
    }
    let Some(scope) = tenant_scope(rt.db(), table).await else { return 0 };
    count_raw(rt, &format!("SELECT count(*) AS n FROM {table} WHERE {scope} AND {extra}"), hub_id).await
}

#[cfg(test)]
mod tests {
    use super::*;

    /// El plan y el informe son el contrato JSON que la UI pinta: round-trip sin perder campos.
    #[test]
    fn plan_and_report_serde_round_trip() {
        let plan = ResetPlan {
            sections: vec![SectionPlan {
                section: "modules/inventory".into(),
                rows: 124,
                blocked_by: Some("12 facturas remitidas a la AEAT".into()),
            }],
        };
        let back: ResetPlan = serde_json::from_str(&serde_json::to_string(&plan).unwrap()).unwrap();
        assert_eq!(plan, back);

        let report = ResetReport {
            sections: vec![SectionOutcome { section: "hub_settings".into(), rows_deleted: 7 }],
        };
        let back: ResetReport =
            serde_json::from_str(&serde_json::to_string(&report).unwrap()).unwrap();
        assert_eq!(report, back);
    }

    /// El conteo del informe se deriva del MISMO `WHERE` del DELETE: si divergieran, la UI
    /// mostraría una cifra que no es la que se borra.
    #[test]
    fn count_of_mirrors_the_delete_predicate() {
        assert_eq!(
            count_of("DELETE FROM inventory_product WHERE hub_id = :hub_id AND TRUE"),
            "SELECT count(*) AS n FROM inventory_product WHERE hub_id = :hub_id AND TRUE"
        );
        assert_eq!(count_of("no es un delete"), "SELECT 0 AS n");
    }

    /// Una selección vacía no genera ni una sentencia: el reset nunca hace de más.
    #[test]
    fn default_selection_is_empty() {
        let sel = ResetSelection::default();
        assert!(!sel.settings && !sel.users && !sel.media && !sel.fiscal);
        assert!(sel.modules.is_empty());
    }
}

// ── Deshacer una importación (ADR-0170 Fase 3) ──────────────────────────────────────────
//
// El camino que motiva el ADR: importo la demo → la miro → la quito limpiamente → cargo lo mío.
// El reset por secciones no sirve aquí, porque para entonces el usuario ya ha creado cosas suyas
// y borrar «el módulo entero» se las llevaría por delante.
//
// La clave es `RETURNING id`: los INSERT del bundle llevan guard `WHERE NOT EXISTS`, así que
// devuelven fila SOLO cuando de verdad insertan. Re-importar el mismo blueprint no apunta nada,
// y por tanto deshacer ese segundo lote no puede borrar lo que trajo el primero.

/// Un lote de importación: lo que trajo un blueprint concreto, para poder deshacerlo.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct ImportBatch {
    pub id: String,
    /// Nombre del blueprint importado (`restaurante_es`), para que el usuario lo reconozca.
    pub name: String,
    /// Filas que ESTE lote insertó realmente.
    pub rows: i64,
    pub created_at: String,
}

const ENSURE_BATCH_TABLES: &str = "\
CREATE TABLE IF NOT EXISTS _hub_import_batch (\
 id TEXT PRIMARY KEY, hub_id TEXT NOT NULL, name TEXT NOT NULL, created_at TEXT NOT NULL);\
CREATE TABLE IF NOT EXISTS _hub_import_row (\
 batch_id TEXT NOT NULL, table_name TEXT NOT NULL, row_id TEXT NOT NULL);";

/// Crea las tablas de trazabilidad de lotes si faltan (idempotente).
async fn ensure_batch_tables(db: &dyn erplora_db::DatabaseAdapter) -> crate::Result<()> {
    db.execute_batch(ENSURE_BATCH_TABLES)
        .await
        .map_err(|e| crate::RuntimeError::Other(format!("reset: tablas de lote de import: {e}")))
}

/// Aplica el SQL de un blueprint REGISTRANDO qué filas inserta, y devuelve el `batch_id`.
///
/// Sustituye el placeholder de tenant por el `hub_id` destino (patrón ADR-0072) igual que el
/// import, y añade `RETURNING id` a cada sentencia para apuntar solo lo realmente insertado.
/// Las tablas sin columna `id` (vínculos M2M) no se registran: se van con su padre.
pub async fn apply_tracked(
    rt: &Runtime,
    hub_id: &str,
    name: &str,
    sql: &str,
    scope: &crate::import_sql::TableScope,
) -> crate::Result<String> {
    let batch_id = begin_batch(rt, hub_id, name).await?;
    apply_tracked_into(rt, &batch_id, hub_id, sql, scope).await?;
    Ok(batch_id)
}

/// Abre un lote de importación vacío y devuelve su id. Lo llama `import_sections` UNA vez por
/// importación, para que todas sus secciones queden bajo el mismo lote deshacible.
pub async fn begin_batch(rt: &Runtime, hub_id: &str, name: &str) -> crate::Result<String> {
    let db = rt.db();
    ensure_batch_tables(db).await?;
    let batch_id = crate::registry::new_id();
    let mut p = erplora_db::Params::new();
    p.insert("id".into(), serde_json::json!(batch_id));
    p.insert("hub_id".into(), serde_json::json!(hub_id));
    p.insert("name".into(), serde_json::json!(name));
    p.insert("now".into(), serde_json::json!(crate::registry::now_rfc3339()));
    db.execute(
        "INSERT INTO _hub_import_batch (id, hub_id, name, created_at) \
         VALUES (:id, :hub_id, :name, :now)",
        &p,
    )
    .await
    .map_err(|e| crate::RuntimeError::Other(format!("reset: registrar el lote: {e}")))?;
    Ok(batch_id)
}

/// Aplica el SQL de una sección DENTRO de un lote ya abierto, registrando las filas insertadas.
///
/// **Valida con el mismo `import_sql::validate` que el import** (subconjunto SQL confinado al
/// scope de la sección, hub#239): el trazado de lotes no puede ser una puerta trasera que
/// ejecute SQL que el import rechazaría.
pub async fn apply_tracked_into(
    rt: &Runtime,
    batch_id: &str,
    hub_id: &str,
    sql: &str,
    scope: &crate::import_sql::TableScope,
) -> crate::Result<usize> {
    let db = rt.db();
    ensure_batch_tables(db).await?;
    let stmts = crate::import_sql::validate(sql, scope).map_err(crate::RuntimeError::Other)?;
    let mut applied = 0usize;

    for stmt in stmts {
        let stmt = stmt.replace(crate::export::HUB_ID_PLACEHOLDER, hub_id);
        let table = insert_target(&stmt);
        let Some(table) = table else {
            // No es un INSERT reconocible: se aplica tal cual, sin registrar.
            db.execute_batch(&stmt).await.map_err(|e| {
                crate::RuntimeError::Other(format!("reset: aplicar sentencia del blueprint: {e}"))
            })?;
            continue;
        };
        // `RETURNING id` sobre el `;` final. Solo devuelve filas si el guard NOT EXISTS pasó.
        let returning = format!("{} RETURNING id", stmt.trim_end().trim_end_matches(';'));
        let res = match db.query(&returning, &erplora_db::Params::new()).await {
            Ok(r) => r,
            // Tabla sin `id` (vínculo M2M) u otra forma no soportada: se aplica sin registrar.
            Err(_) => {
                db.execute_batch(&stmt).await.map_err(|e| {
                    crate::RuntimeError::Other(format!("reset: aplicar sentencia: {e}"))
                })?;
                continue;
            }
        };
        for row in &res.rows {
            let Some(row_id) = row.get("id").and_then(|v| v.as_str()) else { continue };
            let mut rp = erplora_db::Params::new();
            rp.insert("batch_id".into(), serde_json::json!(batch_id));
            rp.insert("table_name".into(), serde_json::json!(table));
            rp.insert("row_id".into(), serde_json::json!(row_id));
            db.execute(
                "INSERT INTO _hub_import_row (batch_id, table_name, row_id) \
                 VALUES (:batch_id, :table_name, :row_id)",
                &rp,
            )
            .await
            .map_err(|e| crate::RuntimeError::Other(format!("reset: registrar fila del lote: {e}")))?;
        }
        applied += 1;
    }
    Ok(applied)
}

/// Tabla destino de un `INSERT INTO <tabla> …`, o `None` si la sentencia no lo es.
fn insert_target(stmt: &str) -> Option<String> {
    let rest = stmt.trim_start().strip_prefix("INSERT INTO ")?;
    let table = rest.split_whitespace().next()?.split('(').next()?;
    safe_ident(table).then(|| table.to_string())
}

/// Lotes de importación del hub, del más reciente al más antiguo.
pub async fn list_import_batches(rt: &Runtime, hub_id: &str) -> crate::Result<Vec<ImportBatch>> {
    let db = rt.db();
    ensure_batch_tables(db).await?;
    let res = db
        .query(
            "SELECT b.id AS id, b.name AS name, b.created_at AS created_at, \
                    (SELECT count(*) FROM _hub_import_row r WHERE r.batch_id = b.id) AS rows \
             FROM _hub_import_batch b WHERE b.hub_id = :hub_id ORDER BY b.created_at DESC",
            &hub_params(hub_id),
        )
        .await
        .map_err(|e| crate::RuntimeError::Other(format!("reset: listar lotes: {e}")))?;
    Ok(res
        .rows
        .iter()
        .map(|r| ImportBatch {
            id: r["id"].as_str().unwrap_or_default().to_string(),
            name: r["name"].as_str().unwrap_or_default().to_string(),
            rows: r["rows"].as_i64().unwrap_or(0),
            created_at: r["created_at"].as_str().unwrap_or_default().to_string(),
        })
        .collect())
}

/// Deshace una importación: borra EXACTAMENTE las filas que ese lote insertó, nada más.
///
/// Acotado por `hub_id` (el lote pertenece a un hub) e **idempotente**: deshacer dos veces no
/// falla ni borra de más — el registro del lote se consume al aplicarlo.
pub async fn undo_import(rt: &Runtime, hub_id: &str, batch_id: &str) -> crate::Result<ResetReport> {
    let db = rt.db();
    ensure_batch_tables(db).await?;

    // El lote debe ser DE ESTE HUB: sin esta comprobación, un batch_id de otro tenant borraría
    // sus filas (misma BD compartida por organización).
    let mut p = hub_params(hub_id);
    p.insert("batch".into(), serde_json::json!(batch_id));
    let owned = db
        .query(
            "SELECT id FROM _hub_import_batch WHERE id = :batch AND hub_id = :hub_id",
            &p,
        )
        .await
        .map_err(|e| crate::RuntimeError::Other(format!("reset: leer el lote: {e}")))?;
    if owned.rows.is_empty() {
        // Ya deshecho (o de otro hub): no es un error, es idempotencia.
        return Ok(ResetReport::default());
    }

    let rows = db
        .query(
            "SELECT table_name, row_id FROM _hub_import_row WHERE batch_id = :batch",
            &p,
        )
        .await
        .map_err(|e| crate::RuntimeError::Other(format!("reset: leer filas del lote: {e}")))?;

    // Agrupado por tabla, y las tablas en orden inverso de FK (igual que el reset por secciones).
    let mut by_table: Vec<(String, Vec<String>)> = Vec::new();
    for r in &rows.rows {
        let (Some(t), Some(id)) = (r["table_name"].as_str(), r["row_id"].as_str()) else { continue };
        if !safe_ident(t) {
            continue;
        }
        match by_table.iter_mut().find(|(name, _)| name == t) {
            Some((_, ids)) => ids.push(id.to_string()),
            None => by_table.push((t.to_string(), vec![id.to_string()])),
        }
    }
    let order = delete_order(db, by_table.iter().map(|(t, _)| t.clone()).collect()).await;
    by_table.sort_by_key(|(t, _)| order.iter().position(|o| o == t).unwrap_or(usize::MAX));

    let mut ops: Vec<(String, erplora_db::Params)> = Vec::new();
    let mut outcomes: Vec<SectionOutcome> = Vec::new();
    for (table, ids) in &by_table {
        // Literales seguros: los ids salen de nuestro propio registro y se escapan igual.
        let list = ids
            .iter()
            .map(|id| format!("'{}'", id.replace('\'', "''")))
            .collect::<Vec<_>>()
            .join(", ");
        ops.push((
            format!("DELETE FROM {table} WHERE id IN ({list})"),
            erplora_db::Params::new(),
        ));
        outcomes.push(SectionOutcome { section: table.clone(), rows_deleted: ids.len() as i64 });
    }
    // El registro del lote se consume en la MISMA transacción: si el borrado revierte, el lote
    // sigue ahí y se puede reintentar (y si no, deshacer otra vez es un no-op limpio).
    ops.push((
        "DELETE FROM _hub_import_row WHERE batch_id = :batch".into(),
        p.clone(),
    ));
    ops.push((
        "DELETE FROM _hub_import_batch WHERE id = :batch AND hub_id = :hub_id".into(),
        p.clone(),
    ));

    db.execute_tx(&ops).await.map_err(|e| {
        crate::RuntimeError::Other(format!("reset: deshacer el import falló, nada se borró: {e}"))
    })?;
    Ok(ResetReport { sections: outcomes })
}
