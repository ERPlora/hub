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
    params.insert("current_user_id".into(), serde_json::json!("system"));

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
        let Some((table, key)) = parse_seed_guard(&stmt) else {
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

/// Traduce la guarda de UNA sentencia de seed a la clave natural que declara, o `None`.
///
/// Forma aceptada, que es la que escriben los tres seeds del repo:
/// `INSERT INTO <t> (…) SELECT … WHERE NOT EXISTS (SELECT 1 FROM <t> WHERE <cond> [AND <cond>]…)`,
/// donde cada `<cond>` es `columna = <lo que sea>` (el valor lo pondrá la fila del bundle, no el
/// seed) o `columna IS NULL`.
fn parse_seed_guard(stmt: &str) -> Option<(String, crate::export::NaturalKey)> {
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
    // `hub_id` a secas no es una clave: es «esta tabla, en este hub». Con ella la guarda saltaría
    // TODA fila entrante en cuanto el módulo hubiera sembrado una sola.
    if cols.iter().all(|c| c == "hub_id") {
        return None;
    }
    Some((
        table.to_string(),
        crate::export::NaturalKey {
            cols,
            predicate,
            nulls_not_distinct: false,
            seeded_only: true,
        },
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

    /// GARANTÍA del seed del demo (hub#36): aplicar `demo.sql` sobre un Runtime SQLite real deja
    /// un usuario "Demo" cuyo PIN "0000" verifica. Si el hash del PIN o los nombres de columna
    /// fueran erróneos, este test FALLA — es la red de seguridad que pide hub#36.
    ///
    /// Ya NO siembra dispositivo de confianza (hub#630): el `device_id` lo acuña el navegador, así
    /// que la fila que había aquí no la podía presentar nadie. Quien abre la puerta ahora es el
    /// trust-on-first-use del login, y **necesita que el hub no conozca ningún dispositivo** —
    /// sembrar uno lo desactivaría. Por eso este test comprueba lo contrario que antes: que el seed
    /// deja la lista VACÍA.
    #[tokio::test]
    async fn demo_seed_enables_demo_pin_login_and_trusted_device() {
        let db = fresh_db().await;
        let runtime = crate::Runtime::new(Box::new(db));
        // Mismo orden que en el server: tablas de sistema primero, luego seed.
        runtime.ensure_system_tables().await.unwrap();
        // Por `Runtime::apply_seed`, que es como lo llama el host (`HUB_SEED_SQL`, server/lib.rs) y
        // quien pone el `hub_id` del despliegue: llamar a `apply` a pelo dejaría sin probar
        // justamente el punto donde se decide de qué hub es lo que se siembra (hub#489).
        let n = runtime.apply_seed(DEMO_SEED).await.unwrap();
        assert!(
            n >= 1,
            "el seed del demo aplica al menos el usuario, fue {n}"
        );

        // El PIN "0000" del usuario "Demo" verifica (valida el formato del hash).
        let user = runtime.verify_pin("Demo", "0000").await.unwrap();
        let user = user.expect("Demo verifica con PIN 0000");
        assert_eq!(user.name, "Demo");
        assert!(user.is_active);
        // Rol con permisos completos (admin/owner): el seed lo fija; comprobamos que NO está vacío.
        assert!(!user.role.is_empty(), "el usuario demo tiene un rol");
        // PIN incorrecto NO verifica.
        assert!(runtime.verify_pin("Demo", "1111").await.unwrap().is_none());

        // 🔴 El seed NO deja ningún dispositivo de confianza, y eso es el contrato ahora (hub#630):
        // el trust-on-first-use del login solo adopta al primer visitante si el hub no conoce
        // ninguno todavía. Una fila sembrada aquí —como la que había, `demo-trusted-device`— dejaba
        // la demo sin puerta: nadie podía presentar ese id y la adopción no llegaba a actuar.
        assert!(
            runtime.list_devices().await.unwrap().is_empty(),
            "el seed debe dejar la lista de dispositivos vacía o el first-use no adopta a nadie"
        );

        // Re-aplicar el seed es idempotente (no crea un segundo "Demo" ni falla).
        runtime.apply_seed(DEMO_SEED).await.unwrap();
        let res = identity_count_demo(&runtime).await;
        assert_eq!(res, 1, "el seed no duplica el usuario Demo al re-aplicarse");
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
