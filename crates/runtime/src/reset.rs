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

use crate::export::{
    foreign_keys, has_column, list_tables, safe_ident, table_owner, ROLES_SECTION,
};
use crate::Runtime;

/// Table behind the `roles` section (system migration v13). Named once, next to the section it
/// backs, so the mirror of the export cannot drift into clearing something else.
const ROLES_TABLE: &str = "hub_role_activation";

/// Section name + table for the print queue (hub#502). `_print_queue` is DATA — pending receipts
/// of sales the reset deletes — so it IS swept. `_print_host` is NOT (local/printer config) and
/// must survive: see the `print_host_survives_a_full_reset` e2e.
const PRINT_QUEUE_SECTION: &str = "print_queue";
const PRINT_QUEUE_TABLE: &str = "_print_queue";

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
    /// The hub's role set (`hub_role_activation`, hub#417): which of the roles the installed
    /// modules DECLARE are live here. Off by default like everything else — switching a role off
    /// makes it unassignable, so it is never a side effect of clearing something else.
    pub roles: bool,
    /// The print queue (`_print_queue`, hub#502): pending tickets from sales the reset just
    /// deleted. Since hub#343 there IS a host draining it, so a reset followed by an app
    /// reconnecting would print **ghost tickets of a business that no longer exists**. The queue
    /// is DATA, unlike `_print_host` (which LOCAL config and stays — see [`print_host_survives`]).
    pub print_queue: bool,
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
    // Desde hub#497 `hub_user` SÍ lleva `hub_id`: se cuentan las personas de ESTE hub. Antes se
    // contaba la tabla entera, así que en una BD compartida el plan del reset prometía borrar —y el
    // borrado se llevaba— al personal del negocio de al lado.
    sections.push(SectionPlan {
        section: "hub_users".into(),
        rows: count_raw(
            rt,
            "SELECT count(*) AS n FROM hub_user WHERE hub_id = :hub_id",
            hub_id,
        )
        .await,
        blocked_by: None,
    });
    // The role set (hub#417). Counted from the table and not from the catalogue: the catalogue
    // hides a row whose module is deactivated, and the reset takes the ROWS — so a figure read off
    // the catalogue would under-count exactly what the owner is about to delete.
    sections.push(SectionPlan {
        section: ROLES_SECTION.into(),
        rows: count_where(rt, ROLES_TABLE, "TRUE", hub_id).await,
        blocked_by: None,
    });
    // The print queue (hub#502): pending receipts of sales the reset is about to delete. Counted
    // with the SAME `WHERE hub_id` as the DELETE — the dry-run must announce exactly what goes.
    // `_print_host` is NOT here on purpose: it is local/printer config, not business data.
    sections.push(SectionPlan {
        section: PRINT_QUEUE_SECTION.into(),
        rows: count_where(rt, PRINT_QUEUE_TABLE, "TRUE", hub_id).await,
        blocked_by: None,
    });

    // Límite fiscal: se calcula UNA vez y se aplica a todas las secciones que lo sostienen.
    let hold = fiscal_hold(rt, hub_id).await;

    for module_id in module_ids(rt) {
        let mut rows = 0;
        for table in module_tables(rt, db, &module_id).await {
            rows += count_raw(rt, &table.count_sql(), hub_id).await;
        }
        sections.push(SectionPlan {
            section: format!("modules/{module_id}"),
            rows,
            blocked_by: fiscal_block(&module_id, hold),
        });
    }
    Ok(ResetPlan { sections })
}

// ── Límite fiscal (RD 1007/2023) ────────────────────────────────────────────────────────

/// Módulos cuyos datos **sostienen** los registros de facturación remitidos: borrarlos dejaría
/// la cadena VeriFactu apuntando a facturas que ya no existen.
const FISCAL_SECTIONS: [&str; 3] = ["verifactu", "invoice", "sales"];

/// Lo que la ley congela en este hub, y cuánto de ello el core puede poner en una cifra.
///
/// **Dos fuentes a propósito, y bloquea la UNIÓN** (hub#561, ADR-0273):
///
/// - [`FiscalHold::emitted`] — `_hub_fiscal_profile.first_record_at`, el sello del PROPIO core:
///   este hub ya mandó un registro a una administración tributaria de verdad. Es
///   **país-agnóstico** y tiene dueño dentro del runtime, así que sostiene el límite en los dos
///   casos donde el conteo de abajo devuelve 0 sin decir nada: un hub francés bajo Factur-X (que
///   no tiene `verifactu_record`) y uno español al que le desinstalaron el módulo.
/// - [`FiscalHold::remitted`] — el conteo sobre la tabla del módulo, que se queda como **red**.
///
/// **Por qué la red sigue puesta aunque hub#551 ya selle el campo.** El sello va sólo **hacia
/// delante**: lo estampa el dispatcher al commitear una transacción que arranca cadena con el perfil
/// en `production` ([`crate::fiscal_profile::stamp_first_record`]). **Nada lo rellena hacia atrás.**
/// Un hub que ya facturó ANTES de esta versión llega con `first_record_at = ''` —la migración v27
/// crea la columna con `DEFAULT ''`— y con `environment = 'testing'`, porque el único que escribe
/// `production` es `go_live`, un botón que entonces no existía. Su única huella son las filas
/// `accepted` de `verifactu_record`. Quitar el conteo dejaría resetear justo a ese hub: el que más
/// tiene que perder.
///
/// Se retira cuando el perfil se rellene hacia atrás, o cuando se dé por bueno que no queda ningún
/// hub anterior al sello.
#[derive(Debug, Clone, Copy, Default)]
struct FiscalHold {
    /// El hub ya emitió, según el perfil fiscal del core.
    emitted: bool,
    /// Facturas remitidas que el módulo `verifactu` todavía puede contar; 0 si no está.
    remitted: i64,
}

impl FiscalHold {
    /// ¿Hay algo que la ley congele? La unión: cualquiera de las dos fuentes basta.
    fn holds(self) -> bool {
        self.emitted || self.remitted > 0
    }
}

/// Resuelve el límite fiscal del hub `hub_id`. Se llama UNA vez por operación y se aplica a todas
/// las secciones que lo sostienen.
async fn fiscal_hold(rt: &Runtime, hub_id: &str) -> FiscalHold {
    FiscalHold {
        emitted: has_emitted(rt, hub_id).await,
        remitted: remitted_invoices(rt, hub_id).await,
    }
}

/// `first_record_at IS NOT NULL` escrito contra el contrato de fila del hub, donde el «nunca» de un
/// instante es `""` y no `NULL`.
///
/// Un perfil que no se puede leer (hub aún sin arrancar, base de datos vieja sin la tabla) degrada
/// a `false` en vez de a error: es la mitad de seguridad de un panel, y un `plan_reset` que revienta
/// deja al dueño sin poder hacer NADA. Lo que no se puede leer lo cubre el conteo de abajo.
async fn has_emitted(rt: &Runtime, hub_id: &str) -> bool {
    matches!(
        crate::fiscal_profile::load(rt.db(), hub_id).await,
        Ok(Some(profile)) if !profile.first_record_at.is_empty()
    )
}

/// Facturas del hub **ya remitidas a la AEAT**: `status` transmitido/aceptado o con CSV de la
/// AEAT. Son **inalterables** (RD 1007/2023). 0 si el módulo `verifactu` no está instalado (la
/// consulta falla y `count_raw` devuelve 0) — y ese silencio es justo lo que hub#561 tapa con
/// [`has_emitted`].
///
/// El criterio es EXACTO, no heurístico: los datos de demo se quedan en `pending` y sin CSV, así
/// que el caso que motiva el ADR-0170 —probar la demo y borrarla— nunca se bloquea. Y es el mismo
/// hecho que sella `first_record_at` (una cadena fiscal que arrancó de verdad), así que la unión de
/// los dos se comporta igual que antes: esto es desacoplar, no cambiar la política.
async fn remitted_invoices(rt: &Runtime, hub_id: &str) -> i64 {
    count_raw(
        rt,
        "SELECT count(*) AS n FROM verifactu_record WHERE hub_id = :hub_id \
         AND (status IN ('transmitted', 'accepted') OR aeat_csv <> '')",
        hub_id,
    )
    .await
}

/// Motivo del bloqueo de una sección, o `None` si no aplica. Un bloqueo sin explicación se lee como
/// un fallo del producto y no como la ley, así que siempre hay texto: con la CIFRA y nombrando a la
/// AEAT cuando el módulo español todavía puede contarlas, y **sin nombrar país** cuando lo único
/// que se sabe es que el hub ya emitió (el caso de un régimen que no es VeriFactu).
fn fiscal_block(module_id: &str, hold: FiscalHold) -> Option<String> {
    if !hold.holds() || !FISCAL_SECTIONS.contains(&module_id) {
        return None;
    }
    Some(if hold.remitted > 0 {
        format!(
            "{} facturas remitidas a la AEAT: inalterables por RD 1007/2023, \
             no se pueden borrar",
            hold.remitted
        )
    } else {
        "este hub ya ha emitido registros de facturación ante su administración tributaria: \
         son inalterables y no se pueden borrar"
            .to_string()
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
    let hold = fiscal_hold(rt, hub_id).await;
    if hold.holds() {
        let bloqueada = selection
            .modules
            .iter()
            .find(|m| FISCAL_SECTIONS.contains(&m.as_str()))
            .map(|m| format!("modules/{m}"))
            .or_else(|| selection.fiscal.then(|| "fiscal".to_string()));
        if let Some(section) = bloqueada {
            return Err(crate::RuntimeError::Other(format!(
                "reset: la sección {section} está bloqueada — {}. No se ha borrado nada.",
                fiscal_block("verifactu", hold).unwrap_or_default()
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
        // Nunca al actor: un owner no puede quedarse fuera de su propio hub con un clic. Y nunca
        // fuera de este hub: desde hub#497 `hub_user` lleva `hub_id` y el borrado se acota por él.
        ops.push((
            "hub_users".into(),
            "hub_user".into(),
            "DELETE FROM hub_user WHERE hub_id = :hub_id AND id <> :actor".into(),
        ));
    }
    // The role set (hub#417) — the half of the mirror the reset never had. Once the export learned
    // to carry which roles this hub has live (ADR-0242), the reset had to learn to clear them, or
    // «lo que el hub sabe exportar es exactamente lo que sabe borrar» stopped being true.
    //
    // It matters beyond symmetry: a switched-on role is a role that can be HANDED to a person
    // (`roles::ensure_assignable`), a bundle can switch one on, and until now the only way to take
    // that back was to uninstall the module that declared it. This is the owner's door in the other
    // direction — and it only ever DELETEs, so it can never be a way to grant.
    //
    // Base roles are not here to be protected: they are live by construction and have no row.
    if selection.roles && existing.iter().any(|t| t == ROLES_TABLE) {
        ops.push((
            ROLES_SECTION.into(),
            ROLES_TABLE.into(),
            format!("DELETE FROM {ROLES_TABLE} WHERE hub_id = :hub_id"),
        ));
    }
    // The print queue (hub#502): since hub#343 a host DRAINS it, so a reset followed by an app
    // reconnecting would print ghost tickets of a business that just got deleted. Sweeping the
    // queue is the owner's door the other way. `_print_host` (which printer prints kitchen) is
    // LOCAL config and stays — re-pairing printers after every reset is exactly what hub#342
    // avoided on purpose.
    if selection.print_queue && existing.iter().any(|t| t == PRINT_QUEUE_TABLE) {
        ops.push((
            PRINT_QUEUE_SECTION.into(),
            PRINT_QUEUE_TABLE.into(),
            format!("DELETE FROM {PRINT_QUEUE_TABLE} WHERE hub_id = :hub_id"),
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
    let tx: Vec<(String, erplora_db::Params)> = ops
        .iter()
        .map(|(_, _, sql)| (sql.clone(), p.clone()))
        .collect();
    db.execute_tx(&tx).await.map_err(|e| {
        crate::RuntimeError::Other(format!("reset: la transacción falló, nada se borró: {e}"))
    })?;

    Ok(ResetReport {
        sections: planned
            .into_iter()
            .map(|(section, rows_deleted)| SectionOutcome {
                section,
                rows_deleted,
            })
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
        format!(
            "DELETE FROM {} WHERE {} AND {}",
            self.name, self.scope, self.user_rows
        )
    }
    fn count_sql(&self) -> String {
        format!(
            "SELECT count(*) AS n FROM {} WHERE {} AND {}",
            self.name, self.scope, self.user_rows
        )
    }
}

fn module_ids(rt: &Runtime) -> Vec<String> {
    rt.registry()
        .installed
        .iter()
        .map(|m| m.id.clone())
        .collect()
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
        out.push(ResetTable {
            name,
            user_rows,
            scope,
        });
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
        conds.push(format!(
            "({prefix}is_system IS NULL OR {prefix}is_system = 0)"
        ));
    }
    if has_column(db, table, "source").await {
        conds.push(format!(
            "({prefix}source IS NULL OR {prefix}source <> 'shipped')"
        ));
    }
    if has_column(db, table, "created_by").await {
        conds.push(format!(
            "({prefix}created_by IS NULL OR {prefix}created_by <> 'system')"
        ));
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
    let Some(scope) = tenant_scope(rt.db(), table).await else {
        return 0;
    };
    count_raw(
        rt,
        &format!("SELECT count(*) AS n FROM {table} WHERE {scope} AND {extra}"),
        hub_id,
    )
    .await
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
            sections: vec![SectionOutcome {
                section: "hub_settings".into(),
                rows_deleted: 7,
            }],
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
        assert!(
            !sel.print_queue,
            "la cola de impresión tampoco se borra por defecto"
        );
        assert!(sel.modules.is_empty());
    }

    // ── El límite duro, sin base de datos de por medio (hub#561, ADR-0273) ───────────────
    //
    // Los e2e de `tests/reset_fiscal_test.rs` prueban esto contra los módulos REALES, pero el
    // gate de pre-push los salta por paridad con CI (`ERPLORA_E2E_ALLOW_SKIP=1`). La decisión
    // —qué bloquea y con qué texto— se fija aquí también, en el nivel que SIEMPRE corre.

    /// **El sello del core basta.** Es todo el punto de hub#561: un hub que ya emitió queda
    /// bloqueado aunque el módulo que sabía contarlo no esté (otro régimen, o desinstalado).
    #[test]
    fn el_sello_del_core_bloquea_sin_que_ningun_modulo_cuente_nada() {
        let hold = FiscalHold {
            emitted: true,
            remitted: 0,
        };
        let motivo = fiscal_block("sales", hold).expect("un hub que emitió bloquea sus ventas");
        assert!(
            !motivo.is_empty(),
            "el bloqueo llega siempre con motivo escrito"
        );
        // País-agnóstico: sin cifra que dar, el texto NO puede nombrar a la AEAT — sería meter
        // España en un core que ya no la nombra.
        assert!(
            !motivo.to_lowercase().contains("aeat"),
            "sin conteo del módulo español, el motivo no nombra país: {motivo}"
        );
    }

    /// **La red sigue puesta.** El sello de hub#551 sólo va hacia delante y nada lo rellena hacia
    /// atrás, así que en un hub que facturó ANTES de esta versión el conteo sobre la tabla del
    /// módulo es lo ÚNICO que bloquea. Si este test cae, el límite duro se apagó para ese hub.
    #[test]
    fn el_conteo_del_modulo_sigue_bloqueando_con_el_sello_aun_vacio() {
        let hold = FiscalHold {
            emitted: false,
            remitted: 2,
        };
        let motivo = fiscal_block("verifactu", hold).expect("2 facturas remitidas bloquean");
        assert!(motivo.contains('2'), "el motivo dice CUÁNTAS: {motivo}");
        assert!(
            motivo.to_lowercase().contains("aeat"),
            "y nombra a la AEAT: {motivo}"
        );
    }

    /// Nada sellado y nada contado ⇒ nada bloqueado. El caso ADR-0170: probar la demo y borrarla.
    #[test]
    fn sin_sello_ni_conteo_no_se_bloquea_nada() {
        assert!(!FiscalHold::default().holds());
        assert_eq!(fiscal_block("sales", FiscalHold::default()), None);
    }

    /// El alcance no se toca: el límite congela las secciones fiscal/ventas, no el reset entero.
    #[test]
    fn el_bloqueo_solo_alcanza_a_las_secciones_fiscales() {
        let hold = FiscalHold {
            emitted: true,
            remitted: 3,
        };
        for fiscal in FISCAL_SECTIONS {
            assert!(
                fiscal_block(fiscal, hold).is_some(),
                "{fiscal} sostiene lo emitido"
            );
        }
        assert_eq!(
            fiscal_block("inventory", hold),
            None,
            "limpiar el catálogo de demo nunca se bloquea por una factura"
        );
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
 batch_id TEXT NOT NULL, table_name TEXT NOT NULL, row_id TEXT NOT NULL);\
CREATE TABLE IF NOT EXISTS _hub_import_retired_row (\
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
    p.insert(
        "now".into(),
        serde_json::json!(crate::registry::now_rfc3339()),
    );
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
            let Some(row_id) = row.get("id").and_then(|v| v.as_str()) else {
                continue;
            };
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
            .map_err(|e| {
                crate::RuntimeError::Other(format!("reset: registrar fila del lote: {e}"))
            })?;
        }
        applied += 1;
    }
    Ok(applied)
}

/// Ids de las filas VIVAS que `table` tiene ahora mismo en este hub.
///
/// Es la foto que [`retire_replaced_placeholder`] compara contra la de después de aplicar la
/// sección: lo que ya estaba es lo que el bundle sustituye, y lo que no estaba es la prueba de que
/// el bundle llegó a entrar. Se saca por `id` y no por `count(*)` porque hacen falta las dos cosas
/// —cuánto y CUÁL— y una tabla puede perder y ganar filas en la misma sección.
pub(crate) async fn live_row_ids(
    db: &dyn erplora_db::DatabaseAdapter,
    hub_id: &str,
    table: &str,
) -> crate::Result<Vec<String>> {
    if !safe_ident(table)
        || !has_column(db, table, "hub_id").await
        || !has_column(db, table, "is_deleted").await
    {
        return Ok(Vec::new());
    }
    let p = hub_params(hub_id);
    let res = db
        .query(
            &format!("SELECT id FROM {table} WHERE hub_id = :hub_id AND is_deleted = 0"),
            &p,
        )
        .await
        .map_err(|e| {
            crate::RuntimeError::Other(format!("import: leer las filas vivas de {table}: {e}"))
        })?;
    Ok(res
        .rows
        .iter()
        .filter_map(|r| r.get("id").and_then(|v| v.as_str()).map(str::to_string))
        .collect())
}

/// Retira el contenido ANTERIOR de una tabla de **objeto único**, ahora que la sección del bundle
/// acaba de poner ahí el suyo (hub#1535 · hub#1548).
///
/// El caso que lo motiva: un hub recién montado instala `schedules`, cuyo seed siembra una semana
/// genérica (Mon–Fri 09:00–18:00, fin de semana cerrado) para que «sin horario configurado» deje de
/// ser un estado alcanzable (schedules#36). Después llega el blueprint del sector con el horario
/// REAL, y las dos semanas conviven: el sábado sale abierto de 09:30 a 14:00 **y** cerrado, y
/// «¿estamos abiertos?» contesta según la fila que le toque. Ninguna de las dos guardas de
/// idempotencia puede evitarlo — no hay índice único (`schedules#8` lo retiró: una jornada partida
/// son varias filas por día) y el seed no declara clave (su guarda es la tabla entera) —, así que
/// la guarda queda solo por `id` y los ids nunca coinciden.
///
/// hub#1535 lo cerró retirando **lo que firmó el instalador** (`created_by = 'system'`). hub#1548
/// enseñó que el cruce es más ancho: si el negocio prueba un blueprint y después OTRO, las dos
/// semanas que chocan las trajeron dos plantillas y ya no queda ninguna fila `system` a la que
/// agarrarse — cada día salía dos veces, con las horas de la primera y las de la segunda. Por eso
/// lo que se retira no es «lo que firmó el instalador» sino **lo que hubiera antes**, sea de quien
/// sea: una guarda de seed por la tabla entera es el módulo declarando que ahí vive UN objeto del
/// hub, y un objeto no se importa dos veces, se sustituye. Es lo que hace todo el mercado con los
/// datos maestros (Odoo hace upsert por external ID, Shopify casa por handle, Business Central
/// sobrescribe al aplicar el paquete de configuración): ninguno deja dos lunes contradictorios.
///
/// Suena a borrado silencioso de datos del negocio, y no lo es — por los cuatro cierres, y los
/// cuatro importan:
///
/// * **Solo tablas que el módulo declaró como marcador** (`Registry::seeds_placeholder_table`), o
///   sea aquellas cuyo seed se guarda por el hub entero. Las categorías fiscales canónicas de
///   `taxes` o las unidades de `inventory` NO entran: su seed declara clave por fila, van por la
///   vía de hub#842 y borrarlas se llevaría por delante datos de referencia que otros módulos
///   resuelven por clave (`tax_category_key`).
/// * **Solo si la sección llegó a ENTRAR en esta tabla.** Se exige una fila viva que no estuviera
///   en la foto anterior: si la sección no insertó nada (guarda que la saltó, índice único que la
///   rechazó), retirar el contenido dejaría al hub sin horario — exactamente el estado que
///   schedules#36 hizo inalcanzable. Por eso se llama DESPUÉS de aplicar, no antes.
/// * **Soft-delete, y apuntado en el lote.** La fila se marca `is_deleted = 1` como manda el
///   contrato de fila, y su id queda registrado para que [`undo_import`] la devuelva. Sustituir
///   solo vale si es REVERSIBLE: deshacer el segundo blueprint devuelve el primero entero. Sin
///   eso, deshacer la importación borraría el horario importado y dejaría lo anterior enterrado:
///   la guarda del seed no filtra `is_deleted`, así que el módulo NO lo replantaría nunca y el hub
///   se quedaría sin horas para siempre.
/// * **Acotado al hub que importó.** En una BD compartida por varios hubs (el reparto pre-ADR-0201,
///   vivo aún para los hubs legacy) la semana del vecino no se toca.
///
/// Devuelve cuántas filas retiró. Es best-effort como el resto del camino del import: una tabla sin
/// las columnas del contrato de fila no se toca.
pub(crate) async fn retire_replaced_placeholder(
    rt: &Runtime,
    batch_id: Option<&str>,
    hub_id: &str,
    table: &str,
    previous: &[String],
) -> crate::Result<usize> {
    let db = rt.db();
    if !safe_ident(table) {
        return Ok(0);
    }
    // Sin `is_deleted` no se puede retirar sin BORRAR, y borrar no lo devuelve el undo: se deja
    // como estaba, igual que hace el resto del import ante una tabla que no entiende.
    if !has_column(db, table, "is_deleted").await {
        return Ok(0);
    }

    let live = live_row_ids(db, hub_id, table).await?;
    // ¿Aterrizó algo de la sección EN ESTA TABLA? Una fila viva que no estaba en la foto anterior
    // es la prueba, y es la única que vale: `applied` cuenta la sección ENTERA, así que una tabla
    // que no recibió nada saldría igual de verde que una que sí.
    if !live.iter().any(|id| !previous.contains(id)) {
        return Ok(0);
    }
    // `previous` es la foto de las filas VIVAS de antes, y sigue siéndolo: los datos de un bundle
    // solo pueden ser `INSERT INTO` (`import_sql` rechaza `UPDATE`/`DELETE`, y hasta el
    // `WITH x AS (DELETE …)` que PG aceptaría), así que aplicar la sección no puede haber enterrado
    // ninguna. Intersecar con `live` sería una rama que ningún test puede alcanzar.
    let ids = previous;
    if ids.is_empty() {
        return Ok(0);
    }

    // Literales seguros: los ids salen de una consulta nuestra y se escapan igual que en el undo.
    let list = ids
        .iter()
        .map(|id| format!("'{}'", id.replace('\'', "''")))
        .collect::<Vec<_>>()
        .join(", ");
    let now = crate::registry::now_rfc3339();
    let mut sets = format!("is_deleted = 1, updated_at = '{now}'");
    if has_column(db, table, "deleted_at").await {
        sets.push_str(&format!(", deleted_at = '{now}'"));
    }
    let mut ops: Vec<(String, erplora_db::Params)> = vec![(
        format!("UPDATE {table} SET {sets} WHERE id IN ({list})"),
        erplora_db::Params::new(),
    )];
    // El registro va en la MISMA transacción que el soft-delete: un marcador retirado que el lote
    // no apuntara sería un horario que `undo_import` no sabría devolver.
    if let Some(batch) = batch_id {
        ensure_batch_tables(db).await?;
        for id in ids {
            let mut rp = erplora_db::Params::new();
            rp.insert("batch_id".into(), serde_json::json!(batch));
            rp.insert("table_name".into(), serde_json::json!(table));
            rp.insert("row_id".into(), serde_json::json!(id));
            ops.push((
                "INSERT INTO _hub_import_retired_row (batch_id, table_name, row_id) \
                 VALUES (:batch_id, :table_name, :row_id)"
                    .into(),
                rp,
            ));
        }
    }
    db.execute_tx(&ops).await.map_err(|e| {
        crate::RuntimeError::Other(format!(
            "import: retirar el contenido anterior de {table}: {e}"
        ))
    })?;
    Ok(ids.len())
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

/// The actionable report of an import — the thing `ImportPanel.vue` paints and the Dashboard
/// promises (hub#763). One row per `batch_id`: re-importing the same blueprint opens a NEW batch
/// (so a new row), and the server UPSERTs the extended report (runtime sections + installed
/// modules + media + fiscal) over it once the orchestration finishes. Without it, the report lived
/// only in a Vue `ref` that navigation threw away — the admin arrived at Settings › Data and found
/// the catalogue, with no report, no reason and no way forward.
const ENSURE_REPORT_TABLE: &str = "CREATE TABLE IF NOT EXISTS _hub_import_report (\
 id TEXT PRIMARY KEY, hub_id TEXT NOT NULL, name TEXT NOT NULL, report TEXT NOT NULL, \
 created_at TEXT NOT NULL);";

/// Creates the import-report table if it is missing (idempotent, like the batch tables — it is NOT
/// a module migration, so it sidesteps the hub system-migration «max applied» trap).
async fn ensure_report_table(db: &dyn erplora_db::DatabaseAdapter) -> crate::Result<()> {
    db.execute_batch(ENSURE_REPORT_TABLE)
        .await
        .map_err(|e| crate::RuntimeError::Other(format!("reset: tabla de informe de import: {e}")))
}

/// Stores (or, on re-import over the same `batch_id`, replaces) the actionable report of one
/// import run (hub#763).
///
/// `report_json` is opaque to this layer: the runtime writes its [`crate::import::ImportReport`]
/// here, and the server later UPSERTs the EXTENDED report (modules/media/fiscal) it builds on top,
/// so the row a reload reads is the same the UI would have painted in-memory.
///
/// A failure here MUST NOT abort the import — the engine already ran. Like the batch it lives
/// under, losing it costs the traceability this PR adds, not the data the import applied.
pub async fn store_import_report(
    rt: &Runtime,
    hub_id: &str,
    batch_id: &str,
    name: &str,
    report_json: &str,
) -> crate::Result<()> {
    let db = rt.db();
    ensure_report_table(db).await?;
    let mut p = erplora_db::Params::new();
    p.insert("id".into(), serde_json::json!(batch_id));
    p.insert("hub_id".into(), serde_json::json!(hub_id));
    p.insert("name".into(), serde_json::json!(name));
    p.insert("report".into(), serde_json::json!(report_json));
    p.insert(
        "now".into(),
        serde_json::json!(crate::registry::now_rfc3339()),
    );
    // UPSERT: a `batch_id` is unique per import, so this only replaces on a replay over the exact
    // same batch (the server's «extend the runtime report with modules/media/fiscal» step).
    db.execute(
        "INSERT INTO _hub_import_report (id, hub_id, name, report, created_at) \
         VALUES (:id, :hub_id, :name, :report, :now) \
         ON CONFLICT(id) DO UPDATE SET report = :report, created_at = :now",
        &p,
    )
    .await
    .map_err(|e| {
        crate::RuntimeError::Other(format!("reset: persistir el informe de import: {e}"))
    })?;
    Ok(())
}

/// One persisted import report (the actionable document `ImportPanel.vue` paints), with its
/// `batch_id` and when it ran — enough for the UI to say «the import of <name> from <time>».
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct StoredImportReport {
    pub batch_id: String,
    pub name: String,
    /// The JSON the writer stored (runtime report, or the server's extended one). Opaque here.
    pub report: String,
    pub created_at: String,
}

/// The last actionable report for `hub_id`, most recent first (hub#763).
///
/// This is what the Data tab reads on mount to recover what the Dashboard pointed at: the most
/// recent import run, whatever it was. `None` when no import has run (or its batch was undone and
/// the report with it — see [`undo_import`]).
pub async fn last_import_report_for_hub(
    rt: &Runtime,
    hub_id: &str,
) -> crate::Result<Option<StoredImportReport>> {
    let db = rt.db();
    ensure_report_table(db).await?;
    let res = db
        .query(
            "SELECT id AS batch_id, name AS name, report AS report, created_at AS created_at \
             FROM _hub_import_report WHERE hub_id = :hub_id ORDER BY created_at DESC LIMIT 1",
            &hub_params(hub_id),
        )
        .await
        .map_err(|e| crate::RuntimeError::Other(format!("reset: leer el último informe: {e}")))?;
    Ok(res.rows.first().map(|r| StoredImportReport {
        batch_id: r["batch_id"].as_str().unwrap_or_default().to_string(),
        name: r["name"].as_str().unwrap_or_default().to_string(),
        report: r["report"].as_str().unwrap_or_default().to_string(),
        created_at: r["created_at"].as_str().unwrap_or_default().to_string(),
    }))
}

/// The actionable report of ONE import run, by its `batch_id`, scoped to `hub_id` (hub#763).
///
/// `None` when the batch does not exist, belongs to another hub, or was undone (its report row is
/// deleted together with the batch in [`undo_import`]). This is the same hub-scoping the undo path
/// relies on, so an admin cannot read another tenant's report by guessing a `batch_id`.
pub async fn last_import_report(
    rt: &Runtime,
    hub_id: &str,
    batch_id: &str,
) -> crate::Result<Option<StoredImportReport>> {
    let db = rt.db();
    ensure_report_table(db).await?;
    let mut p = hub_params(hub_id);
    p.insert("batch".into(), serde_json::json!(batch_id));
    let res = db
        .query(
            "SELECT id AS batch_id, name AS name, report AS report, created_at AS created_at \
             FROM _hub_import_report WHERE id = :batch AND hub_id = :hub_id",
            &p,
        )
        .await
        .map_err(|e| crate::RuntimeError::Other(format!("reset: leer el informe: {e}")))?;
    Ok(res.rows.first().map(|r| StoredImportReport {
        batch_id: r["batch_id"].as_str().unwrap_or_default().to_string(),
        name: r["name"].as_str().unwrap_or_default().to_string(),
        report: r["report"].as_str().unwrap_or_default().to_string(),
        created_at: r["created_at"].as_str().unwrap_or_default().to_string(),
    }))
}

/// Deshace una importación: borra EXACTAMENTE las filas que ese lote insertó, nada más.
///
/// Acotado por `hub_id` (el lote pertenece a un hub) e **idempotente**: deshacer dos veces no
/// falla ni borra de más — el registro del lote se consume al aplicarlo.
pub async fn undo_import(rt: &Runtime, hub_id: &str, batch_id: &str) -> crate::Result<ResetReport> {
    let db = rt.db();
    ensure_batch_tables(db).await?;
    // The report table is deleted in the same tx (hub#763): ensure it exists so the DELETE is
    // valid even on a hub whose imports never persisted a report (fresh DB, batch never stored one).
    ensure_report_table(db).await?;

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
    // hub#1535: y los marcadores que este lote RETIRÓ, que vuelven. Deshacer un import tiene que
    // dejar el hub como estaba, y como estaba era con la semana genérica que el módulo sembró al
    // instalarse — no sin horario. El seed no la replantaría: su guarda no filtra `is_deleted`, así
    // que ve la fila enterrada y no hace nada. Si no la devolvemos aquí, no la devuelve nadie.
    let retired = db
        .query(
            "SELECT table_name, row_id FROM _hub_import_retired_row WHERE batch_id = :batch",
            &p,
        )
        .await
        .map_err(|e| {
            crate::RuntimeError::Other(format!("reset: leer marcadores retirados del lote: {e}"))
        })?;

    // Agrupado por tabla, y las tablas en orden inverso de FK (igual que el reset por secciones).
    let mut by_table: Vec<(String, Vec<String>)> = Vec::new();
    for r in &rows.rows {
        let (Some(t), Some(id)) = (r["table_name"].as_str(), r["row_id"].as_str()) else {
            continue;
        };
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
        outcomes.push(SectionOutcome {
            section: table.clone(),
            rows_deleted: ids.len() as i64,
        });
    }
    // El registro del lote se consume en la MISMA transacción: si el borrado revierte, el lote
    // sigue ahí y se puede reintentar (y si no, deshacer otra vez es un no-op limpio).
    // Los marcadores vuelven ANTES de consumir el registro del lote, y en la misma transacción
    // que los borrados: o el hub vuelve entero a como estaba, o no se mueve nada.
    let mut retired_by_table: Vec<(String, Vec<String>)> = Vec::new();
    for r in &retired.rows {
        let (Some(t), Some(id)) = (r["table_name"].as_str(), r["row_id"].as_str()) else {
            continue;
        };
        if !safe_ident(t) {
            continue;
        }
        match retired_by_table.iter_mut().find(|(name, _)| name == t) {
            Some((_, ids)) => ids.push(id.to_string()),
            None => retired_by_table.push((t.to_string(), vec![id.to_string()])),
        }
    }
    for (table, ids) in &retired_by_table {
        // hub#1551: se devuelve lo retirado SOLO si el hueco que dejó SIGUE AHÍ. Es el espejo de
        // la regla de la retirada («solo si el dato de verdad está ya dentro»), y sin él deshacer
        // vuelve a plantar el marcador ENCIMA de lo que el negocio ya escribió: importas una
        // plantilla, ajustas el lunes en la pantalla de horas, deshaces, y el lunes sale dos veces
        // —el genérico de 09:00 a 18:00 y el tuyo— que es exactamente el síntoma que hub#1535
        // cerró, entrando por la otra puerta.
        //
        // El hueco sigue ahí si, quitadas las filas que este lote insertó (las de arriba, que se
        // borran en esta misma transacción), no queda nada vivo en la tabla. Si queda algo, lo
        // escribió una persona después de importar: la tabla ya es suya y el marcador se queda
        // retirado. No hay forma de devolverlo «solo por los días que falten» — no hay clave
        // declarada, que es precisamente el motivo de que exista hub#1535.
        let batch_rows: &[String] = by_table
            .iter()
            .find(|(t, _)| t == table)
            .map(|(_, i)| i.as_slice())
            .unwrap_or(&[]);
        let survivors = live_row_ids(db, hub_id, table)
            .await?
            .into_iter()
            .filter(|id| !batch_rows.contains(id))
            .count();
        if survivors > 0 {
            continue;
        }
        let list = ids
            .iter()
            .map(|id| format!("'{}'", id.replace('\'', "''")))
            .collect::<Vec<_>>()
            .join(", ");
        // Misma comprobación que al retirar: `deleted_at` es opcional en el contrato de fila, y
        // nombrarla donde no existe tumbaría la transacción ENTERA del undo.
        let mut sets = String::from("is_deleted = 0");
        if has_column(db, table, "deleted_at").await {
            sets.push_str(", deleted_at = NULL");
        }
        ops.push((
            format!("UPDATE {table} SET {sets} WHERE id IN ({list})"),
            erplora_db::Params::new(),
        ));
    }
    // hub#1555 (review of hub#1548): the chain of substitutions is INHERITED when a batch is undone
    // out of order. Settings › Data lists every batch with its own «undo» button, so the business
    // can undo template A while template B — which retired A's week — is still in place. A's rows
    // are being hard-deleted above, and they are exactly the rows B's ledger promised to bring
    // back: without this, undoing B afterwards restores ids that no longer exist and the hub is
    // left with NO hours — the state schedules#36 made unreachable. So what A had retired (the
    // seeded week) passes on to B's ledger, in this same transaction: undoing B then gives back
    // what was there before A, which is the honest «before B» once A is gone. An id lives in ONE
    // ledger at a time (a batch only retires LIVE rows, and what it retired was already buried when
    // the next one ran), so the move needs no dedupe.
    for (table, ids) in &by_table {
        let list = ids
            .iter()
            .map(|id| format!("'{}'", id.replace('\'', "''")))
            .collect::<Vec<_>>()
            .join(", ");
        let mut tp = p.clone();
        tp.insert("table_name".into(), serde_json::json!(table));
        let heirs = db
            .query(
                &format!(
                    "SELECT DISTINCT r.batch_id AS batch_id FROM _hub_import_retired_row r \
                     JOIN _hub_import_batch b ON b.id = r.batch_id \
                     WHERE b.hub_id = :hub_id AND r.batch_id <> :batch \
                       AND r.table_name = :table_name AND r.row_id IN ({list})"
                ),
                &tp,
            )
            .await
            .map_err(|e| {
                crate::RuntimeError::Other(format!(
                    "reset: read which later batch retired the rows of {table}: {e}"
                ))
            })?;
        let inherited: &[String] = retired_by_table
            .iter()
            .find(|(t, _)| t == table)
            .map(|(_, i)| i.as_slice())
            .unwrap_or(&[]);
        for heir in heirs.rows.iter().filter_map(|r| r["batch_id"].as_str()) {
            let mut hp = tp.clone();
            hp.insert("heir".into(), serde_json::json!(heir));
            // The later batch stops waiting for rows that are about to be gone…
            ops.push((
                format!(
                    "DELETE FROM _hub_import_retired_row \
                     WHERE batch_id = :heir AND table_name = :table_name AND row_id IN ({list})"
                ),
                hp.clone(),
            ));
            // …and waits for what THIS batch had retired instead.
            for id in inherited {
                let mut rp = hp.clone();
                rp.insert("row_id".into(), serde_json::json!(id));
                ops.push((
                    "INSERT INTO _hub_import_retired_row (batch_id, table_name, row_id) \
                     VALUES (:heir, :table_name, :row_id)"
                        .into(),
                    rp,
                ));
            }
        }
    }
    ops.push((
        "DELETE FROM _hub_import_retired_row WHERE batch_id = :batch".into(),
        p.clone(),
    ));
    ops.push((
        "DELETE FROM _hub_import_row WHERE batch_id = :batch".into(),
        p.clone(),
    ));
    ops.push((
        "DELETE FROM _hub_import_batch WHERE id = :batch AND hub_id = :hub_id".into(),
        p.clone(),
    ));
    // The actionable report travels with its batch (hub#763): undoing an import that «did not go
    // in» removes its report too, so the Data tab no longer offers the detail of something the hub
    // just rolled back. In the SAME transaction as the deletes, so a failed undo keeps both.
    ops.push((
        "DELETE FROM _hub_import_report WHERE id = :batch AND hub_id = :hub_id".into(),
        p.clone(),
    ));

    db.execute_tx(&ops).await.map_err(|e| {
        crate::RuntimeError::Other(format!(
            "reset: deshacer el import falló, nada se borró: {e}"
        ))
    })?;
    Ok(ResetReport { sections: outcomes })
}
