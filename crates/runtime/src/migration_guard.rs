//! La puerta que sí protege: qué puede hacer la migración de un módulo (hub#542).
//!
//! Hasta ahora el SQL de un módulo se ejecutaba **tal cual**: `db.execute_batch(&sql)`, sin que
//! nada lo mirase. En la práctica los 24 módulos publicados respetan su prefijo, pero eso es una
//! **convención**: la cumple el módulo bien escrito, no protege del que tenga un bug. Y ya se cruzó
//! una vez — `taxes/003` crea y dropea `_taxes_backfill_hubs`, en el namespace de las tablas de
//! sistema.
//!
//! Importa **ahora** porque con la actualización automática de módulos (hub#516) ese SQL se
//! aplicará **solo, en toda la flota, sin que nadie lo lea**, y con blue/green (saas#1249) mientras
//! la versión anterior **sigue cobrando**.
//!
//! ## Dos reglas, y una traducción
//!
//! 1. **La tabla pertenece al módulo** — prefijo `<module_id>_`, y nunca `hub_*` ni `_*`.
//! 2. **El SQL coincide con el `kind` declarado.** Declarar la intención y comprobar que cuadra da
//!    errores entendibles; **adivinar** la intención del SQL es frágil.
//! 3. 🔑 **`DROP` se traduce a rename.** El módulo escribe `DROP COLUMN x`; el runtime ejecuta
//!    `RENAME COLUMN x TO _deprecated_x`. Es metadata —instantáneo, sin lock largo, sin copiar un
//!    byte—, **los datos siguen ahí**, y revertir es renombrar de vuelta. El autor escribe lo
//!    natural; el sistema hace lo seguro.
//!
//! ## Lo que esto NO es
//!
//! No es un parser de SQL, y no pretende serlo: es un **lint** sobre el texto de la migración. La
//! validación fina —índices sin `CONCURRENTLY`, `NOT NULL` sin default, defaults volátiles— es
//! trabajo de [Squawk](https://squawkhq.com/), que va en su propia iteración. Estas dos reglas son
//! las que Squawk **no** puede conocer, porque son nuestras.

use std::collections::HashSet;

/// Qué declara el módulo que hace esta migración.
#[derive(Debug, Clone, Copy, PartialEq, Eq, serde::Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum Kind {
    /// Solo aditivo. El 95% de los casos, y lo que se asume cuando no se declara nada.
    Expand,
    /// DML idempotente sobre tablas propias.
    Backfill,
    /// Lo destructivo. **Único sitio donde se admite `DROP`** — y aun ahí se traduce a rename.
    Contract,
}

impl Default for Kind {
    fn default() -> Self {
        Kind::Expand
    }
}

#[derive(Debug)]
pub enum GuardError {
    /// Toca una tabla que no es suya.
    ForeignTable { module_id: String, table: String },
    /// Toca el namespace del sistema (`hub_*`, `_*`).
    ReservedNamespace { table: String },
    /// El SQL no hace lo que el `kind` declara.
    KindMismatch { kind: Kind, found: String },
}

impl std::fmt::Display for GuardError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            GuardError::ForeignTable { module_id, table } => write!(
                f,
                "la migración toca `{table}`, que no pertenece a `{module_id}`. Una tabla de módulo \
                 empieza por `{module_id}_`."
            ),
            GuardError::ReservedNamespace { table } => write!(
                f,
                "la migración toca `{table}`: `hub_*` y `_*` son del sistema, no de un módulo."
            ),
            GuardError::KindMismatch { kind, found } => write!(
                f,
                "la migración se declara `{kind:?}` pero contiene `{found}`. Si es intencionado, \
                 declárala `contract` (y llevará `since`); si no, sobra."
            ),
        }
    }
}

impl std::error::Error for GuardError {}

/// Lo que YA está publicado y no cumpliría el contrato de hoy.
///
/// **Reescribir el histórico no es opción**: `_hub_migrations` registra por **nombre de fichero**,
/// así que tocar un `.sql` ya aplicado no re-ejecuta nada donde ya está y sí rompe donde no.
///
/// 🔴 **Esta lista solo puede ENCOGER.** Hay un test que falla si crece — es lo único que impide
/// que «abuelar» se convierta en la vía para seguir publicando lo que el contrato prohíbe. Y el
/// pase es por FICHERO, no por módulo: una migración nueva del mismo módulo no hereda nada.
pub const GRANDFATHERED: &[(&str, &str)] = &[
    // Generada escaneando los 24 módulos publicados con este mismo guard (2026-08-09).
    // ⚠️ La auditoría de la issue se quedaba corta: decía «~12 sentencias en 4 módulos» y son
    // NUEVE ficheros en SEIS — `tables/007`, `pricing/004` y `sales/011` no estaban contados.
    ("tables", "migrations/postgres/007_session_history_fk.sql"), // DROP CONSTRAINT
    ("sales", "migrations/postgres/011_sale_forgets_table.sql"),  // DROP COLUMN
    ("sales", "migrations/postgres/013_drop_legacy_cart.sql"),    // DROP TABLE
    ("taxes", "migrations/postgres/003_backfill_es_vat_baseline.sql"), // toca `_taxes_backfill_hubs`
    ("verifactu", "migrations/postgres/006_drop_cert_columns.sql"), // DROP COLUMN
    ("verifactu", "migrations/postgres/009_drop_auto_transmit.sql"), // DROP COLUMN
    ("pricing", "migrations/postgres/004_price_list_item_tenant_fk.sql"), // DROP CONSTRAINT
    ("services", "migrations/postgres/002_tax_rate_id.sql"),      // DROP COLUMN
    ("services", "migrations/postgres/004_discount_split.sql"),   // DROP COLUMN
];

fn is_grandfathered(module_id: &str, filename: &str) -> bool {
    GRANDFATHERED
        .iter()
        .any(|(m, f)| *m == module_id && *f == filename)
}

/// Qué hacer con la migración tras revisarla.
#[derive(Debug, PartialEq, Eq)]
pub enum Plan {
    /// Ejecutar **el SQL original, sin tocar**. Es lo que se devuelve en el 99% de los casos.
    ///
    /// 🔴 Esto NO es una optimización, es una regla de seguridad: partir por `;` y recomponer
    /// **corrompe SQL válido**. El primer intento lo hacía y reventó cinco e2e con
    /// `syntax error at or near "flags"` — el splitter no entiende dollar-quoting (`$$…$$`), y
    /// recomponer lo que no se ha entendido del todo destroza la migración.
    ///
    /// Inspeccionar puede ser imperfecto (se escapa algo, y el peor caso es no cazarlo).
    /// **Reescribir no puede**: el peor caso es romper un módulo que estaba bien.
    AsWritten,
    /// Solo en un `contract`: las sentencias con los `DROP` ya traducidos a rename.
    Rewritten(Vec<String>),
}

/// ¿El SQL hace lo que su `kind` dice? **Sin** la regla de propiedad.
///
/// Existe para las migraciones de **sistema** (hub#517), que no tienen manifest donde declarar nada
/// y que —al revés que las de módulo— **sí son dueñas** de `hub_*` y `_*`. Lo que sigue valiendo
/// igual es lo otro: una migración que destruye tiene que decirlo.
///
/// Es la mitad que importa para el rollback. Al revertir **no se ejecuta nada sobre el esquema**
/// (ADR-0269): se revierte el código y la columna se queda, y la versión anterior la ignora porque
/// su SQL no la menciona. Eso solo funciona si lo que se aplicó era **aditivo** — de ahí que
/// marcar lo que no lo es sea la única forma de saber qué versiones no admiten vuelta atrás.
pub fn kind_matches(sql: &str, kind: Kind) -> Result<(), GuardError> {
    for statement in split_statements(sql) {
        match kind {
            Kind::Expand => {
                if let Some(found) = destructive_verb(&statement) {
                    return Err(GuardError::KindMismatch { kind, found });
                }
            }
            Kind::Backfill => {
                if let Some(found) = ddl_verb(&statement) {
                    return Err(GuardError::KindMismatch { kind, found });
                }
            }
            Kind::Contract => {}
        }
    }
    Ok(())
}

/// Revisa la migración y dice cómo aplicarla.
pub fn check(
    module_id: &str,
    filename: &str,
    sql: &str,
    kind: Kind,
) -> Result<Plan, GuardError> {
    // Un fichero abuelado se aplica tal cual: ya está en las bases de la flota, y el contrato no
    // puede aplicarse retroactivamente sin romper justo lo que protege.
    if is_grandfathered(module_id, filename) {
        return Ok(Plan::AsWritten);
    }

    let statements: Vec<String> = split_statements(sql);

    let mut out = Vec::with_capacity(statements.len());
    for statement in statements {
        for table in tables_touched(&statement) {
            if table.starts_with("hub_") || table.starts_with('_') {
                return Err(GuardError::ReservedNamespace { table });
            }
            if !table.starts_with(&format!("{module_id}_")) {
                return Err(GuardError::ForeignTable {
                    module_id: module_id.to_string(),
                    table,
                });
            }
        }

        match kind {
            Kind::Expand => {
                if let Some(found) = destructive_verb(&statement) {
                    return Err(GuardError::KindMismatch { kind, found });
                }
                out.push(statement);
            }
            Kind::Backfill => {
                if let Some(found) = ddl_verb(&statement) {
                    return Err(GuardError::KindMismatch { kind, found });
                }
                out.push(statement);
            }
            // El único sitio donde `DROP` está admitido — y aun así se aparta, no se destruye.
            Kind::Contract => out.push(set_aside_instead_of_dropping(&statement)),
        }
    }

    // Solo un `contract` se reescribe. Todo lo demás se ejecuta **tal y como lo escribió el autor**.
    match kind {
        Kind::Contract => Ok(Plan::Rewritten(out)),
        _ => Ok(Plan::AsWritten),
    }
}

/// `DROP COLUMN x` → `RENAME COLUMN x TO _deprecated_x`; `DROP TABLE t` → `RENAME TO _deprecated_t`.
///
/// 🔴 **Decide sobre el SQL, nunca sobre el texto de la sentencia** (hub#1137). [`split_statements`]
/// conserva el comentario DENTRO de la sentencia que lo sigue —a propósito, es el arreglo de
/// hub#1027— así que una sentencia real EMPIEZA por la prosa del autor, no por su verbo. Cuando
/// esto casaba `DROP TABLE ` al principio del texto, un bloque de cabecera encima del primer `DROP`
/// —la forma que tienen las 123 migraciones publicadas, porque el repo la pide— hacía que no
/// casara: la función devolvía la sentencia tal cual y el hub ejecutaba un `DROP TABLE` **real e
/// irreversible** sobre la BD de un cliente, en silencio. El ` DROP COLUMN ` sobrevivía porque
/// buscaba en medio del texto, y esa asimetría es justo lo que lo hacía imposible de ver.
///
/// Lo que se reescribe se emite con **la prosa de cabecera delante**: lo que cambia es el SQL que
/// se ejecuta, no la explicación de por qué se ejecuta. Un comentario que fuera EN MEDIO de la
/// sentencia no viaja con el rename — es prosa, y lo que corre es el rename.
///
/// Lo que **no** se traduce, y a propósito: `DROP INDEX`. Un índice no guarda datos, su definición
/// vive en el `.sql` que lo creó y volver a crearlo es una línea; apartarlo a `_deprecated_*` lo
/// dejaría cobrando su coste de escritura para siempre a cambio de nada. Ninguna herramienta de
/// migraciones madura (Rails, Django, Flyway, Liquibase) aparta índices. Y en un `DROP TABLE` ni
/// siquiera hace falta escribirlo: Postgres se lleva los índices con la tabla — y con la tabla
/// apartada, se van con ella.
fn set_aside_instead_of_dropping(statement: &str) -> String {
    let (prose, rest) = leading_prose(statement);
    // El SQL de verdad, sin comentarios: es lo único sobre lo que se puede decidir.
    let cleaned = strip_comments(rest);
    let sql = cleaned.trim();
    let upper = sql.to_uppercase();

    if let Some(at) = upper.find(" DROP COLUMN ") {
        let head = sql[..at].trim_end(); // "ALTER TABLE sales_sale"
        let rest = sql[at + " DROP COLUMN ".len()..].trim();
        let (guard, column) = strip_if_exists(rest);
        let column = column.split_whitespace().next().unwrap_or(column).trim_end_matches(';');
        return format!("{prose}{head} RENAME COLUMN {guard}{column} TO _deprecated_{column}");
    }

    if upper.starts_with("DROP TABLE ") {
        let named = sql["DROP TABLE ".len()..].trim();
        let (guard, table) = strip_if_exists(named);
        let table = table.split_whitespace().next().unwrap_or(table).trim_end_matches(';');
        return format!("{prose}ALTER TABLE {guard}{table} RENAME TO _deprecated_{table}");
    }

    statement.to_string()
}

/// Parte la sentencia en (prosa de cabecera, SQL). La prosa es todo lo que precede al primer
/// carácter que no es espacio ni comentario — comentarios de línea y de bloque incluidos.
///
/// Existe para que reescribir un `DROP` no borre la explicación del autor: el trozo devuelto se
/// repone **verbatim** delante del `ALTER … RENAME`. Es un corte, no un parser: si la sentencia es
/// solo prosa, devuelve `("", statement)` y el llamante la deja como estaba.
fn leading_prose(statement: &str) -> (&str, &str) {
    let bytes = statement.as_bytes();
    let mut i = 0;
    loop {
        while i < bytes.len() && bytes[i].is_ascii_whitespace() {
            i += 1;
        }
        if statement[i..].starts_with("--") {
            match statement[i..].find('\n') {
                Some(end) => i += end + 1,
                // Un `--` sin salto de línea se come el resto: la sentencia es solo prosa.
                None => return ("", statement),
            }
            continue;
        }
        if statement[i..].starts_with("/*") {
            match statement[i..].find("*/") {
                Some(end) => i += end + "*/".len(),
                // Bloque sin cerrar: no se entiende, no se toca.
                None => return ("", statement),
            }
            continue;
        }
        break;
    }
    if i >= statement.len() {
        return ("", statement);
    }
    statement.split_at(i)
}

/// Devuelve (`"IF EXISTS "` si lo llevaba, resto). Se conserva: un `contract` que se reintenta —
/// porque el arranque anterior murió a medias— no puede reventar por apartar algo ya apartado.
fn strip_if_exists(rest: &str) -> (&'static str, &str) {
    let upper = rest.to_uppercase();
    if let Some(stripped) = upper.strip_prefix("IF EXISTS ") {
        let _ = stripped;
        ("IF EXISTS ", rest["IF EXISTS ".len()..].trim())
    } else {
        ("", rest)
    }
}

fn destructive_verb(statement: &str) -> Option<String> {
    let upper = strip_comments(statement).to_uppercase();
    for verb in ["DROP COLUMN", "DROP TABLE", "DROP CONSTRAINT", "TRUNCATE", "DELETE FROM"] {
        if upper.contains(verb) {
            return Some(verb.to_string());
        }
    }
    // `SET NOT NULL` sobre una columna que YA existe tampoco admite vuelta atrás: el binario
    // anterior insertaba sin ese campo y empezaría a fallar. Dentro de un `CREATE TABLE` sí es
    // aditivo (la tabla es nueva), y por eso solo cuenta en un `ALTER`.
    if upper.trim_start().starts_with("ALTER TABLE") && upper.contains("SET NOT NULL") {
        return Some("SET NOT NULL".to_string());
    }
    None
}

fn ddl_verb(statement: &str) -> Option<String> {
    let upper = strip_comments(statement).trim_start().to_uppercase();
    for verb in ["CREATE ", "ALTER ", "DROP ", "TRUNCATE"] {
        if upper.starts_with(verb) {
            return Some(verb.trim().to_string());
        }
    }
    None
}

/// Los nombres de tabla que la sentencia toca. Deliberadamente **simple**: reconoce las formas que
/// una migración usa de verdad y, ante la duda, no inventa — lo que no reconoce no bloquea, porque
/// un falso positivo aquí deja un módulo sin instalar.
/// Quita los comentarios SQL antes de mirar nada.
///
/// **Sin esto, las palabras de un comentario se leen como nombres de tabla.** Comprobado contra los
/// 24 módulos publicados: `-- … the …`, `-- … for …`, `-- … now …` producían cinco rechazos de
/// migraciones perfectamente correctas. Y un falso positivo aquí **deja un módulo sin instalar**,
/// que es peor que el problema que esto viene a resolver.
fn strip_comments(sql: &str) -> String {
    let mut out = String::with_capacity(sql.len());
    let mut chars = sql.chars().peekable();
    let mut in_string = false;
    while let Some(ch) = chars.next() {
        if in_string {
            out.push(ch);
            if ch == '\'' {
                in_string = false;
            }
            continue;
        }
        match ch {
            '\'' => {
                in_string = true;
                out.push(ch);
            }
            '-' if chars.peek() == Some(&'-') => {
                for next in chars.by_ref() {
                    if next == '\n' {
                        out.push('\n');
                        break;
                    }
                }
            }
            '/' if chars.peek() == Some(&'*') => {
                chars.next();
                let mut prev = ' ';
                for next in chars.by_ref() {
                    if prev == '*' && next == '/' {
                        break;
                    }
                    prev = next;
                }
                out.push(' ');
            }
            _ => out.push(ch),
        }
    }
    out
}

fn tables_touched(statement: &str) -> Vec<String> {
    let statement = &strip_comments(statement);
    let mut found = Vec::new();
    let mut seen = HashSet::new();
    let tokens: Vec<&str> = statement.split_whitespace().collect();

    for (i, token) in tokens.iter().enumerate() {
        let upper = token.to_uppercase();
        // `ON` solo cuenta en un `CREATE INDEX … ON <tabla>`: en un JOIN va seguido de una
        // condición (`a.id = b.id`), y tomarla por un nombre de tabla es un falso positivo — que
        // aquí significa dejar un módulo sin instalar.
        let creating_index = {
            let head = strip_comments(statement).trim_start().to_uppercase();
            head.starts_with("CREATE INDEX") || head.starts_with("CREATE UNIQUE INDEX")
        };
        let is_anchor = matches!(upper.as_str(), "TABLE" | "INTO" | "UPDATE")
            || (upper == "ON" && creating_index)
            || (upper == "FROM" && !statement.trim_start().to_uppercase().starts_with("SELECT"));
        if !is_anchor {
            continue;
        }
        let mut j = i + 1;
        while let Some(next) = tokens.get(j) {
            let next_upper = next.to_uppercase();
            if matches!(next_upper.as_str(), "IF" | "NOT" | "EXISTS" | "ONLY") {
                j += 1;
                continue;
            }
            let name = next
                .trim_matches(|c: char| !c.is_alphanumeric() && c != '_')
                .to_lowercase();
            if !name.is_empty() && seen.insert(name.clone()) {
                found.push(name);
            }
            break;
        }
    }
    found
}

/// Parte por `;` respetando literales **y comentarios** — el mismo criterio que ya usa
/// `system_migrations`, más lo que le faltaba: un `;` (o un `'`) dentro de `-- …` o `/* … */` es
/// prosa, no SQL. Sin esto, `printing/002_jobs.sql` («-- read); this table is …») se partía a
/// mitad de comentario, el trozo perdía su `--`, y «table is» se leía como una tabla `is` que
/// «no pertenece a printing» — un módulo publicado y correcto que no se instalaba.
///
/// El comentario se conserva en la sentencia (se copia tal cual): quitarlo es cosa de
/// [`strip_comments`], en el momento de inspeccionar.
fn split_statements(sql: &str) -> Vec<String> {
    let mut out = Vec::new();
    let mut current = String::new();
    let mut in_string = false;
    let mut chars = sql.chars().peekable();
    while let Some(ch) = chars.next() {
        if in_string {
            current.push(ch);
            if ch == '\'' {
                in_string = false;
            }
            continue;
        }
        match ch {
            '\'' => {
                in_string = true;
                current.push(ch);
            }
            '-' if chars.peek() == Some(&'-') => {
                current.push(ch);
                for next in chars.by_ref() {
                    current.push(next);
                    if next == '\n' {
                        break;
                    }
                }
            }
            '/' if chars.peek() == Some(&'*') => {
                current.push(ch);
                let mut prev = ' ';
                for next in chars.by_ref() {
                    current.push(next);
                    if prev == '*' && next == '/' {
                        break;
                    }
                    prev = next;
                }
            }
            ';' => {
                if !current.trim().is_empty() {
                    out.push(current.trim().to_string());
                }
                current.clear();
            }
            _ => current.push(ch),
        }
    }
    if !current.trim().is_empty() {
        out.push(current.trim().to_string());
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    fn expand(sql: &str) -> Result<Plan, GuardError> {
        check("sales", "migrations/postgres/007_x.sql", sql, Kind::Expand)
    }

    fn contract(sql: &str) -> Result<Plan, GuardError> {
        check("sales", "migrations/postgres/013_x.sql", sql, Kind::Contract)
    }

    // ── La tabla pertenece al módulo ─────────────────────────────────────────────────

    /// Un `expand` **no se reescribe nunca**: su SQL sale tal cual.
    #[test]
    fn an_expand_is_applied_exactly_as_written() {
        assert_eq!(expand("CREATE TABLE sales_sale (id BIGINT)").unwrap(), Plan::AsWritten);
    }

    #[test]
    fn a_module_may_touch_its_own_tables() {
        expand("CREATE TABLE sales_sale (id BIGINT)").expect("su prefijo, su tabla");
    }

    /// **Un módulo no toca las tablas de OTRO.** Hoy es una convención que cumple el módulo bien
    /// escrito; no protege del que tenga un bug, y con la actualización automática (#516) ese SQL
    /// se aplicará solo, en toda la flota, sin que nadie lo lea.
    #[test]
    fn a_module_may_not_touch_another_modules_tables() {
        let refused = expand("ALTER TABLE inventory_item ADD COLUMN x TEXT");

        assert!(matches!(refused, Err(GuardError::ForeignTable { .. })), "{refused:?}");
    }

    /// **Ni las del sistema.** Ya se cruzó una vez: `taxes/003` crea y dropea
    /// `_taxes_backfill_hubs`, en el namespace `_*` de las tablas de sistema.
    #[test]
    fn the_system_namespaces_are_off_limits() {
        for sql in [
            "ALTER TABLE hub_module ADD COLUMN x TEXT",
            "DROP TABLE _hub_migrations",
            "CREATE TABLE _sales_scratch (id BIGINT)",
        ] {
            let refused = check("sales", "m.sql", sql, Kind::Contract);
            assert!(
                matches!(refused, Err(GuardError::ReservedNamespace { .. })),
                "debería rechazar `{sql}`: {refused:?}"
            );
        }
    }

    /// **Un índice también toca una tabla.** Sin esto, un módulo podía indexar la tabla de otro y
    /// el guard no lo veía — el hueco lo destapó un fixture al que `CREATE INDEX … ON products` se
    /// le escapó del renombrado.
    #[test]
    fn an_index_on_another_modules_table_is_caught() {
        let refused = expand("CREATE INDEX idx_x ON inventory_item (hub_id)");

        assert!(matches!(refused, Err(GuardError::ForeignTable { .. })), "{refused:?}");
    }

    #[test]
    fn an_index_on_its_own_table_is_fine() {
        expand("CREATE INDEX idx_x ON sales_sale (hub_id)").expect("su tabla, su índice");
    }

    // ── El SQL coincide con el `kind` declarado ──────────────────────────────────────

    /// Declarar la intención y comprobar que el SQL coincide da errores entendibles; **adivinar**
    /// la intención del SQL es frágil. Por eso el `kind` lo declara el módulo.
    #[test]
    fn an_expand_may_not_destroy() {
        let refused = expand("ALTER TABLE sales_sale DROP COLUMN total");

        assert!(matches!(refused, Err(GuardError::KindMismatch { .. })), "{refused:?}");
    }

    #[test]
    fn a_backfill_may_not_change_the_schema() {
        let refused = check(
            "sales",
            "m.sql",
            "ALTER TABLE sales_sale ADD COLUMN total BIGINT",
            Kind::Backfill,
        );

        assert!(matches!(refused, Err(GuardError::KindMismatch { .. })), "{refused:?}");
    }

    #[test]
    fn a_backfill_may_update_its_own_rows() {
        check("sales", "m.sql", "UPDATE sales_sale SET total = 0 WHERE total IS NULL", Kind::Backfill)
            .expect("es exactamente para lo que existe");
    }

    // ── 🔑 `DROP` se traduce a rename ────────────────────────────────────────────────

    /// **Lo que se destruye se aparta, no se destruye.** El autor escribe lo natural; el sistema
    /// hace lo seguro. Un `RENAME` es metadata: instantáneo, sin lock largo, sin copiar un byte —
    /// y **los datos siguen ahí**, así que revertir es renombrar de vuelta.
    #[test]
    fn dropping_a_column_becomes_renaming_it_aside() {
        let rewritten = contract("ALTER TABLE sales_sale DROP COLUMN tax_rate").unwrap();

        assert_eq!(
            rewritten,
            Plan::Rewritten(vec![
                "ALTER TABLE sales_sale RENAME COLUMN tax_rate TO _deprecated_tax_rate".into()
            ])
        );
    }

    #[test]
    fn dropping_a_table_becomes_renaming_it_aside() {
        let rewritten = contract("DROP TABLE sales_old_line").unwrap();

        assert_eq!(
            rewritten,
            Plan::Rewritten(vec![
                "ALTER TABLE sales_old_line RENAME TO _deprecated_sales_old_line".into()
            ])
        );
    }

    /// Y no se aparta dos veces: al segundo arranque la columna ya se llama `_deprecated_*`.
    #[test]
    fn setting_something_aside_twice_is_not_an_error() {
        let Plan::Rewritten(rewritten) =
            contract("ALTER TABLE sales_sale DROP COLUMN IF EXISTS tax_rate").unwrap()
        else {
            panic!("un contract se reescribe");
        };

        assert!(
            rewritten[0].contains("IF EXISTS") || rewritten[0].contains("RENAME"),
            "un contract repetido no puede reventar el arranque: {rewritten:?}"
        );
    }

    // ── 🔑 …y la prosa del autor no puede anularlo (hub#1137) ───────────────────────

    /// 🔴 **El caso que destruía datos de verdad.** `split_statements` conserva el comentario
    /// DENTRO de la sentencia que lo sigue (hub#1027, y está bien: sin eso `printing/002_jobs.sql`
    /// se partía a mitad de un `--`). El traductor casaba `DROP TABLE ` al PRINCIPIO del texto, así
    /// que un bloque de prosa de cabecera —la forma que tienen las 123 migraciones publicadas,
    /// porque el repo la pide— empujaba el `DROP` fuera del principio, no casaba, y el `DROP TABLE`
    /// salía **tal cual** hacia la BD del cliente. La decisión se toma sobre el SQL, no sobre el
    /// texto; la prosa se repone delante de lo reescrito.
    #[test]
    fn a_header_comment_above_the_drop_does_not_defeat_the_translation() {
        let Plan::Rewritten(rewritten) = contract(
            "-- Sales · migration 013 — retire the legacy cart.\n\
             -- The feature moved into the core; this file is how the table stops being used.\n\
             DROP TABLE IF EXISTS sales_old_line",
        )
        .unwrap() else {
            panic!("un contract se reescribe");
        };

        assert!(
            !rewritten[0].to_uppercase().contains("DROP TABLE"),
            "🔴 un `DROP TABLE` REAL e irreversible se escapó a la BD del cliente: {rewritten:?}"
        );
        assert!(
            rewritten[0].ends_with(
                "ALTER TABLE IF EXISTS sales_old_line RENAME TO _deprecated_sales_old_line"
            ),
            "la tabla se aparta, no se destruye: {rewritten:?}"
        );
        assert!(
            rewritten[0].starts_with("-- Sales · migration 013"),
            "y la explicación del autor viaja con lo que se ejecuta: {rewritten:?}"
        );
    }

    /// Lo mismo con un comentario de **bloque**: `/* … */` también viaja dentro de la sentencia.
    #[test]
    fn a_block_comment_above_the_drop_does_not_defeat_the_translation() {
        let Plan::Rewritten(rewritten) =
            contract("/* retire the legacy cart (sales#12) */\nDROP TABLE sales_old_line").unwrap()
        else {
            panic!("un contract se reescribe");
        };

        assert!(
            rewritten[0].ends_with(
                "ALTER TABLE sales_old_line RENAME TO _deprecated_sales_old_line"
            ),
            "un comentario de bloque tampoco anula la traducción: {rewritten:?}"
        );
    }

    /// Y el `DROP` no tiene por qué ser el primero del fichero: cada sentencia se traduce donde
    /// esté, lleve prosa delante o no.
    #[test]
    fn every_drop_of_the_file_is_translated_wherever_it_sits() {
        let Plan::Rewritten(rewritten) = contract(
            "-- Sales · migration 013 — retire the legacy cart.\n\
             CREATE TABLE sales_new_line (id BIGINT);\n\
             -- first the child, then the parent\n\
             DROP TABLE sales_old_line;\n\
             ALTER TABLE sales_sale DROP COLUMN legacy_total;\n\
             /* and the index goes with it */\n\
             DROP TABLE IF EXISTS sales_old_cart",
        )
        .unwrap() else {
            panic!("un contract se reescribe");
        };

        let escaped: Vec<&String> =
            rewritten.iter().filter(|s| s.to_uppercase().contains("DROP ")).collect();
        assert!(
            escaped.is_empty(),
            "🔴 estos `DROP` se escaparon sin traducir: {escaped:?}"
        );
        assert!(rewritten[1].ends_with("RENAME TO _deprecated_sales_old_line"), "{rewritten:?}");
        assert!(
            rewritten[2].ends_with("RENAME COLUMN legacy_total TO _deprecated_legacy_total"),
            "{rewritten:?}"
        );
        assert!(rewritten[3].ends_with("RENAME TO _deprecated_sales_old_cart"), "{rewritten:?}");
    }

    /// La red de seguridad: **ningún** `contract` puede dejar salir un `DROP TABLE`/`DROP COLUMN`
    /// sin traducir, escríbalo el autor como lo escriba. Es el test que se pone rojo si alguien
    /// vuelve a decidir sobre el texto crudo en vez de sobre el SQL.
    #[test]
    fn no_contract_ever_emits_an_untranslated_drop() {
        let shapes = [
            "DROP TABLE sales_x",
            "  DROP TABLE sales_x",
            "-- prosa\nDROP TABLE sales_x",
            "-- prosa\n-- más prosa\nDROP TABLE IF EXISTS sales_x",
            "/* prosa */ DROP TABLE sales_x",
            "/* prosa */\n  DROP TABLE IF EXISTS sales_x",
            "-- prosa\nALTER TABLE sales_sale DROP COLUMN tax_rate",
            "/* prosa */ ALTER TABLE sales_sale DROP COLUMN IF EXISTS tax_rate",
        ];

        for sql in shapes {
            let Plan::Rewritten(rewritten) = contract(sql).unwrap() else {
                panic!("un contract se reescribe: {sql:?}");
            };
            for statement in &rewritten {
                let executed = strip_comments(statement).to_uppercase();
                assert!(
                    !executed.contains("DROP TABLE") && !executed.contains("DROP COLUMN"),
                    "🔴 `{sql}` deja escapar un DROP real: {statement:?}"
                );
                assert!(
                    executed.contains("RENAME"),
                    "`{sql}` tenía que apartarse con un RENAME: {statement:?}"
                );
            }
        }
    }

    /// El otro `contract` publicado (`verifactu/012_named_gate_constraints.sql`) **sí** abre con un
    /// bloque de prosa, y lo suyo es un `DROP CONSTRAINT` — que el guard NO traduce y no tiene por
    /// qué: una restricción no guarda filas y su definición viaja en el mismo fichero que la
    /// repone. Lo que este test fija es que reponer la prosa delante no cambia lo que se ejecuta
    /// cuando NO hay nada que traducir: la sentencia sale intacta, comentario incluido.
    #[test]
    fn what_the_guard_does_not_translate_comes_out_untouched() {
        let sql = "-- Each gate refuses UNDER ITS OWN NAME (verifactu#40).\n\
                   ALTER TABLE sales_gate DROP CONSTRAINT IF EXISTS sales_gate_ok_check;\n\
                   ALTER TABLE sales_gate ADD CONSTRAINT sales_gate_is_declared CHECK (ok = 1)";

        let Plan::Rewritten(rewritten) = contract(sql).unwrap() else {
            panic!("un contract se reescribe");
        };

        assert_eq!(
            rewritten,
            vec![
                "-- Each gate refuses UNDER ITS OWN NAME (verifactu#40).\nALTER TABLE sales_gate DROP CONSTRAINT IF EXISTS sales_gate_ok_check".to_string(),
                "ALTER TABLE sales_gate ADD CONSTRAINT sales_gate_is_declared CHECK (ok = 1)".to_string(),
            ],
            "lo que no se traduce se ejecuta TAL CUAL, prosa incluida"
        );
    }

    /// **Un comentario no es SQL.** Comprobado contra los 24 módulos publicados: las palabras de
    /// los comentarios (`-- … the …`, `-- … for …`) se leían como nombres de tabla y rechazaban
    /// CINCO migraciones correctas. Un falso positivo aquí deja un módulo sin instalar, que es peor
    /// que el problema que esto viene a resolver.
    #[test]
    fn words_inside_comments_are_not_table_names() {
        expand(
            "-- la fila que guarda el total for every sale\n             CREATE TABLE sales_total (id BIGINT);\n             /* DROP TABLE inventory_item -- esto es prosa, no SQL */",
        )
        .expect("los comentarios no cuentan");
    }

    /// The real `printing/002_jobs.sql` (v0.1.11): its header prose has TWO apostrophes
    /// ("The module's … the runtime's") inside `--` comments. Read as string delimiters they
    /// desynchronise the quote tracking, and prose words start looking like table names — the
    /// install failed with «la migración toca `is`». A comment is opaque, apostrophes and all.
    #[test]
    fn apostrophes_inside_comments_do_not_open_a_string() {
        let sql = include_str!("../tests/fixtures/migration_guard/printing_002_jobs.sql");
        check("printing", "migrations/postgres/002_jobs.sql", sql, Kind::Expand)
            .unwrap_or_else(|e| panic!("a published, well-formed migration must pass: {e}"));
    }

    // ── Lo ya publicado: la lista de abuelados ───────────────────────────────────────

    /// Las ~12 sentencias destructivas que YA están publicadas siguen aplicándose.
    ///
    /// Reescribir el histórico **no es opción**: `_hub_migrations` registra por **nombre de
    /// fichero**, así que tocar un `.sql` ya aplicado no re-ejecuta nada donde ya está y sí rompe
    /// donde no. Se abuelan por `(module_id, filename)` y se dejan pasar tal cual.
    #[test]
    fn what_was_already_published_still_applies() {
        let sql = "DROP TABLE sales_legacy_cart";

        check("sales", "migrations/postgres/013_drop_legacy_cart.sql", sql, Kind::Expand)
            .expect("un fichero abuelado pasa aunque su SQL ya no sea legal");
    }

    /// **La lista solo puede encoger.** Es lo único que impide que «abuelar» se convierta en la vía
    /// para seguir publicando lo que el contrato prohíbe.
    #[test]
    fn the_grandfathered_list_may_only_shrink() {
        assert!(
            GRANDFATHERED.len() <= 9,
            "la lista de abuelados ha CRECIDO ({} entradas). No se añade nada: si una migración \
             nueva necesita estar aquí, es que no cumple el contrato.",
            GRANDFATHERED.len()
        );
    }

    #[test]
    fn a_new_file_in_a_grandfathered_module_gets_no_pass() {
        let refused = check("sales", "migrations/postgres/099_nuevo.sql", "DROP TABLE sales_x", Kind::Expand);

        assert!(
            matches!(refused, Err(GuardError::KindMismatch { .. })),
            "el pase es por FICHERO, no por módulo: {refused:?}"
        );
    }
}
