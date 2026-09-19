//! Seed-al-arrancar: carga de **configuración inicial** vía SQL idempotente (hub#36).
//!
//! Mecanismo GENÉRICO (NO es "modo demo"): si el host pasa SQL de seed (env `HUB_SEED_SQL`
//! inline o `HUB_SEED_SQL_PATH` a un fichero), el runtime lo ejecuta **una vez al arrancar**,
//! **después** de [`crate::Runtime::ensure_system_tables`] (las tablas de sistema ya existen).
//!
//! Idempotencia: es responsabilidad del propio SQL (usa `WHERE NOT EXISTS` / `ON CONFLICT`),
//! igual que hacía el seed legacy. Cualquier hub puede usarlo para sembrar config inicial; el
//! caso de uso inmediato es el despliegue *demo* (un `hub_user` "Demo" + dispositivo de confianza),
//! pero la mecánica no tiene nada específico de demo.
//!
//! Se aplica sobre la **misma conexión del runtime** (mismo adaptador → funciona en SQLite y
//! Postgres). Se parte en sentencias con [`crate::system_migrations`]-style split (`;`).

use erplora_db::DatabaseAdapter;

use crate::errors::{Result, RuntimeError};

/// Aplica `sql` (un batch de sentencias separadas por `;`) sobre `db`, una por una.
///
/// Devuelve cuántas sentencias aplicó. Se asume que el SQL es **idempotente** (el llamador lo
/// garantiza con `WHERE NOT EXISTS`/`ON CONFLICT`); este módulo NO añade guardas: solo ejecuta.
///
/// Liga `:hub_id`, como [`apply_module_seed`] (hub#489). Un seed se aplica **sobre un hub**, y
/// desde la migración de sistema v23 las tablas que siembra —`hub_trusted_device` la primera— van
/// acotadas por él: sin el bind, el seed escribiría filas que no nombran hub y que ningún hub
/// vería. El `hub_id` lo aporta el despliegue, no el fichero.
///
/// Si una sentencia falla, devuelve un error claro (con el índice de la sentencia) para que el
/// host aborte el arranque — un seed roto debe ser visible, no silencioso.
pub async fn apply(db: &dyn DatabaseAdapter, sql: &str, hub_id: &str) -> Result<usize> {
    let mut params = erplora_db::Params::new();
    params.insert("hub_id".into(), serde_json::json!(hub_id));
    let stmts = split_statements(sql);
    let mut applied = 0usize;
    for (i, stmt) in stmts.iter().enumerate() {
        // hub#840: a seed written before `hub_user.hub_id` existed gets this hub put on it here.
        let stmt = &scope_insert_to_hub(stmt);
        db.execute(stmt, &params).await.map_err(|e| {
            RuntimeError::Other(format!(
                "seed: fallo en la sentencia #{} de {}: {e}\n  SQL: {stmt}",
                i + 1,
                stmts.len()
            ))
        })?;
        applied += 1;
    }
    Ok(applied)
}

/// Aplica el bloque `seed` de un MÓDULO (ADR-0147): datos de referencia que todo hub necesita y
/// que el usuario no puede aportar — unidades de medida, categorías fiscales.
///
/// Se diferencia de [`apply`] en que **liga parámetros**: la semilla de un módulo se escribe por
/// hub (`:hub_id`) y con auditoría (`:now`, `:current_user_id`), así que no puede ir por
/// `execute_batch`. La idempotencia la garantiza el propio SQL (`WHERE NOT EXISTS` por la clave
/// natural), no este código: reinstalar un módulo vuelve a ejecutarlo y no debe duplicar.
///
/// Se aplica DESPUÉS de las migraciones — la semilla escribe en tablas que acaban de crearse.
/// Con quién firma el instalador TODA fila que siembra un módulo (`created_by`).
///
/// Es el marcador que separa lo que plantamos nosotros de lo que crea una persona, y es UNIFORME
/// para los 27 módulos. Lo leen [`crate::export::is_module_seeded`] (para que lo sembrado no viaje
/// en un bundle) y el import (para que el marcador ceda cuando llegan los datos del negocio,
/// hub#1535), así que vive junto a quien lo escribe: si esto cambiara, las tres puntas cambian a la vez.
pub(crate) const SEEDED_BY: &str = "system";

pub async fn apply_module_seed(
    db: &dyn DatabaseAdapter,
    sql: &str,
    hub_id: &str,
    now: &str,
) -> Result<usize> {
    let mut params = erplora_db::Params::new();
    params.insert("hub_id".into(), serde_json::json!(hub_id));
    params.insert("now".into(), serde_json::json!(now));
    // La semilla la escribe el sistema, no un usuario: la auditoría queda a nombre del instalador.
    params.insert("current_user_id".into(), serde_json::json!(SEEDED_BY));

    let stmts = split_statements(sql);
    let mut applied = 0usize;
    for (i, stmt) in stmts.iter().enumerate() {
        // Same rule, same reason (hub#840): a module seed touching an identity table is rare, but
        // when it does it must scope the row to this hub like every other door does.
        let stmt = &scope_insert_to_hub(stmt);
        db.execute(stmt, &params).await.map_err(|e| {
            RuntimeError::Other(format!(
                "seed de módulo: fallo en la sentencia #{} de {}: {e}\n  SQL: {stmt}",
                i + 1,
                stmts.len()
            ))
        })?;
        applied += 1;
    }
    Ok(applied)
}

/// The identity tables a seed may write whose rows belong to ONE hub and carry no other clue about
/// which. Deliberately the same allow-list `import::rewrite_insert` uses (hub#497), because it is
/// the same rule about the same rows — see [`scope_insert_to_hub`].
///
/// Short and blunt on purpose: a module's own table is none of this function's business. Its seed
/// is written against a schema the runtime does not know, and adding a `hub_id` column to a table
/// that may not have one would turn a working seed into a syntax error. Module seeds say `:hub_id`
/// themselves ([`apply_module_seed`]), which is the contract for everything outside this list.
const HUB_SCOPED_IDENTITY_TABLES: [&str; 2] = ["hub_user", "hub_session"];

/// **Puts THIS hub on a seeded identity row whose author never named one** (hub#840).
///
/// Seeds are written by somebody who is not this hub: the SaaS builds one per demo deployment, a
/// blueprint ships one per sector. They were written when `hub_user` had no `hub_id`, and system
/// migration v42 (hub#497) made that column `NOT NULL`. Since [`apply`]'s failure ABORTS BOOT, such
/// a seed does not merely lose the hub its staff — the hub does not come up.
///
/// hub#497 already answered this exact question for the IMPORT path, and answered it the same way:
/// the runtime injects the destination hub when the incoming SQL does not name it
/// (`import::rewrite_insert`, whose `hub_user | hub_session` allow-list this one mirrors). What it
/// missed is that import is not the only door SQL written elsewhere comes through — `HUB_SEED_SQL`
/// is the other, and it is the one the live demo uses. **The two blocks want to be one function**;
/// they are not yet only because `import.rs` is held by another change in flight (see the PR).
///
/// Three rules, and the third is the one that keeps this safe:
///
/// 1. Only the tables in [`HUB_SCOPED_IDENTITY_TABLES`].
/// 2. Only when the statement's explicit column list does NOT already name `hub_id` — what the
///    author wrote always wins, so a bundle restored into its own hub keeps the hub it names.
/// 3. **Anything it cannot read confidently is returned untouched.** A wrong guess would corrupt a
///    seed silently; leaving it alone yields the loud not-null error an operator can act on.
///
/// The injected value is the bind `:hub_id`, so this is only correct on a path that binds it — both
/// callers in this module do.
fn scope_insert_to_hub(stmt: &str) -> String {
    let Some((table, after_table)) = parse_insert_target(stmt) else {
        return stmt.to_string();
    };
    if !HUB_SCOPED_IDENTITY_TABLES.contains(&table.as_str()) {
        return stmt.to_string();
    }
    // An explicit column list is required: there is no list to add a column to otherwise, and
    // positional `INSERT … SELECT` would need to know the table's real column order.
    let rest = &stmt[after_table..];
    let offset = rest.len() - rest.trim_start().len();
    if !rest[offset..].starts_with('(') {
        return stmt.to_string();
    }
    let open = after_table + offset;
    let Some(close) = matching_paren(stmt, open) else {
        return stmt.to_string();
    };
    if split_top_level(&stmt[open + 1..close])
        .iter()
        .any(|c| c.trim().trim_matches('"').eq_ignore_ascii_case("hub_id"))
    {
        return stmt.to_string(); // Rule 2: the file already said which hub.
    }
    let Some(values) = scope_value_lists(&stmt[close + 1..]) else {
        return stmt.to_string(); // Rule 3: unreadable → untouched.
    };
    format!("{}, hub_id){}", &stmt[..close], values)
}

/// `INSERT INTO <table>` → the table name and where it ends. `None` for anything that is not an
/// insert, which is most of a seed.
fn parse_insert_target(stmt: &str) -> Option<(String, usize)> {
    let mut cursor = skip_ws(stmt, 0);
    cursor = expect_keyword(stmt, cursor, "INSERT")?;
    cursor = skip_ws(stmt, cursor);
    cursor = expect_keyword(stmt, cursor, "INTO")?;
    cursor = skip_ws(stmt, cursor);
    let start = cursor;
    let bytes = stmt.as_bytes();
    while cursor < bytes.len()
        && (bytes[cursor].is_ascii_alphanumeric() || bytes[cursor] == b'_' || bytes[cursor] == b'"')
    {
        cursor += 1;
    }
    if cursor == start {
        return None;
    }
    Some((
        stmt[start..cursor].trim_matches('"').to_ascii_lowercase(),
        cursor,
    ))
}

/// Adds `, :hub_id` to the VALUES of an insert whose column list just grew by one.
///
/// Handles the two shapes a seed is written in — `SELECT …` (with or without a guard) and
/// `VALUES (…), (…)` — and returns `None` for anything else, which is rule 3.
fn scope_value_lists(after_columns: &str) -> Option<String> {
    let start = skip_ws(after_columns, 0);
    if let Some(cursor) = expect_keyword(after_columns, start, "SELECT") {
        // The select list ends at the top-level guard (`WHERE NOT EXISTS (…)`, the idiom every
        // idempotent seed uses) or, without one, at the end of the statement. The inner `WHERE` of
        // the guard sits inside parentheses, so a depth-aware scan never mistakes it for this one.
        let end = find_top_level(after_columns, cursor, "WHERE")
            .unwrap_or_else(|| end_of_statement(after_columns));
        // The trailing space matters: the guard follows immediately, and `:hub_idWHERE` is a
        // syntax error rather than a bound parameter.
        return Some(format!(
            "{}, :hub_id {}",
            &after_columns[..end],
            &after_columns[end..]
        ));
    }
    if let Some(cursor) = expect_keyword(after_columns, start, "VALUES") {
        let mut tuples = Vec::new();
        let mut at = skip_ws(after_columns, cursor);
        while after_columns[at..].starts_with('(') {
            let close = matching_paren(after_columns, at)?;
            tuples.push(close);
            at = skip_ws(after_columns, close + 1);
            if !after_columns[at..].starts_with(',') {
                break;
            }
            at = skip_ws(after_columns, at + 1);
        }
        if tuples.is_empty() {
            return None;
        }
        // Right to left, so an earlier insertion never shifts a later index.
        let mut out = after_columns.to_string();
        for close in tuples.into_iter().rev() {
            out.insert_str(close, ", :hub_id");
        }
        return Some(out);
    }
    None
}

fn skip_ws(s: &str, from: usize) -> usize {
    let bytes = s.as_bytes();
    let mut i = from;
    while i < bytes.len() && bytes[i].is_ascii_whitespace() {
        i += 1;
    }
    i
}

/// Consumes `keyword` at `from`, case-insensitively, only when it is a whole word.
fn expect_keyword(s: &str, from: usize, keyword: &str) -> Option<usize> {
    let end = from + keyword.len();
    if end > s.len() || !s[from..end].eq_ignore_ascii_case(keyword) {
        return None;
    }
    match s.as_bytes().get(end) {
        Some(b) if b.is_ascii_alphanumeric() || *b == b'_' => None,
        _ => Some(end),
    }
}

/// Index of `keyword` at parenthesis depth 0 and outside any string literal, searching from `from`.
fn find_top_level(s: &str, from: usize, keyword: &str) -> Option<usize> {
    let bytes = s.as_bytes();
    let mut depth = 0i32;
    let mut i = from;
    while i < bytes.len() {
        match bytes[i] {
            b'\'' => i = skip_string_literal(s, i),
            b'(' => {
                depth += 1;
                i += 1;
            }
            b')' => {
                depth -= 1;
                i += 1;
            }
            _ => {
                if depth == 0 && expect_keyword(s, i, keyword).is_some() {
                    return Some(i);
                }
                i += 1;
            }
        }
    }
    None
}

/// Where the payload of a statement ends: before its trailing `;` and any whitespace after it.
fn end_of_statement(s: &str) -> usize {
    s.trim_end().strip_suffix(';').unwrap_or(s.trim_end()).len()
}

/// Index just past the closing quote of the literal starting at `from`, honouring `''` escaping.
fn skip_string_literal(s: &str, from: usize) -> usize {
    let bytes = s.as_bytes();
    let mut i = from + 1;
    while i < bytes.len() {
        if bytes[i] == b'\'' {
            if bytes.get(i + 1) == Some(&b'\'') {
                i += 2; // An escaped quote inside the literal, not its end.
                continue;
            }
            return i + 1;
        }
        i += 1;
    }
    i
}

/// The `)` matching the `(` at `open`, ignoring parentheses inside string literals.
fn matching_paren(s: &str, open: usize) -> Option<usize> {
    let bytes = s.as_bytes();
    let mut depth = 0i32;
    let mut i = open;
    while i < bytes.len() {
        match bytes[i] {
            b'\'' => {
                i = skip_string_literal(s, i);
                continue;
            }
            b'(' => depth += 1,
            b')' => {
                depth -= 1;
                if depth == 0 {
                    return Some(i);
                }
            }
            _ => {}
        }
        i += 1;
    }
    None
}

/// Splits on commas at depth 0 and outside string literals (a column list).
fn split_top_level(s: &str) -> Vec<String> {
    let bytes = s.as_bytes();
    let mut parts = Vec::new();
    let mut depth = 0i32;
    let mut start = 0usize;
    let mut i = 0usize;
    while i < bytes.len() {
        match bytes[i] {
            b'\'' => {
                i = skip_string_literal(s, i);
                continue;
            }
            b'(' => depth += 1,
            b')' => depth -= 1,
            b',' if depth == 0 => {
                parts.push(s[start..i].to_string());
                start = i + 1;
            }
            _ => {}
        }
        i += 1;
    }
    parts.push(s[start..].to_string());
    parts
}

/// Parte un batch SQL en sentencias individuales (separa por `;`, descarta vacías). A diferencia de
/// [`crate::system_migrations`] (SQL horneado sin comentarios), un fichero de seed lo escribe un
/// humano y suele llevar comentarios `--`, que pueden contener `;` y romperían el split ingenuo;
/// por eso primero se **descartan las líneas de comentario `--`**. El seed es DDL/DML simple sin
/// literales con `;` embebidos. Cada sentencia se ejecuta por separado, ligando `:hub_id`.
pub(crate) fn split_statements(sql: &str) -> Vec<String> {
    let without_comments: String = sql
        .lines()
        .filter(|line| !line.trim_start().starts_with("--"))
        .collect::<Vec<_>>()
        .join("\n");
    without_comments
        .split(';')
        .map(|s| s.trim())
        .filter(|s| !s.is_empty())
        .map(|s| format!("{s};"))
        .collect()
}

/// **Las CLAVES NATURALES que el seed de un módulo declara sobre sus propias tablas** (hub#842).
///
/// El seed de un módulo es DML idempotente por contrato, y su idempotencia la escribe como
/// `WHERE NOT EXISTS (SELECT 1 FROM <tabla> WHERE hub_id = :hub_id AND type = 'cash' AND is_deleted = 0)`.
/// Esa guarda **es** la declaración de qué fila considera «la misma» el módulo: `sales` lo dice con
/// todas las letras en su comentario —«si el dueño ya creó o renombró un método de ese tipo, se
/// respeta el suyo»— y por eso reinstalar no duplica.
///
/// El import necesita exactamente esa clave y **no la puede sacar de ningún otro sitio**. El
/// catálogo ([`crate::export::natural_keys`], hub#753) solo ve índices ÚNICOS, y `(hub_id, type)`
/// no puede ser uno: `type` es una CLASE DE COMPORTAMIENTO —`cash` abre el cajón y pide entregado,
/// `card` no—, no una identidad, así que un hub puede tener `Visa` y `Amex` a la vez. La clave
/// existe en un solo sitio del sistema: aquí. (El manifest tampoco sirve como sitio: obligaría a
/// republicar el módulo, y las cuatro plantillas publicadas y los hubs vivos duplican **hoy**.)
///
/// Se lee del MISMO texto que se va a ejecutar, en [`crate::installer::register_module`], así que
/// no puede desincronizarse de lo que el seed siembra de verdad.
///
/// **Fail-open, como todo el resto del camino**: una guarda que no case con la forma canónica se
/// descarta —no se traduce a medias— y su tabla se comporta como antes de hub#842. Dos descartes
/// concretos, y los dos importan:
///
/// * una guarda cuya única columna sea `hub_id` («siembra solo si la tabla está vacía») declararía
///   como clave «todo el hub», y saltaría la sección ENTERA de esa tabla;
/// * una guarda que mire una tabla distinta de la que inserta no habla de esta fila.
pub(crate) fn declared_natural_keys(
    sql: &str,
) -> std::collections::HashMap<String, Vec<crate::export::NaturalKey>> {
    let mut out: std::collections::HashMap<String, Vec<crate::export::NaturalKey>> =
        std::collections::HashMap::new();
    for stmt in split_statements(sql) {
        let Some((table, SeedGuard::Key(key))) = parse_seed_guard(&stmt) else {
            continue;
        };
        let keys = out.entry(table).or_default();
        // El seed planta una fila por sentencia y todas comparten la clave (cambia el VALOR, no la
        // columna): basta con quedarse una vez con cada juego de columnas.
        if !keys
            .iter()
            .any(|k: &crate::export::NaturalKey| k.cols == key.cols && k.predicate == key.predicate)
        {
            keys.push(key);
        }
    }
    out
}

/// Tablas que el seed de un módulo siembra como **marcador de posición de tabla entera**
/// (hub#1535): las que declaran [`SeedGuard::WholeTable`].
///
/// Es la lectura complementaria de [`declared_natural_keys`] sobre el MISMO texto, y por el mismo
/// motivo — la guarda con la que el seed se hace idempotente es la única declaración que existe de
/// lo que el módulo considera suyo. Aquí dice algo más fuerte que una clave: que esas filas son
/// nuestras solo mientras el negocio no haya puesto las suyas.
pub(crate) fn declared_placeholder_tables(sql: &str) -> Vec<String> {
    let mut out: Vec<String> = Vec::new();
    for stmt in split_statements(sql) {
        let Some((table, SeedGuard::WholeTable)) = parse_seed_guard(&stmt) else {
            continue;
        };
        if !out.contains(&table) {
            out.push(table);
        }
    }
    out
}

/// Lo que la guarda `WHERE NOT EXISTS` de una sentencia de seed declara sobre lo que planta.
///
/// Las dos formas son declaraciones distintas del módulo, y el import las necesita a las dos:
///
/// * [`SeedGuard::Key`] — «no plantes si ya existe LA MISMA fila»: el seed reparte filas de
///   REFERENCIA, una por hueco (`(hub_id, type)` en `sales`, `(hub_id, code)` en `inventory`,
///   `(hub_id, key)` en `taxes`). Es la clave de hub#842, y hace que la fila entrante equivalente
///   se salte.
/// * [`SeedGuard::WholeTable`] — «no plantes si el hub tiene YA algo aquí»: la guarda es
///   `WHERE hub_id = :hub_id` y nada más, así que el seed no reparte filas independientes: planta
///   UN objeto —la semana de apertura de `schedules`, siete filas que solo significan algo
///   juntas— y solo mientras el hub esté virgen. Eso lo convierte en un MARCADOR DE POSICIÓN, no
///   en datos: cuando llegan los de verdad, cede (hub#1535).
#[derive(Debug, Clone)]
enum SeedGuard {
    Key(crate::export::NaturalKey),
    WholeTable,
}

/// Traduce la guarda de UNA sentencia de seed a la clave natural que declara, o `None`.
///
/// Forma aceptada, que es la que escriben los tres seeds del repo:
/// `INSERT INTO <t> (…) SELECT … WHERE NOT EXISTS (SELECT 1 FROM <t> WHERE <cond> [AND <cond>]…)`,
/// donde cada `<cond>` es `columna = <lo que sea>` (el valor lo pondrá la fila del bundle, no el
/// seed) o `columna IS NULL`.
fn parse_seed_guard(stmt: &str) -> Option<(String, SeedGuard)> {
    let table = stmt
        .trim()
        .strip_prefix("INSERT INTO ")?
        .split_whitespace()
        .next()?;
    if !crate::export::safe_ident(table) {
        return None;
    }
    // El cuerpo del `NOT EXISTS`, hasta su paréntesis de cierre.
    let needle = format!("NOT EXISTS (SELECT 1 FROM {table} WHERE ");
    let at = stmt.find(&needle)?;
    let body_start = at + needle.len();
    let body_end = body_start + stmt[body_start..].find(')')?;
    let body = &stmt[body_start..body_end];
    // 🔴 El cierre se busca por el PRIMER `)`, así que un paréntesis o una comilla dentro de la
    // guarda la cortarían a media condición — y una clave con MENOS columnas es una guarda MÁS
    // PERMISIVA, que saltaría filas legítimas en silencio. Es la única dirección en la que
    // equivocarse sale caro, y no se intenta entender: la forma canónica no tiene ni una cosa ni
    // la otra, así que cualquiera de las dos descarta la clave entera.
    if body.contains('(') || body.matches('\'').count() % 2 != 0 {
        return None;
    }

    let mut cols: Vec<String> = Vec::new();
    let mut predicate: Vec<(String, Option<String>)> = Vec::new();
    for cond in body.split(" AND ") {
        let cond = cond.trim();
        if let Some(col) = cond.strip_suffix(" IS NULL") {
            let col = col.trim();
            if !crate::export::safe_ident(col) {
                return None;
            }
            predicate.push((col.to_string(), None));
            continue;
        }
        let (col, _value) = cond.split_once('=')?;
        let col = col.trim();
        if !crate::export::safe_ident(col) {
            return None;
        }
        cols.push(col.to_string());
    }
    // `hub_id` a secas no es una clave: es «esta tabla, en este hub». Como CLAVE saltaría TODA
    // fila entrante en cuanto el módulo hubiera sembrado una sola — por eso no lo es. Lo que sí
    // es, y hub#1535 necesita, es la otra mitad de la declaración: el módulo dice que siembra
    // esta tabla como UN objeto y solo cuando el hub no tiene nada suyo. Ver [`SeedGuard`].
    if cols == ["hub_id"] && predicate.is_empty() {
        return Some((table.to_string(), SeedGuard::WholeTable));
    }
    if cols.iter().all(|c| c == "hub_id") {
        return None;
    }
    Some((
        table.to_string(),
        SeedGuard::Key(crate::export::NaturalKey {
            cols,
            predicate,
            nulls_not_distinct: false,
            seeded_only: true,
        }),
    ))
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::identity;
    use erplora_db::testutil::fresh_db;

    /// SQL de seed del **demo** (el que el terraform pasa inline por `HUB_SEED_SQL`). Es el mismo
    /// contenido versionado en `crates/server/seeds/demo.sql`; aquí lo embebemos para que el test
    /// garantice que el hash del PIN y las columnas reales son correctos sin leer ficheros.
    const DEMO_SEED: &str = include_str!("../../server/seeds/demo.sql");

    /// **hub#840 — a seed written before the column existed still lands in THIS hub.**
    ///
    /// The exact shape every seed in the wild still carries: `INSERT INTO hub_user` with an
    /// explicit column list that predates `hub_id`. It is not a hypothetical — this is, verbatim
    /// modulo the hash, what `saas/…/hetzner/hub_demo_seed.sql` hands to `HUB_SEED_SQL` today and
    /// what the sector seeds carry for their cashiers
    /// (`crates/runtime/tests/fixtures/sector_pack_es/*/seed.sql`).
    ///
    /// Against the `NOT NULL` of system migration v42 (hub#497) this used to be a not-null
    /// violation, and [`apply`]'s failure ABORTS BOOT (`server/lib.rs`, `apply_seed(&seed_sql)?`):
    /// the hub did not merely lose its staff, it did not come up.
    const SEED_WITHOUT_HUB_ID: &str = "\
INSERT INTO hub_user (id, name, pin_hash, role, cloud_user_id, is_active, created_at)
SELECT 'user-seeded-cashier', 'Cajero 1', 'salt:hash', 'employee', NULL, 1, '2026-01-01T00:00:00+00:00'
WHERE NOT EXISTS (SELECT 1 FROM hub_user WHERE name = 'Cajero 1');";

    /// The runtime puts THIS hub on a seeded identity row the file did not scope (hub#840).
    ///
    /// Through [`crate::Runtime::apply_seed`] — the door the host really uses (`HUB_SEED_SQL`) —
    /// and against the real system schema, because the constraint being satisfied is the one
    /// `ensure_system_tables` installs. Asserting on a hand-made table would prove nothing.
    #[tokio::test]
    async fn a_seed_that_predates_hub_id_still_lands_in_this_hub() {
        let db = fresh_db().await;
        let runtime = crate::Runtime::new(Box::new(db));
        runtime.ensure_system_tables().await.unwrap();

        runtime
            .apply_seed(SEED_WITHOUT_HUB_ID)
            .await
            .expect("a seed written before the column existed must not abort the hub's boot");

        let row = runtime
            .db_for_test()
            .query(
                "SELECT hub_id FROM hub_user WHERE id = 'user-seeded-cashier'",
                &erplora_db::Params::new(),
            )
            .await
            .unwrap();
        assert_eq!(row.rows.len(), 1, "the seeded cashier exists: {row:?}");
        assert_eq!(
            row.rows[0]["hub_id"].as_str(),
            Some(crate::DEV_HUB_ID),
            "…and belongs to the hub being seeded, which is the only hub it could belong to"
        );
    }

    /// The rewrite is NOT «add hub_id to everything»: a seed that scopes its own row keeps what it
    /// wrote. Otherwise the runtime would be overwriting an author's explicit answer with a guess —
    /// and a bundle restored into its own hub names its `hub_id` on purpose.
    #[tokio::test]
    async fn a_seed_that_names_its_hub_is_left_alone() {
        let db = fresh_db().await;
        let runtime = crate::Runtime::new(Box::new(db));
        runtime.ensure_system_tables().await.unwrap();

        runtime
            .apply_seed(
                "INSERT INTO hub_user (id, hub_id, name, pin_hash, role, is_active, created_at)\n\
                 SELECT 'u-explicit', 'other-hub', 'Ana', 'salt:hash', 'employee', 1, '2026-01-01T00:00:00+00:00'\n\
                 WHERE NOT EXISTS (SELECT 1 FROM hub_user WHERE id = 'u-explicit');",
            )
            .await
            .expect("seed applies");

        let row = runtime
            .db_for_test()
            .query(
                "SELECT hub_id FROM hub_user WHERE id = 'u-explicit'",
                &erplora_db::Params::new(),
            )
            .await
            .unwrap();
        assert_eq!(
            row.rows[0]["hub_id"].as_str(),
            Some("other-hub"),
            "what the file says wins; the runtime only fills a hole"
        );
    }

    /// Only the tables whose rows ARE an identity in this hub. A seed writing its own module table
    /// is none of this function's business: guessing a `hub_id` column onto a table that may not
    /// have one would turn a working seed into a syntax error.
    #[test]
    fn only_the_identity_tables_are_rewritten() {
        let untouched = "INSERT INTO inventory_product (id, name) SELECT 'p1', 'Café';";
        assert_eq!(scope_insert_to_hub(untouched), untouched);
        assert!(
            scope_insert_to_hub("INSERT INTO hub_session (id, user_id) SELECT 's1', 'u1';")
                .contains(":hub_id")
        );
    }

    /// What it cannot parse, it does not touch. The failure mode of a wrong guess here is a
    /// corrupted seed applied in silence; the failure mode of leaving it alone is the loud not-null
    /// error the operator can read. Loud wins.
    #[test]
    fn an_insert_it_cannot_read_is_left_exactly_as_it_was() {
        for odd in [
            // No explicit column list: there is no list to add a column to.
            "INSERT INTO hub_user SELECT 'a', 'b';",
            // Unbalanced: not something to rewrite blind.
            "INSERT INTO hub_user (id, name SELECT 'a', 'b';",
        ] {
            assert_eq!(scope_insert_to_hub(odd), odd, "left alone: {odd}");
        }
    }

    #[tokio::test]
    async fn apply_runs_each_statement_and_is_idempotent() {
        let db = fresh_db().await;
        // Tres sentencias idempotentes (CREATE IF NOT EXISTS + dos inserts guardados).
        let sql = "\
CREATE TABLE IF NOT EXISTS t (id TEXT PRIMARY KEY, v TEXT);\
INSERT INTO t (id, v) SELECT 'a', '1' WHERE NOT EXISTS (SELECT 1 FROM t WHERE id = 'a');\
INSERT INTO t (id, v) SELECT 'b', '2' WHERE NOT EXISTS (SELECT 1 FROM t WHERE id = 'b');";
        let n = apply(&db, sql, "hub-test").await.unwrap();
        assert_eq!(n, 3, "tres sentencias aplicadas");

        // Re-aplicar no duplica ni falla (idempotente por el propio SQL).
        apply(&db, sql, "hub-test").await.unwrap();
        let res = db
            .query("SELECT COUNT(*) AS c FROM t", &erplora_db::Params::new())
            .await
            .unwrap();
        assert_eq!(res.rows[0]["c"].as_i64(), Some(2), "no se duplican filas");
    }

    #[test]
    fn split_statements_drops_comment_lines() {
        let sql = "-- a comment with a ; semicolon inside\n\
                   INSERT INTO t VALUES (1);\n\
                   -- another comment;\n\
                   INSERT INTO t VALUES (2);";
        let stmts = split_statements(sql);
        assert_eq!(
            stmts.len(),
            2,
            "solo las dos sentencias, no los comentarios: {stmts:?}"
        );
        assert!(stmts[0].starts_with("INSERT INTO t VALUES (1)"));
        assert!(stmts[1].starts_with("INSERT INTO t VALUES (2)"));
    }

    #[tokio::test]
    async fn apply_reports_clear_error_on_bad_statement() {
        let db = fresh_db().await;
        let err = apply(&db, "SELECT * FROM no_such_table;", "hub-test")
            .await
            .unwrap_err();
        assert!(
            format!("{err}").contains("seed:"),
            "error de seed claro: {err}"
        );
    }

    /// GUARANTEE of the demo seed (hub#36): applying `demo.sql` on a real Runtime leaves a
    /// "Demo" user whose PIN verifies. If the PIN hash or the column names were wrong, this test
    /// FAILS — it is the safety net hub#36 asked for.
    ///
    /// Regression for ERPlora/hub#1929: the demo asks for SIX digits like every hub provisioned
    /// today (ADR-0372), and its PIN is always `000000`. The pinpad submits at exactly
    /// `pin_length` digits (hub#1037), so the seeded PIN and the seeded length have to agree: a
    /// four-digit PIN behind a six-digit keypad can never be typed, and the other way round the
    /// keypad fires before the PIN is complete. `000000` is guessable on purpose — the
    /// `clean_pin` rules are for PINs a person picks; this one is public, shown on the demo page,
    /// and enters through SQL.
    ///
    /// It no longer seeds a trusted device (hub#630): the browser mints the `device_id`, so the
    /// row that used to be here could not be presented by anyone. The login's trust-on-first-use
    /// opens the door now, and **it needs the hub to know no device yet** — seeding one would
    /// disable it. That is why this test checks the opposite of what it used to: that the seed
    /// leaves the list EMPTY.
    #[tokio::test]
    async fn demo_seed_enables_demo_pin_login_and_trusted_device() {
        const DEMO_PIN: &str = "000000";

        let db = fresh_db().await;
        let runtime = crate::Runtime::new(Box::new(db));
        // Same order as the server: system tables first, then the seed.
        runtime.ensure_system_tables().await.unwrap();
        // Through `Runtime::apply_seed`, which is how the host calls it (`HUB_SEED_SQL`,
        // server/lib.rs) and who sets the deployment's `hub_id`: calling `apply` directly would
        // leave untested exactly the point where it is decided which hub the seed belongs to
        // (hub#489).
        let n = runtime.apply_seed(DEMO_SEED).await.unwrap();
        assert!(n >= 1, "the demo seed applies at least the user, was {n}");

        // hub#1929: the keypad the demo shows is six digits long, and the PIN fills it exactly.
        let pin_length = runtime.pin_length().await.unwrap();
        assert_eq!(pin_length, 6, "the demo asks for six digits (hub#1929)");
        assert_eq!(
            DEMO_PIN.len() as i64,
            pin_length,
            "the demo PIN must fill the keypad exactly: the pinpad submits at `pin_length` digits"
        );

        // The "Demo" user's PIN verifies (validates the hash format).
        let user = runtime.verify_pin("Demo", DEMO_PIN).await.unwrap();
        let user = user.expect("Demo verifies with PIN 000000");
        assert_eq!(user.name, "Demo");
        assert!(user.is_active);
        // Role with full permissions (admin/owner): the seed sets it; we check it is NOT empty.
        assert!(!user.role.is_empty(), "the demo user has a role");
        // A wrong PIN does NOT verify — the old four-digit one included (hub#1929).
        assert!(runtime.verify_pin("Demo", "0000").await.unwrap().is_none());
        assert!(runtime.verify_pin("Demo", "111111").await.unwrap().is_none());

        // 🔴 The seed leaves NO trusted device, and that is the contract now (hub#630): the
        // login's trust-on-first-use only adopts the first visitor if the hub knows none yet. A
        // row seeded here —like the `demo-trusted-device` there used to be— left the demo without
        // a door: nobody could present that id and the adoption never got to act.
        assert!(
            runtime.list_devices().await.unwrap().is_empty(),
            "the seed must leave the device list empty or first-use adopts nobody"
        );

        // Re-applying the seed is idempotent (no second "Demo", no failure) and never overwrites
        // the hub's own answer: the seed runs at every boot, and a length the admin changed in
        // Ajustes outranks the one the demo was born with — same `WHERE NOT EXISTS` contract as
        // the SaaS's `pin_length` seed.
        runtime.set_pin_length(4).await.unwrap();
        runtime.apply_seed(DEMO_SEED).await.unwrap();
        let res = identity_count_demo(&runtime).await;
        assert_eq!(res, 1, "the seed does not duplicate the Demo user when re-applied");
        assert_eq!(
            runtime.pin_length().await.unwrap(),
            4,
            "re-applying the seed must not overwrite the hub's PIN length"
        );
    }

    async fn identity_count_demo(runtime: &crate::Runtime) -> i64 {
        let mut p = erplora_db::Params::new();
        p.insert("name".into(), serde_json::json!("Demo"));
        let res = runtime
            .db_for_test()
            .query("SELECT COUNT(*) AS c FROM hub_user WHERE name = :name", &p)
            .await
            .unwrap();
        res.rows[0]["c"].as_i64().unwrap_or_default()
    }

    // Sanity: el módulo de identidad expone verify_pin (compila el import).
    #[allow(unused_imports)]
    use identity::HubUser as _SeedHubUser;

    // ── hub#842: la clave natural que declara el seed ────────────────────────────────────────

    /// El seed REAL de `sales`, verbatim (dos sentencias, misma clave `(hub_id, type, is_deleted)`).
    const SALES_SEED: &str = "\
-- comentario con ; dentro
INSERT INTO sales_payment_method (id, hub_id, name, type, is_deleted)
SELECT (:hub_id || '|paymethod|cash'), :hub_id, 'Cash', 'cash', 0
WHERE NOT EXISTS (SELECT 1 FROM sales_payment_method WHERE hub_id = :hub_id AND type = 'cash' AND is_deleted = 0);

INSERT INTO sales_payment_method (id, hub_id, name, type, is_deleted)
SELECT (:hub_id || '|paymethod|card'), :hub_id, 'Card', 'card', 0
WHERE NOT EXISTS (SELECT 1 FROM sales_payment_method WHERE hub_id = :hub_id AND type = 'card' AND is_deleted = 0);";

    #[test]
    fn el_seed_declara_su_clave_natural_y_solo_una_vez_por_juego_de_columnas() {
        let keys = declared_natural_keys(SALES_SEED);
        let payment = keys.get("sales_payment_method").expect("la tabla del seed");
        assert_eq!(
            payment.len(),
            1,
            "dos sentencias, una sola clave: {payment:?}"
        );
        assert_eq!(payment[0].cols, vec!["hub_id", "type", "is_deleted"]);
        assert!(
            payment[0].seeded_only,
            "una clave de seed solo pregunta por lo que sembró el módulo"
        );
        assert!(payment[0].predicate.is_empty());
    }

    /// `col IS NULL` no es un valor a comparar contra la fila entrante: es una condición que la
    /// fila debe cumplir para caer en la clave (la forma de `taxes_rule`).
    #[test]
    fn is_null_en_la_guarda_va_al_predicado_no_a_las_columnas() {
        let sql = "INSERT INTO taxes_rule (id, hub_id) SELECT 'x', :hub_id \
                   WHERE NOT EXISTS (SELECT 1 FROM taxes_rule WHERE hub_id = :hub_id \
                   AND country_code = 'ES' AND parent_id IS NULL);";
        let keys = declared_natural_keys(sql);
        let rule = &keys["taxes_rule"][0];
        assert_eq!(rule.cols, vec!["hub_id", "country_code"]);
        assert_eq!(rule.predicate, vec![("parent_id".to_string(), None)]);
    }

    /// «Siembra solo si la tabla está vacía» NO es una clave natural: tomada por tal, saltaría la
    /// sección entera de esa tabla en cuanto el módulo hubiera sembrado una fila.
    #[test]
    fn una_guarda_que_solo_mira_el_hub_no_declara_nada() {
        let sql = "INSERT INTO t (id, hub_id) SELECT 'x', :hub_id \
                   WHERE NOT EXISTS (SELECT 1 FROM t WHERE hub_id = :hub_id);";
        assert!(
            declared_natural_keys(sql).is_empty(),
            "«toda la tabla» no es una clave"
        );
    }

    /// …pero SÍ declara la otra cosa (hub#1535): que lo sembrado en esa tabla es un marcador de
    /// posición. Es la misma guarda leída para lo que de verdad dice.
    #[test]
    fn una_guarda_que_solo_mira_el_hub_declara_un_marcador_de_tabla_entera() {
        let sql = "INSERT INTO t (id, hub_id) SELECT 'x', :hub_id \
                   WHERE NOT EXISTS (SELECT 1 FROM t WHERE hub_id = :hub_id);";
        assert_eq!(declared_placeholder_tables(sql), vec!["t".to_string()]);
    }

    /// Y una guarda POR FILA no lo es: son datos de referencia (`inventory_unit`, `taxes_category`)
    /// que otros módulos resuelven por clave. Retirarlos sería mucho peor que el duplicado que
    /// hub#1535 arregla, así que las dos lecturas de la guarda son excluyentes.
    #[test]
    fn una_guarda_por_fila_no_declara_marcador() {
        let sql = "INSERT INTO t (id, hub_id, code) SELECT 'x', :hub_id, 'ud' \
                   WHERE NOT EXISTS (SELECT 1 FROM t WHERE hub_id = :hub_id AND code = 'ud');";
        assert!(
            declared_placeholder_tables(sql).is_empty(),
            "una clave por fila describe datos de referencia, no un marcador"
        );
        assert_eq!(
            declared_natural_keys(sql)["t"][0].cols,
            vec!["hub_id", "code"]
        );
    }

    /// El marcador se declara una vez por tabla aunque el seed la siembre en varias sentencias.
    #[test]
    fn el_marcador_no_se_repite_por_tabla() {
        let sql = "INSERT INTO t (id, hub_id) SELECT 'x', :hub_id \
                   WHERE NOT EXISTS (SELECT 1 FROM t WHERE hub_id = :hub_id);\
                   INSERT INTO t (id, hub_id) SELECT 'y', :hub_id \
                   WHERE NOT EXISTS (SELECT 1 FROM t WHERE hub_id = :hub_id);";
        assert_eq!(declared_placeholder_tables(sql), vec!["t".to_string()]);
    }

    /// Una guarda que además de `hub_id` mira otra cosa NO se lee como tabla entera: en la duda se
    /// deja como estaba (fail-open, igual que el resto de este parser).
    #[test]
    fn una_guarda_con_hub_id_y_algo_mas_no_es_marcador_de_tabla_entera() {
        let sql = "INSERT INTO t (id, hub_id) SELECT 'x', :hub_id \
                   WHERE NOT EXISTS (SELECT 1 FROM t WHERE hub_id = :hub_id AND parent_id IS NULL);";
        assert!(declared_placeholder_tables(sql).is_empty());
    }

    /// Las guardas que el parser descarta por ambiguas tampoco declaran marcador: un `)` dentro del
    /// cuerpo significa que no vimos la guarda entera, y retirar filas por una lectura a medias es
    /// exactamente lo que no se puede hacer.
    #[test]
    fn una_guarda_ambigua_no_declara_marcador() {
        for sql in [
            "INSERT INTO t (id, hub_id) SELECT 'x', :hub_id \
             WHERE NOT EXISTS (SELECT 1 FROM t WHERE hub_id = upper(:hub_id));",
            "INSERT INTO t (id, hub_id) SELECT 'x', :hub_id \
             WHERE NOT EXISTS (SELECT 1 FROM b WHERE hub_id = :hub_id);",
            "INSERT INTO t (id, hub_id) VALUES ('x', :hub_id);",
        ] {
            assert!(
                declared_placeholder_tables(sql).is_empty(),
                "guarda ambigua leída como marcador: {sql}"
            );
        }
    }

    /// 🔴 The shape `schedules` actually ships (hub#1535), copied VERBATIM from
    /// `ERPlora/schedules@8c0c282e` (`seed/install.postgres.sql`, origin/main on 2026-09-05), not
    /// read from the shared checkout: the version of this test that read the checkout printed
    /// `SKIP` and went green without proving anything, because that checkout has no `seed/`.
    ///
    /// What the fixtures of the integration test do NOT reproduce and this one does: a header of
    /// `--` lines that quote the guard itself, a multi-line `INSERT`, and `--` comments TRAILING
    /// each `VALUES` tuple. If the parser ever trips on any of those, the fix silently stops
    /// applying to the one module that motivated it — and the week duplicates again.
    #[test]
    fn the_seed_shape_schedules_ships_declares_its_week_as_a_placeholder() {
        let sql = r#"-- Canonical seed of the `schedules` module (ADR-0147, schedules#36): the DEFAULT OPENING WEEK a
-- hub has the moment the module is installed. Per-hub idempotent DML, applied by the installer
-- after migrating with :hub_id/:now/:current_user_id injected (crates/runtime/src/seed.rs).
--
-- WHY A HUB IS NEVER LEFT WITHOUT HOURS. ADR-0392 decision 4 keeps `no_hours` as a verdict of its
-- own: with no rule for the day the business is NOT declared open, and the consumer may offer
-- «set your opening hours» rather than paint a closed door. That is still true — what changes
-- here is that the state stops being REACHABLE. `appointments` (its booking door, #102/#105) has
-- to permit everything while the hub has not one weekly row, because refusing there would turn
-- «I have not set my hours yet» into «I cannot take bookings» — an outage, not a guard. A door
-- that cannot refuse is not a door, so the hours have to exist from minute one.
--
-- ⚠️ ALL SEVEN DAYS, weekend included. `no_hours` is answered PER DAY, not per hub: seeding only
-- Monday–Friday would leave Saturday and Sunday still answering «nothing configured», and the
-- consumer's fallback would stay alive for two days a week. The weekend is seeded as explicit
-- CLOSED rows, which read as `closed_today`.
--
-- THE WEEK ITSELF IS THE MARKET'S, NOT OURS (skill `market-decision`, 10 references in the issue).
-- Every product that ships a default calendar ships the same shape — Monday–Friday working,
-- weekend non-working, one continuous daytime window: Odoo's «Standard 40 hours/week», Google
-- Calendar's pre-checked Mon–Fri 9–17, Microsoft Bookings' 8–17, Business Central's base calendar
-- («a base calendar would typically list all Saturdays as non-working days»). The close time is
-- the hospitality end of that range: Lightspeed Reservations defaults to 09:00–19:00, and the
-- cost of a default is asymmetric — too NARROW refuses bookings the business could have served,
-- too wide only shows an hour it will correct. 09:00–18:00 sits between the office default and
-- the hospitality one. No lunch break: only Odoo splits its default, and a siesta the business
-- does not take is an invented refusal in the middle of the day (a break is simply the gap
-- between two intervals since schedules#8, so the owner adds one by splitting the row).
--
-- IT IS A STARTING POINT, NOT A CONSTANT OF OURS. The hours are a fact about the business, so the
-- Hours screen flags the week as unconfirmed until somebody saves it (`created_by` = 'system' is
-- what the installer stamps, and what tells the two apart).
--
-- 🔴 THE GUARD IS THE WHOLE TABLE, ON PURPOSE. `WHERE NOT EXISTS (… WHERE hub_id = :hub_id)` and
-- nothing else: the seed runs again on EVERY update of the module (`register_manifest` re-applies
-- it), so a per-day guard would keep planting the days a live hub had deliberately left alone —
-- a salon that only ever set Monday would wake up with six days it never wrote. It does not
-- filter `is_deleted` either: rows are soft-deleted here, so a hub that cleared its week has
-- still TOUCHED its hours and the seed must not put one back. One statement, not seven, because
-- the guard sees the rows the previous statement wrote: seven guarded INSERTs would plant Monday
-- and skip the rest. The runtime reads this guard as «this table, in this hub», declares NO
-- natural key from it (`parse_seed_guard` returns none when the only column is `hub_id`) and that
-- is correct — the week is one object, not seven independent reference rows.
INSERT INTO schedules_business_hours
  (id, hub_id, day_of_week, position, open_time, close_time, is_closed, break_start, break_end,
   is_deleted, created_by, created_at, updated_by, updated_at)
SELECT (:hub_id || '|schedhours|' || d.day_of_week), :hub_id, d.day_of_week, 0,
       d.open_time, d.close_time, d.is_closed, NULL, NULL,
       0, :current_user_id, :now, :current_user_id, :now
FROM (VALUES
    (0, '09:00', '18:00', 0),   -- Monday
    (1, '09:00', '18:00', 0),   -- Tuesday
    (2, '09:00', '18:00', 0),   -- Wednesday
    (3, '09:00', '18:00', 0),   -- Thursday
    (4, '09:00', '18:00', 0),   -- Friday
    (5, '00:00', '00:00', 1),   -- Saturday — closed
    (6, '00:00', '00:00', 1)    -- Sunday — closed
  ) AS d(day_of_week, open_time, close_time, is_closed)
WHERE NOT EXISTS (SELECT 1 FROM schedules_business_hours WHERE hub_id = :hub_id);"#;
        assert_eq!(
            declared_placeholder_tables(sql),
            vec!["schedules_business_hours".to_string()],
            "the real seed guards the WHOLE table, so it declares a placeholder"
        );
        assert!(
            !declared_natural_keys(sql).contains_key("schedules_business_hours"),
            "and declares NO natural key: as a key it would make the import skip the real hours"
        );
    }

    /// Una guarda que pregunta por OTRA tabla no habla de la fila que se inserta.
    #[test]
    fn una_guarda_sobre_otra_tabla_se_descarta() {
        let sql = "INSERT INTO a (id, hub_id) SELECT 'x', :hub_id \
                   WHERE NOT EXISTS (SELECT 1 FROM b WHERE hub_id = :hub_id AND code = 'k');";
        assert!(declared_natural_keys(sql).is_empty());
    }

    /// 🔴 El cierre del `NOT EXISTS` se busca por el primer `)`, así que un paréntesis DENTRO de la
    /// guarda la cortaría a media condición — y la clave saldría con **menos** columnas, es decir
    /// **más permisiva**: saltaría filas que no debía. Es la única dirección en la que este parser
    /// puede equivocarse de forma cara, así que no se intenta entender: se descarta.
    #[test]
    fn una_guarda_con_parentesis_dentro_se_descarta_en_vez_de_cortarse() {
        let sql = "INSERT INTO t (id, hub_id) SELECT 'x', :hub_id \
                   WHERE NOT EXISTS (SELECT 1 FROM t WHERE hub_id = :hub_id \
                   AND code = upper('a') AND is_deleted = 0);";
        assert!(
            declared_natural_keys(sql).is_empty(),
            "cortada por el primer `)`, la clave saldría sin `is_deleted` y saltaría filas de más"
        );
    }

    /// Lo mismo con un literal que se coma el `)` o el ` AND `: comillas descompensadas dentro del
    /// cuerpo significan que el troceo no vio la guarda entera.
    #[test]
    fn una_guarda_con_comillas_descompensadas_se_descarta() {
        let sql = "INSERT INTO t (id, hub_id) SELECT 'x', :hub_id \
                   WHERE NOT EXISTS (SELECT 1 FROM t WHERE hub_id = :hub_id \
                   AND note = 'cierra aqui ) y sigue' AND is_deleted = 0);";
        assert!(
            declared_natural_keys(sql).is_empty(),
            "el `)` dentro del literal corta el cuerpo: la clave saldría incompleta"
        );
    }

    /// Un seed sin guarda (o con una que no case con la forma canónica) deja su tabla exactamente
    /// como estaba antes de hub#842.
    #[test]
    fn un_seed_sin_guarda_no_declara_clave() {
        let sql = "INSERT INTO t (id, hub_id) VALUES ('x', :hub_id);";
        assert!(declared_natural_keys(sql).is_empty());
    }

    /// El seed REAL del módulo `sales`, leído del repo hermano: lo que este arreglo promete es
    /// sobre ESE fichero, no sobre una copia parafraseada aquí.
    #[test]
    fn el_seed_real_de_sales_declara_hub_id_y_type() {
        let path = crate::e2e_support::modules_root().join("sales/seed/install.postgres.sql");
        let Ok(sql) = std::fs::read_to_string(&path) else {
            println!("⏭  SKIP: sin modules-workspace en {}", path.display());
            return;
        };
        let keys = declared_natural_keys(&sql);
        let payment = keys
            .get("sales_payment_method")
            .unwrap_or_else(|| panic!("el seed de sales declara su clave:\n{sql}"));
        assert_eq!(payment[0].cols, vec!["hub_id", "type", "is_deleted"]);
    }
}
