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
//! trabajo de [Squawk](https://squawkhq.com/), que va en su propia iteración.
//!
//! Y de ahí sale la regla de hub#1149: **lo que este lint no puede leer, no entra**. El cuerpo de
//! un `DO`/`CREATE FUNCTION` es opaco —dentro cabe un `EXECUTE` que arma la sentencia en tiempo de
//! ejecución— así que el guard no finge entenderlo: lo rechaza y dice por dónde se pasa. Medido
//! antes de escribirlo: cero de las 155 migraciones publicadas usa un cuerpo procedimental. Estas dos reglas son
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
    /// Un `contract` destruye FILAS. No hay traducción posible: se rechaza (hub#1145).
    RowDestruction { verb: &'static str },
    /// Un `contract` que RESHAPEa (rename / cambio de tipo) sin decir desde qué versión es
    /// seguro retirarlo: la ventana N/N-1 no se puede revisar si nadie la declara (hub#1163).
    ContractWithoutVersion { verb: String },
    /// Un `DROP` que nombra varias cosas en una sentencia. La traducción es 1:1 o no es (hub#1145).
    DropsMoreThanOne {
        what: &'static str,
        statement: String,
    },
    /// Un cuerpo procedimental (`DO`, `CREATE FUNCTION`/`PROCEDURE`). El guard es un lint sobre el
    /// TEXTO y ahí dentro no hay texto que leer: no se inspecciona, no entra (hub#1149).
    NotInspectable { construct: &'static str },
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
                 declárala `contract` (con su `since` en el manifest, y una línea \
                 `-- contract: <versión>` si lo que hace es renombrar o cambiar un tipo); si no, \
                 sobra."
            ),
            GuardError::RowDestruction { verb } => write!(
                f,
                "la migración se declara `contract` pero contiene `{verb}`, que DESTRUYE FILAS sin \
                 vuelta atrás. Un `contract` retira ESTRUCTURA y el runtime la aparta a \
                 `_deprecated_*`; de las filas no hay nada que apartar. Si de verdad hay que \
                 limpiarlas, va en una migración `backfill`, que es donde el DML tiene su sitio y \
                 donde se ve que no admite vuelta atrás."
            ),
            GuardError::NotInspectable { construct } => write!(
                f,
                "la migración contiene un `{construct}`, y el cuerpo de un bloque procedimental es \
                 opaco para esta puerta: dentro cabe un `EXECUTE` que arma la sentencia en tiempo \
                 de ejecución, así que no se puede afirmar ni qué tablas toca ni si destruye filas. \
                 Escribe la migración como sentencias SQL sueltas, que es lo que sí se puede leer."
            ),
            GuardError::ContractWithoutVersion { verb } => write!(
                f,
                "la migración se declara `contract` y contiene `{verb}`, que deja de servir a la \
                 versión ANTERIOR del hub: con `start-first` las dos sirven a la vez contra la \
                 misma base. Di desde qué versión es seguro con una línea `-- contract: <versión>` \
                 —la versión del módulo que dejó de usar lo que esto retira—."
            ),
            GuardError::DropsMoreThanOne { what, statement } => write!(
                f,
                "la migración `contract` retira más de una {what} en la misma sentencia, y la \
                 traducción a `RENAME` es de una sentencia a una sentencia: `{statement}`. Escribe \
                 una {what} por sentencia."
            ),
        }
    }
}

impl std::error::Error for GuardError {}

/// The verbs that take a migration OUT of `expand` — the catalogue frozen in
/// `contracts/kernel/engine.snapshot`.
///
/// Two families, and the second is the one hub#1163 was missing:
///
///  - **destroys DATA** (`DROP …`, `TRUNCATE`, `DELETE FROM`, `SET NOT NULL`): there is no way
///    back, so it cannot be additive.
///  - **destroys the PREVIOUS BINARY** ([`RESHAPE_VERBS`]): a rename or a type change touches no
///    row, and is exactly what breaks N-1. With `start-first` + `dnsrr` the old task and the new
///    one serve at the same time against the same database, and `failure_action: rollback` gives
///    back a hub that has already run the migrations of N — against a schema no rollback undoes,
///    because reverting runs no SQL (ADR-0269).
///
/// Every entry has a positive control in the tests: a statement that trips it BY THIS NAME.
pub const NOT_EXPAND: &[&str] = &[
    "ALTER COLUMN ... TYPE",
    "DELETE FROM",
    "DROP COLUMN",
    "DROP CONSTRAINT",
    "DROP TABLE",
    "RENAME COLUMN",
    "RENAME TO",
    "SET NOT NULL",
    "TRUNCATE",
];

/// The subset of [`NOT_EXPAND`] that breaks N-1 without destroying a single row.
///
/// It is its own list for two reasons: it is what [`RESHAPE_GRANDFATHERED`] excuses (and nothing
/// else), and it is what a `contract` has to name a version for.
pub const RESHAPE_VERBS: &[&str] = &["ALTER COLUMN ... TYPE", "RENAME COLUMN", "RENAME TO"];

/// The already-published `expand` migrations that reshape a column, from BEFORE hub#1163.
///
/// Same reasoning as [`GRANDFATHERED`] and the same rule: **it may only SHRINK.** These twelve
/// files are installed across the fleet and are re-run in full on every FRESH install; refusing
/// them now would undo nothing — it would simply stop eight modules from installing.
///
/// Generated by running this guard over the `origin/main` of the published module repos
/// (2026-08-28): 153 migrations scanned, these 12 refused and no others. The frozen copies live
/// in `tests/fixtures/published_reshapes/`, and `published_reshapes_still_install.rs` is what
/// keeps the list honest in both directions. The pass is for the RESHAPE and per FILE: the same
/// module's next migration inherits nothing, and a `DROP` in a listed file is still refused.
pub const RESHAPE_GRANDFATHERED: &[(&str, &str)] = &[
    (
        "cart_checkout",
        "migrations/postgres/003_quantity_fixed_point.sql",
    ),
    ("inventory", "migrations/postgres/002_tax_rate_id.sql"),
    ("inventory", "migrations/postgres/004_tax_category_key.sql"),
    ("inventory", "migrations/postgres/005_stock_ledger.sql"),
    (
        "inventory",
        "migrations/postgres/006_quantity_fixed_point.sql",
    ),
    (
        "invoice",
        "migrations/postgres/004_quantity_fixed_point.sql",
    ),
    ("kitchen", "migrations/postgres/004_dispatch_snapshot.sql"),
    (
        "kitchen",
        "migrations/postgres/005_quantity_fixed_point.sql",
    ),
    (
        "pricing",
        "migrations/postgres/005_quantity_fixed_point.sql",
    ),
    ("sales", "migrations/postgres/014_quantity_fixed_point.sql"),
    ("services", "migrations/postgres/005_tax_category_key.sql"),
    (
        "services",
        "migrations/postgres/006_quantity_fixed_point.sql",
    ),
];

fn is_reshape_grandfathered(module_id: &str, filename: &str) -> bool {
    RESHAPE_GRANDFATHERED
        .iter()
        .any(|(m, f)| *m == module_id && *f == filename)
}

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
    (
        "taxes",
        "migrations/postgres/003_backfill_es_vat_baseline.sql",
    ), // toca `_taxes_backfill_hubs`
    ("verifactu", "migrations/postgres/006_drop_cert_columns.sql"), // DROP COLUMN
    (
        "verifactu",
        "migrations/postgres/009_drop_auto_transmit.sql",
    ), // DROP COLUMN
    (
        "pricing",
        "migrations/postgres/004_price_list_item_tenant_fk.sql",
    ), // DROP CONSTRAINT
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
    /// `syntax error at or near "flags"`, porque recomponer lo que no se ha entendido del todo
    /// destroza la migración. Desde hub#1149 el splitter sí entiende dollar-quoting, pero la regla
    /// no cambia: se entiende para **decidir**, no para reescribir.
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
            // Aquí `contract` significa «declaro que esto no admite vuelta atrás», y esa
            // declaración es justamente lo que se pedía: no hay nada que comprobar. La regla de
            // hub#1145 —un `contract` no destruye filas— vive en [`check`], que es la puerta de las
            // migraciones de MÓDULO, las únicas cuyo `DROP` se traduce. Las de sistema son nuestras,
            // se leen en una PR y `MIGRATIONS` lleva su inventario de versiones sin rollback.
            Kind::Contract => {}
        }
    }
    Ok(())
}

/// Revisa la migración y dice cómo aplicarla.
pub fn check(module_id: &str, filename: &str, sql: &str, kind: Kind) -> Result<Plan, GuardError> {
    // Un fichero abuelado se aplica tal cual: ya está en las bases de la flota, y el contrato no
    // puede aplicarse retroactivamente sin romper justo lo que protege.
    if is_grandfathered(module_id, filename) {
        return Ok(Plan::AsWritten);
    }

    let statements: Vec<String> = split_statements(sql);
    // Se lee del texto CRUDO —es un comentario, y `strip_comments` se lo lleva— y una sola vez:
    // la marca es del FICHERO, no de la sentencia.
    let contract_version_declared = declares_contract_version(sql);

    let mut out = Vec::with_capacity(statements.len());
    for statement in statements {
        // 🔴 Lo que no se puede LEER, no entra (hub#1149). Esto es un lint sobre el texto y el
        // cuerpo de un bloque procedimental es opaco: dentro cabe `EXECUTE format('DROP TABLE
        // %I', …)`, donde ni el verbo ni la tabla son tokens. Va lo PRIMERO a propósito — si no,
        // el error que ve el autor sería un `KindMismatch` sobre un `DELETE` que el guard cree
        // haber entendido, y lo que hay que decirle es que ahí no se puede afirmar nada.
        if let Some(construct) = procedural_construct(&statement) {
            return Err(GuardError::NotInspectable { construct });
        }
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
                    // El pase de `RESHAPE_GRANDFATHERED` es para el RESHAPE y para nada más: un
                    // `DROP` en un fichero de la lista se sigue rechazando, y el fichero siguiente
                    // del mismo módulo no hereda nada.
                    let excused = RESHAPE_VERBS.contains(&found.as_str())
                        && is_reshape_grandfathered(module_id, filename);
                    if !excused {
                        return Err(GuardError::KindMismatch { kind, found });
                    }
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
            Kind::Contract => {
                // 🔴 Lo que NO se puede apartar, no entra (hub#1145). `set_aside_instead_of_dropping`
                // solo sabe traducir `DROP TABLE` y `DROP COLUMN`; cualquier otro verbo destructivo
                // salía por aquí **tal cual** y se ejecutaba de verdad.
                if let Some(verb) = row_destroying_verb(&statement) {
                    return Err(GuardError::RowDestruction { verb });
                }
                // 🔑 La escotilla del reshape es ESTA, y solo aquí (hub#1163): un `contract` puede
                // renombrar o cambiar un tipo, pero tiene que decir desde qué versión es seguro.
                // Un `contract` que solo retira ESTRUCTURA no la necesita — el runtime la aparta a
                // `_deprecated_*` y las 4 publicadas son exactamente eso.
                if let Some(verb) = reshape_verb(&strip_comments(&statement).to_uppercase()) {
                    if !contract_version_declared {
                        return Err(GuardError::ContractWithoutVersion {
                            verb: verb.to_string(),
                        });
                    }
                }
                out.push(set_aside_instead_of_dropping(&statement)?);
            }
        }
    }

    // Solo un `contract` se reescribe. Todo lo demás se ejecuta **tal y como lo escribió el autor**.
    match kind {
        Kind::Contract => Ok(Plan::Rewritten(out)),
        _ => Ok(Plan::AsWritten),
    }
}

/// The name a retired table or column is set aside under. The install gate of commands
/// (`installer::validate_table_scope`) recognises a module's own set-aside tables by it (hub#2461).
pub const SET_ASIDE_PREFIX: &str = "_deprecated_";

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
///
/// 🔴 **La traducción es de UNA sentencia a UNA sentencia** (hub#1145). `DROP TABLE a, b;` es SQL
/// válido, pero `ALTER TABLE … RENAME TO` acepta **una sola** tabla, así que una lista tendría que
/// salir como N sentencias. Cuando esto se limitaba a coger el primer nombre, lo que se ejecutaba
/// era `ALTER TABLE a, RENAME TO _deprecated_a,` — un `syntax error at or near ","` que no explica
/// nada y que además dejaba `b` sin retirar. Se rechaza en el guard, con el error diciendo qué
/// escribir: romper el 1:1 por una forma que nadie usa cuesta lo único que hace auditable la
/// traducción — que el autor pueda leer el SQL reescrito y casarlo con el suyo línea a línea.
fn set_aside_instead_of_dropping(statement: &str) -> Result<String, GuardError> {
    let (prose, rest) = leading_prose(statement);
    // El SQL de verdad, sin comentarios: es lo único sobre lo que se puede decidir.
    let cleaned = strip_comments(rest);
    let sql = cleaned.trim();
    let upper = sql.to_uppercase();

    if let Some(at) = upper.find(" DROP COLUMN ") {
        // Una coma en cualquier sitio significa que el `ALTER` lleva más de una acción — sea
        // `DROP COLUMN a, DROP COLUMN b` o `ADD COLUMN x TEXT, DROP COLUMN y`. Las dos formas
        // producían un `RENAME` roto con la coma pegada dentro.
        if sql.trim_end_matches(';').contains(',') {
            return Err(GuardError::DropsMoreThanOne {
                what: "columna",
                statement: sql.to_string(),
            });
        }
        let head = sql[..at].trim_end(); // "ALTER TABLE sales_sale"
        let rest = sql[at + " DROP COLUMN ".len()..].trim();
        let (guard, column) = strip_if_exists(rest);
        let column = column
            .split_whitespace()
            .next()
            .unwrap_or(column)
            .trim_end_matches(';');
        if guard.is_empty() {
            return Ok(format!(
                "{prose}{head} RENAME COLUMN {column} TO _deprecated_{column}"
            ));
        }
        return Ok(format!(
            "{prose}{}",
            guarded_column_rename(table_of_alter(head), column)
        ));
    }

    if upper.starts_with("DROP TABLE ") {
        let named = sql["DROP TABLE ".len()..].trim();
        let (guard, table) = strip_if_exists(named);
        // `DROP TABLE t CASCADE` no lleva coma y sigue siendo una tabla: el `CASCADE` se cae solo
        // al renombrar, porque renombrar no arrastra a nadie.
        if table.trim_end_matches(';').contains(',') {
            return Err(GuardError::DropsMoreThanOne {
                what: "tabla",
                statement: sql.to_string(),
            });
        }
        let table = table
            .split_whitespace()
            .next()
            .unwrap_or(table)
            .trim_end_matches(';');
        return Ok(format!(
            "{prose}ALTER TABLE {guard}{table} RENAME TO {SET_ASIDE_PREFIX}{table}"
        ));
    }

    Ok(statement.to_string())
}

/// `DROP COLUMN IF EXISTS c` set aside WITHOUT losing its `IF EXISTS` (hub#2108).
///
/// Postgres has `ALTER TABLE IF EXISTS` and `DROP COLUMN IF EXISTS`, but **no**
/// `RENAME COLUMN IF EXISTS`: emitting it was a `syntax error at or near "EXISTS"` that left the
/// module un-updatable on every hub. Dropping the guard is not the answer either — the author wrote
/// `IF EXISTS` because the column may legitimately be missing, and a plain rename would then fail
/// the update just the same. So the rename runs only when the column is there, checked in the
/// catalog of the schema the migration runs in. The `DO` body is ours, not the module's: the
/// guard's refusal of procedural bodies (hub#1149) is about SQL it cannot read, and this one is
/// built here from two identifiers.
fn guarded_column_rename(table: &str, column: &str) -> String {
    format!(
        "DO $erplora_set_aside$ BEGIN IF EXISTS (SELECT 1 FROM information_schema.columns \
         WHERE table_schema = current_schema() AND table_name = {} AND column_name = {}) \
         THEN ALTER TABLE {table} RENAME COLUMN {column} TO _deprecated_{column}; END IF; \
         END $erplora_set_aside$",
        catalog_literal(table),
        catalog_literal(column),
    )
}

/// The table named by `ALTER TABLE [IF EXISTS] [ONLY] <table>`.
fn table_of_alter(head: &str) -> &str {
    let mut rest = head.trim();
    for keyword in ["ALTER TABLE ", "IF EXISTS ", "ONLY "] {
        if rest.len() >= keyword.len() && rest[..keyword.len()].eq_ignore_ascii_case(keyword) {
            rest = rest[keyword.len()..].trim_start();
        }
    }
    rest
}

/// An identifier as the catalog stores it, as a string literal: unquoted names fold to lower case,
/// quoted ones keep theirs.
fn catalog_literal(identifier: &str) -> String {
    let name = match identifier
        .strip_prefix('"')
        .and_then(|inner| inner.strip_suffix('"'))
    {
        Some(quoted) => quoted.replace("\"\"", "\""),
        None => identifier.to_lowercase(),
    };
    format!("'{}'", name.replace('\'', "''"))
}

/// El verbo que destruye FILAS, si la sentencia lleva alguno (hub#1145).
///
/// Solo `TRUNCATE` y `DELETE FROM`, y a propósito: es lo que un `contract` **no puede traducir**.
/// `DROP TABLE`/`DROP COLUMN` se apartan, y `DROP CONSTRAINT` no toca ni una fila —de hecho una de
/// las tres migraciones `contract` publicadas es exactamente eso, un swap atómico de constraint—,
/// así que meterlos aquí pondría en rojo trabajo correcto ya publicado.
///
/// Compara **tokens enteros**, no subcadenas: `contains("TRUNCATE")` caza una columna llamada
/// `truncate_at`, y un falso positivo aquí deja un módulo sin instalar. Por lo mismo `DELETE` solo
/// cuenta cuando le sigue `FROM` — `ON DELETE CASCADE` es una constraint, no un borrado — y se mira
/// token a token en vez de buscar la frase `"DELETE FROM"`, que un salto de línea partiría.
fn row_destroying_verb(statement: &str) -> Option<&'static str> {
    let cleaned = strip_comments(statement).to_uppercase();
    let tokens: Vec<&str> = cleaned.split_whitespace().map(bare_token).collect();
    for (i, token) in tokens.iter().enumerate() {
        if *token == "TRUNCATE" {
            return Some("TRUNCATE");
        }
        if *token == "DELETE" && tokens.get(i + 1) == Some(&"FROM") {
            return Some("DELETE FROM");
        }
    }
    None
}

/// El token sin la puntuación que lo rodea: `t);` → `T`. Deja `_` dentro, que es parte del nombre.
fn bare_token(token: &str) -> &str {
    token.trim_matches(|c: char| !c.is_ascii_alphanumeric() && c != '_')
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

/// Does the migration declare the version from which its `contract` is safe? (hub#1163)
///
/// The line is `-- contract: <version>` and it has to name a VERSION — digits and dots, the shape
/// of the module versions the manifest already uses in `since`. `-- contract:` on its own, or
/// followed by prose, is the author saying nothing while looking like they said something.
///
/// 🔴 It is read ONLY under `Kind::Contract`. hub#1137 already cost real data by letting a comment
/// change what the guard did with the SQL under it: the hatch is the declared `kind`, which a
/// reviewer sees in the manifest — this marker only says WHEN, never WHETHER.
fn declares_contract_version(sql: &str) -> bool {
    sql.lines().any(|line| {
        let Some(rest) = line.trim().strip_prefix("--") else {
            return false;
        };
        let Some(version) = rest.trim_start().strip_prefix("contract:") else {
            return false;
        };
        let version = version.trim();
        let version = version.strip_suffix("*/").unwrap_or(version).trim();
        !version.is_empty()
            && version.starts_with(|c: char| c.is_ascii_digit())
            && version.chars().all(|c| c.is_ascii_digit() || c == '.')
    })
}

/// Returns (`"IF EXISTS "` if it had one, rest). It is kept: a `contract` that is retried —because
/// the previous boot died halfway— cannot blow up setting aside something already set aside. For a
/// table it travels as `ALTER TABLE IF EXISTS`; for a column Postgres has no such clause, so it
/// becomes a catalog check ([`guarded_column_rename`], hub#2108).
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
    for verb in [
        "DROP COLUMN",
        "DROP TABLE",
        "DROP CONSTRAINT",
        "TRUNCATE",
        "DELETE FROM",
    ] {
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
    reshape_verb(&upper).map(str::to_string)
}

/// The verb that breaks N-1 without destroying a row, if the statement carries one (hub#1163).
///
/// Takes the SQL **already stripped of comments and upper-cased**, and compares WHOLE TOKENS —
/// never substrings. `contains("RENAME TO")` is caught out by a column called `rename_to`, and a
/// false positive here leaves a module uninstalled, which is the expensive direction. Same
/// criterion as [`row_destroying_verb`], for the same reason.
///
/// `ALTER COLUMN` only counts when the action is a TYPE change (`… TYPE`, `… SET DATA TYPE`):
/// `SET DEFAULT`, `DROP DEFAULT` and `DROP NOT NULL` widen what the previous binary may write,
/// they do not narrow it. `SET NOT NULL` is the exception, and it is handled by its caller.
///
/// `RENAME CONSTRAINT` stays out on purpose: it moves no data and no query names a constraint.
///
/// 🔴 The keyword `COLUMN` is **optional** in Postgres in both verbs (`RENAME a TO b`,
/// `ALTER a TYPE …`), so both forms are read. A guard you get past by leaving a word out is not
/// a guard, and nobody leaves it out on purpose — which is exactly why it would have slipped.
fn reshape_verb(cleaned_upper: &str) -> Option<&'static str> {
    let tokens: Vec<&str> = cleaned_upper.split_whitespace().map(bare_token).collect();
    for (i, token) in tokens.iter().enumerate() {
        if *token == "RENAME" {
            match tokens.get(i + 1) {
                Some(&"COLUMN") => return Some("RENAME COLUMN"),
                Some(&"TO") => return Some("RENAME TO"),
                // A constraint is not part of the surface a query names: it stays out.
                Some(&"CONSTRAINT") => {}
                // `RENAME <columna> TO <columna>`: la palabra `COLUMN` es opcional, y omitirla no
                // lo hace menos rompedor para N-1.
                Some(_) if tokens.get(i + 2) == Some(&"TO") => return Some("RENAME COLUMN"),
                _ => {}
            }
        }
        if *token == "ALTER" {
            // `ALTER [COLUMN] <nombre> <acción>`: con la palabra, la acción empieza tres tokens
            // más allá; sin ella, dos. El `ALTER` de cabecera (`ALTER TABLE <tabla> …`) no casa
            // por sí mismo: en su posición la «acción» es el nombre de la tabla.
            let with_keyword = tokens.get(i + 1) == Some(&"COLUMN");
            let action_at = if with_keyword { i + 3 } else { i + 2 };
            let action = &tokens[action_at.min(tokens.len())..];
            if action.first() == Some(&"TYPE") || action.starts_with(&["SET", "DATA", "TYPE"]) {
                return Some("ALTER COLUMN ... TYPE");
            }
        }
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

/// La construcción procedimental que la sentencia abre, si abre alguna (hub#1149).
///
/// Solo `DO` y `CREATE [OR REPLACE] FUNCTION`/`PROCEDURE`: las tres formas que meten un cuerpo
/// que esta puerta no puede leer. Un `$…$` suelto **no** cuenta — `VALUES ($$hola$$)` es un
/// literal perfectamente legible, y rechazarlo sería un falso positivo, que aquí significa dejar
/// un módulo sin instalar.
///
/// Se mira sobre el SQL **sin comentarios** y por tokens enteros: una columna `do_not_ship` o un
/// comentario que diga «function» no abren nada.
fn procedural_construct(statement: &str) -> Option<&'static str> {
    let cleaned = strip_comments(statement).to_uppercase();
    let tokens: Vec<&str> = cleaned.split_whitespace().map(bare_token).collect();

    if tokens.first() == Some(&"DO") {
        return Some("DO");
    }
    if tokens.first() == Some(&"CREATE") {
        let mut j = 1;
        while matches!(tokens.get(j), Some(&"OR") | Some(&"REPLACE")) {
            j += 1;
        }
        match tokens.get(j) {
            Some(&"FUNCTION") => return Some("CREATE FUNCTION"),
            Some(&"PROCEDURE") => return Some("CREATE PROCEDURE"),
            _ => {}
        }
    }
    None
}

/// Longitud del delimitador `$…$` que empieza en `at`, si de verdad lo es (hub#1149).
///
/// Un tag de Postgres es `$`, un identificador opcional (letra o `_` primero; después también
/// dígitos) y otro `$`. Comprobarlo es lo que separa `$$`/`$body$` —que abren un cuerpo— de un
/// `$1` o de un `$` suelto en un texto, que no abren nada.
fn dollar_tag_len(chars: &[char], at: usize) -> Option<usize> {
    if chars.get(at) != Some(&'$') {
        return None;
    }
    let mut j = at + 1;
    while let Some(&c) = chars.get(j) {
        if c == '$' {
            return Some(j + 1 - at);
        }
        let is_first = j == at + 1;
        if !(c.is_alphabetic() || c == '_' || (!is_first && c.is_ascii_digit())) {
            return None;
        }
        j += 1;
    }
    None
}

fn starts_with_tag(chars: &[char], at: usize, tag: &[char]) -> bool {
    chars.len() >= at + tag.len() && chars[at..at + tag.len()] == *tag
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
            // 🔑 `SET` tras un ancla NUNCA es una tabla (hub#1109). En `UPDATE <tabla> SET …` el
            // token siguiente es la tabla y el ancla acierta; en `ON CONFLICT … DO UPDATE SET …`
            // no hay tabla que anclar —va `SET`, palabra reservada— y esto concluía que el módulo
            // tocaba una tabla llamada `set`. Rechazaba así el upsert al INSTALAR, que es la forma
            // canónica de sembrar datos de referencia idempotentes. Mismo criterio que las otras
            // dos puertas: `validate-sql.mjs` y el espejo del toolkit (module-toolkit#72).
            if next_upper == "SET" {
                break;
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
/// Y respeta el **dollar-quoting** (`$$ … $$`, `$tag$ … $tag$`) desde hub#1149: sin eso el `;`
/// de dentro de un cuerpo lo partía y los inspectores decidían sobre trozos de algo que ya no era
/// la sentencia que Postgres iba a ejecutar. Un `$` que no abre un tag válido —`$1`, un precio—
/// sigue siendo texto corriente.
///
/// El comentario se conserva en la sentencia (se copia tal cual): quitarlo es cosa de
/// [`strip_comments`], en el momento de inspeccionar.
fn split_statements(sql: &str) -> Vec<String> {
    let chars: Vec<char> = sql.chars().collect();
    let mut out = Vec::new();
    let mut current = String::new();
    let mut i = 0;

    while i < chars.len() {
        let ch = chars[i];
        match ch {
            '\'' => {
                current.push(ch);
                i += 1;
                while i < chars.len() {
                    let c = chars[i];
                    current.push(c);
                    i += 1;
                    if c == '\'' {
                        break;
                    }
                }
            }
            '-' if chars.get(i + 1) == Some(&'-') => {
                while i < chars.len() {
                    let c = chars[i];
                    current.push(c);
                    i += 1;
                    if c == '\n' {
                        break;
                    }
                }
            }
            '/' if chars.get(i + 1) == Some(&'*') => {
                current.push('/');
                current.push('*');
                i += 2;
                let mut prev = ' ';
                while i < chars.len() {
                    let c = chars[i];
                    current.push(c);
                    i += 1;
                    if prev == '*' && c == '/' {
                        break;
                    }
                    prev = c;
                }
            }
            // 🔑 Dollar-quoting (hub#1149). Sin esto, el `;` de dentro de un `DO $$ … $$` partía
            // el bloque y los inspectores miraban trozos de algo que ya no era la sentencia que
            // Postgres iba a ejecutar. El cuerpo se copia **verbatim**, tal cual: aquí no se
            // reescribe nada, solo se decide dónde acaba la sentencia.
            '$' => match dollar_tag_len(&chars, i) {
                Some(len) => {
                    let tag: Vec<char> = chars[i..i + len].to_vec();
                    current.extend(tag.iter());
                    i += len;
                    while i < chars.len() {
                        if starts_with_tag(&chars, i, &tag) {
                            current.extend(tag.iter());
                            i += tag.len();
                            break;
                        }
                        current.push(chars[i]);
                        i += 1;
                    }
                }
                // Un `$` que no abre un tag es texto: `$1`, un precio, un nombre raro.
                None => {
                    current.push(ch);
                    i += 1;
                }
            },
            ';' => {
                if !current.trim().is_empty() {
                    out.push(current.trim().to_string());
                }
                current.clear();
                i += 1;
            }
            _ => {
                current.push(ch);
                i += 1;
            }
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
        check(
            "sales",
            "migrations/postgres/013_x.sql",
            sql,
            Kind::Contract,
        )
    }

    // ── La tabla pertenece al módulo ─────────────────────────────────────────────────

    /// Un `expand` **no se reescribe nunca**: su SQL sale tal cual.
    #[test]
    fn an_expand_is_applied_exactly_as_written() {
        assert_eq!(
            expand("CREATE TABLE sales_sale (id BIGINT)").unwrap(),
            Plan::AsWritten
        );
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

        assert!(
            matches!(refused, Err(GuardError::ForeignTable { .. })),
            "{refused:?}"
        );
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

        assert!(
            matches!(refused, Err(GuardError::ForeignTable { .. })),
            "{refused:?}"
        );
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

        assert!(
            matches!(refused, Err(GuardError::KindMismatch { .. })),
            "{refused:?}"
        );
    }

    #[test]
    fn a_backfill_may_not_change_the_schema() {
        let refused = check(
            "sales",
            "m.sql",
            "ALTER TABLE sales_sale ADD COLUMN total BIGINT",
            Kind::Backfill,
        );

        assert!(
            matches!(refused, Err(GuardError::KindMismatch { .. })),
            "{refused:?}"
        );
    }

    #[test]
    fn a_backfill_may_update_its_own_rows() {
        check(
            "sales",
            "m.sql",
            "UPDATE sales_sale SET total = 0 WHERE total IS NULL",
            Kind::Backfill,
        )
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

    /// `DROP COLUMN IF EXISTS` keeps its meaning — "nothing to do if it is not there" — without
    /// emitting `RENAME COLUMN IF EXISTS`, which Postgres does not have (hub#2108). The old
    /// assertion here (`contains("IF EXISTS") || contains("RENAME")`) passed with that broken SQL;
    /// the execution proof lives in `tests/contract_migration_drop_column_if_exists.rs`.
    #[test]
    fn drop_column_if_exists_becomes_a_guarded_rename_postgres_accepts() {
        let Plan::Rewritten(rewritten) =
            contract("ALTER TABLE sales_sale DROP COLUMN IF EXISTS tax_rate").unwrap()
        else {
            panic!("un contract se reescribe");
        };

        assert_eq!(
            rewritten,
            vec![
                "DO $erplora_set_aside$ BEGIN IF EXISTS (SELECT 1 FROM information_schema.columns \
                 WHERE table_schema = current_schema() AND table_name = 'sales_sale' \
                 AND column_name = 'tax_rate') THEN ALTER TABLE sales_sale RENAME COLUMN tax_rate \
                 TO _deprecated_tax_rate; END IF; END $erplora_set_aside$"
                    .to_string()
            ]
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
            rewritten[0]
                .ends_with("ALTER TABLE sales_old_line RENAME TO _deprecated_sales_old_line"),
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

        let escaped: Vec<&String> = rewritten
            .iter()
            .filter(|s| s.to_uppercase().contains("DROP "))
            .collect();
        assert!(
            escaped.is_empty(),
            "🔴 estos `DROP` se escaparon sin traducir: {escaped:?}"
        );
        assert!(
            rewritten[1].ends_with("RENAME TO _deprecated_sales_old_line"),
            "{rewritten:?}"
        );
        assert!(
            rewritten[2].ends_with("RENAME COLUMN legacy_total TO _deprecated_legacy_total"),
            "{rewritten:?}"
        );
        assert!(
            rewritten[3].ends_with("RENAME TO _deprecated_sales_old_cart"),
            "{rewritten:?}"
        );
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

    // ── Un `contract` retira ESTRUCTURA, no filas (hub#1145) ─────────────────────────

    /// 🔴 El agujero: `Kind::Contract` no comprobaba **ningún** verbo, y
    /// `set_aside_instead_of_dropping` solo sabe traducir `DROP TABLE`/`DROP COLUMN`. Un `TRUNCATE`
    /// salía por el `_ => statement` final y se ejecutaba tal cual sobre la BD de un cliente.
    #[test]
    fn a_contract_may_not_truncate() {
        let refused = contract("TRUNCATE sales_line").expect_err("un `contract` no vacía tablas");
        let message = refused.to_string();
        assert!(message.contains("TRUNCATE"), "{message}");
        assert!(
            message.contains("backfill"),
            "y dice por dónde SÍ se limpian filas: {message}"
        );
    }

    /// La otra mitad, y la que más se parece a un cambio inocente.
    #[test]
    fn a_contract_may_not_delete_rows() {
        for sql in [
            "DELETE FROM sales_line WHERE legacy = 'yes'",
            "DELETE FROM sales_line",
            // Un salto de línea entre el verbo y el `FROM` es la razón de mirar token a token en
            // vez de buscar la frase entera.
            "DELETE\n  FROM sales_line",
            "-- retirar lo viejo\nTRUNCATE TABLE sales_line",
        ] {
            let refused = contract(sql).expect_err("un `contract` no destruye filas");
            assert!(
                matches!(refused, GuardError::RowDestruction { .. }),
                "`{sql}` tenía que rechazarse por destruir filas: {refused}"
            );
        }
    }

    /// El mismo verbo en un `backfill` es **el camino que el error recomienda**, así que tiene que
    /// existir de verdad. Sin este test, «vete a un backfill» podría estar mandando a una puerta
    /// cerrada. `TRUNCATE` no: es incondicional y no lo admite ningún `kind`.
    #[test]
    fn deleting_rows_is_what_a_backfill_is_for() {
        check(
            "sales",
            "migrations/postgres/012_clean_legacy.sql",
            "DELETE FROM sales_line WHERE legacy = 'yes'",
            Kind::Backfill,
        )
        .expect("limpiar filas propias es DML, y el DML vive en un `backfill`");

        check("sales", "m.sql", "TRUNCATE sales_line", Kind::Backfill).expect_err(
            "un `TRUNCATE` no admite `WHERE` ni vuelta atrás: no cabe en ningún `kind`",
        );
    }

    /// 🔴 **Control de falsos positivos.** Un falso positivo aquí deja un módulo sin instalar, que
    /// es peor que el problema: por eso se comparan tokens enteros y `DELETE` solo cuenta con su
    /// `FROM` detrás. Las tres formas de abajo son SQL correcto y frecuente.
    #[test]
    fn words_that_only_look_like_a_destructive_verb_are_not_one() {
        for sql in [
            // `truncate_at` es una columna, no el verbo.
            "ALTER TABLE sales_line DROP COLUMN truncate_at",
            // `ON DELETE CASCADE` es una constraint: no borra nada al migrar.
            "ALTER TABLE sales_line ADD CONSTRAINT sales_line_sale_fk FOREIGN KEY (sale_id) \
             REFERENCES sales_sale (id) ON DELETE CASCADE",
            // La palabra dentro de un comentario tampoco es SQL.
            "-- esto NO hace TRUNCATE ni DELETE FROM nada\nDROP TABLE sales_line",
        ] {
            contract(sql).unwrap_or_else(|e| panic!("`{sql}` es correcto y tiene que pasar: {e}"));
        }
    }

    /// 🔴 **El radio de explosión de la regla es CERO**: las tres migraciones `contract` publicadas
    /// siguen pasando. La tercera es un `DROP CONSTRAINT`, que no toca ni una fila — meterlo en la
    /// regla pondría en rojo trabajo correcto ya publicado.
    #[test]
    fn the_three_published_contracts_still_pass() {
        let published = [
            ("services", "DROP TABLE IF EXISTS services_addon;\nDROP TABLE IF EXISTS services_addon_group"),
            ("services", "DROP TABLE IF EXISTS services_variant"),
            (
                "verifactu",
                "ALTER TABLE verifactu_gate DROP CONSTRAINT IF EXISTS verifactu_gate_ok;\n\
                 ALTER TABLE verifactu_gate ADD CONSTRAINT verifactu_gate_is_declared CHECK (ok = 1)",
            ),
        ];
        for (module, sql) in published {
            check(module, "migrations/postgres/099_x.sql", sql, Kind::Contract).unwrap_or_else(
                |e| panic!("`{module}` está publicado y tiene que seguir pasando: {e}"),
            );
        }
    }

    // ── Una sentencia entra, una sentencia sale (hub#1145) ───────────────────────────

    /// `DROP TABLE a, b;` es SQL válido, pero `ALTER TABLE … RENAME TO` acepta **una sola** tabla.
    /// Coger el primer nombre producía `ALTER TABLE a, RENAME TO _deprecated_a,` — un
    /// `syntax error at or near ","` que no explica nada, y `b` se quedaba sin retirar.
    #[test]
    fn a_drop_that_names_two_tables_is_refused_with_the_fix_in_the_message() {
        let refused = contract("DROP TABLE sales_a, sales_b")
            .expect_err("la traducción es de una sentencia a una sentencia");
        let message = refused.to_string();
        assert!(
            message.contains("una tabla por sentencia"),
            "el error tiene que decir qué escribir en su lugar: {message}"
        );
        assert!(
            message.contains("sales_a"),
            "y enseñar la sentencia que lo provoca: {message}"
        );
    }

    /// La misma grieta por el lado de la columna, que la issue no nombraba: un `ALTER` con más de
    /// una acción metía la coma dentro del `RENAME`.
    #[test]
    fn an_alter_with_more_than_one_action_is_refused_too() {
        for sql in [
            "ALTER TABLE sales_sale DROP COLUMN a, DROP COLUMN b",
            "ALTER TABLE sales_sale ADD COLUMN x TEXT, DROP COLUMN y",
        ] {
            let refused = contract(sql).expect_err("una acción por sentencia");
            assert!(
                refused.to_string().contains("una columna por sentencia"),
                "`{sql}`: {refused}"
            );
        }
    }

    /// Y lo que **no** es una lista sigue traduciéndose: `CASCADE` no lleva coma y se cae solo al
    /// renombrar, porque renombrar no arrastra a nadie.
    #[test]
    fn cascade_is_not_a_list_of_tables() {
        let Plan::Rewritten(rewritten) = contract("DROP TABLE sales_old CASCADE").unwrap() else {
            panic!("un contract se reescribe");
        };
        assert_eq!(
            rewritten,
            vec!["ALTER TABLE sales_old RENAME TO _deprecated_sales_old"]
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
        check(
            "printing",
            "migrations/postgres/002_jobs.sql",
            sql,
            Kind::Expand,
        )
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

        check(
            "sales",
            "migrations/postgres/013_drop_legacy_cart.sql",
            sql,
            Kind::Expand,
        )
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
        let refused = check(
            "sales",
            "migrations/postgres/099_nuevo.sql",
            "DROP TABLE sales_x",
            Kind::Expand,
        );

        assert!(
            matches!(refused, Err(GuardError::KindMismatch { .. })),
            "el pase es por FICHERO, no por módulo: {refused:?}"
        );
    }

    // ── Un upsert sobre tabla propia se INSTALA (hub#1109) ───────────────────────────

    /// 🔴 `tables_touched` anclaba **todo** `UPDATE`. En un `UPDATE <tabla> SET …` el token que
    /// sigue es la tabla y acierta; en `ON CONFLICT … DO UPDATE SET …` no hay tabla detrás del
    /// `UPDATE` —va `SET`, palabra reservada— y el guard concluía que el módulo tocaba una tabla
    /// llamada `set`, que no es suya. La puerta de INSTALACIÓN rechazaba así el upsert, que es la
    /// forma canónica de sembrar datos de referencia idempotentes.
    ///
    /// Importaba porque el espejo del toolkit ya no marcaba el falso positivo (module-toolkit#72):
    /// el gate daba VERDE a un upsert que ningún hub instalaba — módulo publicado verde, módulo
    /// que no instala, y el cliente quien lo descubre.
    #[test]
    fn an_upsert_on_its_own_table_installs() {
        let sql = "INSERT INTO taxes_category_label (key, lang, label, description) \
                   VALUES ('food', 'es', 'Alimentacion', 'Tipo reducido') \
                   ON CONFLICT (key, lang) DO UPDATE \
                   SET label = EXCLUDED.label, description = EXCLUDED.description";

        for kind in [Kind::Expand, Kind::Backfill] {
            let plan = check(
                "taxes",
                "migrations/postgres/005_category_labels.sql",
                sql,
                kind,
            )
            .unwrap_or_else(|e| {
                panic!("un upsert sobre la tabla del propio módulo instala ({kind:?}): {e}")
            });
            assert_eq!(plan, Plan::AsWritten, "y se aplica tal cual ({kind:?})");
        }
    }

    /// 🔴 **El ancla sigue cazando el positivo.** Arreglar el falso positivo no puede abrir la
    /// puerta: un `UPDATE` de verdad sobre la tabla de otro módulo se rechaza igual.
    #[test]
    fn an_update_on_another_modules_table_is_still_refused() {
        let refused = check(
            "taxes",
            "migrations/postgres/006_x.sql",
            "UPDATE sales_sale SET total = 0",
            Kind::Backfill,
        )
        .expect_err("la tabla de otro modulo no se toca");

        assert!(
            matches!(&refused, GuardError::ForeignTable { table, .. } if table == "sales_sale"),
            "tenia que rechazarse por tabla ajena: {refused}"
        );
    }

    // ── Lo que no se puede LEER no entra (hub#1149) ──────────────────────────────────

    /// 🔴 `split_statements` no entendía **dollar-quoting**, así que el `;` de dentro de un
    /// `DO $$ … $$` partía el bloque y los inspectores miraban trozos de algo que ya no era la
    /// sentencia que Postgres iba a ejecutar. Es la pieza que rompe primero.
    #[test]
    fn a_dollar_quoted_body_is_one_statement() {
        for sql in [
            "DO $$\nBEGIN\n  DELETE FROM sales_line WHERE legacy = 'yes';\nEND\n$$;",
            "CREATE FUNCTION sales_touch() RETURNS trigger AS $body$\nBEGIN\n  DELETE FROM sales_line;\n  RETURN NEW;\nEND\n$body$ LANGUAGE plpgsql;",
        ] {
            let statements = split_statements(sql);
            assert_eq!(
                statements.len(),
                1,
                "el cuerpo entre `$…$` es UNA sentencia, no {}: {statements:?}",
                statements.len()
            );
        }
    }

    /// 🔴 **El agujero de la issue.** El guard es un lint sobre el TEXTO y no puede afirmar nada
    /// de un cuerpo procedimental: dentro cabe `EXECUTE format('DROP TABLE %I', …)`, donde ni el
    /// verbo ni la tabla son tokens que leer. Así que no se inspecciona: se rechaza — «lo que no
    /// se puede apartar, no entra». Medido antes de escribirlo: **cero** de las 155 migraciones
    /// publicadas en los 27 repos usa un cuerpo procedimental, así que el radio de explosión es 0.
    #[test]
    fn a_procedural_body_does_not_enter_a_module_migration() {
        for sql in [
            "DO $$\nBEGIN\n  DELETE FROM sales_line WHERE legacy = 'yes';\nEND\n$$",
            "DO $limpia$ BEGIN EXECUTE 'DELETE FROM sales_line'; END $limpia$",
            "CREATE FUNCTION sales_touch() RETURNS trigger AS $$ BEGIN RETURN NEW; END $$ LANGUAGE plpgsql",
            "CREATE OR REPLACE FUNCTION sales_touch() RETURNS trigger AS $$ BEGIN RETURN NEW; END $$ LANGUAGE plpgsql",
            "CREATE PROCEDURE sales_clean() LANGUAGE plpgsql AS $$ BEGIN DELETE FROM sales_line; END $$",
        ] {
            for kind in [Kind::Expand, Kind::Backfill, Kind::Contract] {
                let refused = check("sales", "migrations/postgres/020_x.sql", sql, kind)
                    .err()
                    .unwrap_or_else(|| panic!("`{sql}` no es inspeccionable y no puede entrar ({kind:?})"));
                assert!(
                    matches!(refused, GuardError::NotInspectable { .. }),
                    "`{sql}` tenia que rechazarse por no inspeccionable ({kind:?}): {refused}"
                );
            }
        }
    }

    /// El error dice **qué** construcción y **por dónde** se sale, que es lo que separa un guard
    /// de un muro: un módulo sin instalar y sin explicación es el fallo caro.
    #[test]
    fn the_refusal_names_the_construct_and_the_way_out() {
        let refused = check(
            "sales",
            "migrations/postgres/020_x.sql",
            "DO $$ BEGIN PERFORM 1; END $$",
            Kind::Expand,
        )
        .expect_err("no inspeccionable");
        let message = refused.to_string();

        assert!(message.contains("DO"), "nombra la construccion: {message}");
        assert!(
            message.to_lowercase().contains("sql"),
            "y dice por donde SI se pasa: {message}"
        );
    }

    /// 🔴 **Control de falsos positivos**, que aquí valen un módulo sin instalar. Un `$$` dentro
    /// de un literal o de un comentario **no** abre un cuerpo procedimental, y una migración
    /// normal con un `$` suelto sigue pasando.
    #[test]
    fn words_that_only_look_like_a_dollar_quote_are_not_one() {
        for sql in [
            "INSERT INTO sales_line (label) VALUES ('$$ no es un cuerpo $$')",
            "-- el coste va en $$ y no abre nada\nCREATE TABLE sales_line (id BIGINT)",
            "CREATE TABLE sales_line (id BIGINT, note TEXT DEFAULT 'precio en $')",
        ] {
            check("sales", "migrations/postgres/021_x.sql", sql, Kind::Expand)
                .unwrap_or_else(|e| panic!("`{sql}` es SQL correcto y tiene que pasar: {e}"));
        }
    }

    /// Las migraciones de **sistema** son nuestras, se leen en una PR y no pasan por [`check`]:
    /// ahí un cuerpo procedimental sí cabe. Sin este control, la regla se habría llevado por
    /// delante la puerta de al lado.
    #[test]
    fn a_system_migration_may_still_use_a_procedural_body() {
        kind_matches("DO $$ BEGIN PERFORM 1; END $$", Kind::Expand)
            .expect("las de sistema son nuestras y se revisan en una PR");
    }

    // ── N/N-1: reshaping a column is not `expand` (hub#1163) ────────────────────────

    /// Regression test for ERPlora/hub#1163.
    ///
    /// 🔴 **This is the verb that takes the fleet down, not a screen.** With `start-first` and
    /// `endpointSpecSwarm: dnsrr` the new task and the old one serve at the same time against the
    /// SAME database, and `failure_action: rollback` gives back a hub that has ALREADY run the
    /// migrations of N. Rename a column and every query of N-1 that names it starts failing —
    /// against a schema no rollback undoes, because reverting does not run SQL (ADR-0269).
    ///
    /// It passed as `expand` because `destructive_verb` only knew the verbs that destroy DATA.
    /// A rename destroys no data at all: it destroys the PREVIOUS BINARY.
    #[test]
    fn rename_column_is_not_expand_hub1163() {
        let refused = expand("ALTER TABLE sales_sale RENAME COLUMN tax_rate TO tax_category_key");

        let GuardError::KindMismatch { found, .. } = refused.expect_err("un rename rompe N-1")
        else {
            panic!("tenía que ser un KindMismatch");
        };
        assert_eq!(found, "RENAME COLUMN");
    }

    /// Regression test for ERPlora/hub#1163. `ALTER TABLE … RENAME TO` is the same hole one level
    /// up: the whole table disappears from under N-1.
    #[test]
    fn rename_table_is_not_expand_hub1163() {
        let refused = expand("ALTER TABLE sales_sale RENAME TO sales_ticket");

        let GuardError::KindMismatch { found, .. } = refused.expect_err("un rename rompe N-1")
        else {
            panic!("tenía que ser un KindMismatch");
        };
        assert_eq!(found, "RENAME TO");
    }

    /// Regression test for ERPlora/hub#1163.
    ///
    /// The money migrations are the live proof: `ALTER COLUMN quantity TYPE BIGINT USING
    /// (quantity * 1000000)` leaves N-1 writing `1` where the schema now means one millionth.
    /// It is not a syntax error and it is not a crash — it is silently wrong data, which is worse.
    #[test]
    fn alter_column_type_is_not_expand_hub1163() {
        for sql in [
            "ALTER TABLE sales_sale ALTER COLUMN quantity TYPE BIGINT USING (quantity * 1000000)",
            "ALTER TABLE sales_sale ALTER COLUMN quantity SET DATA TYPE BIGINT",
        ] {
            let refused = expand(sql);

            let GuardError::KindMismatch { found, .. } =
                refused.expect_err("cambiar el tipo rompe N-1")
            else {
                panic!("tenía que ser un KindMismatch: `{sql}`");
            };
            assert_eq!(found, "ALTER COLUMN ... TYPE", "`{sql}`");
        }
    }

    /// The other `ALTER COLUMN` actions are NOT reshapes and must keep passing: `SET DEFAULT` /
    /// `DROP NOT NULL` widen what N-1 may write, they do not narrow it. A false positive here
    /// leaves a module uninstalled, which is the expensive direction.
    #[test]
    fn the_additive_alter_column_actions_still_pass_hub1163() {
        for sql in [
            "ALTER TABLE sales_sale ALTER COLUMN note SET DEFAULT ''",
            "ALTER TABLE sales_sale ALTER COLUMN note DROP DEFAULT",
            "ALTER TABLE sales_sale ALTER COLUMN note DROP NOT NULL",
            "ALTER TABLE sales_sale ADD COLUMN renamed_at TEXT",
            "CREATE TABLE sales_type (id BIGINT, rename_to TEXT)",
        ] {
            expand(sql).unwrap_or_else(|e| panic!("`{sql}` es aditivo y tiene que pasar: {e}"));
        }
    }

    /// Regression test for ERPlora/hub#1163.
    ///
    /// 🔴 **`COLUMN` is OPTIONAL in Postgres**, in both verbs: `ALTER TABLE t RENAME a TO b` and
    /// `ALTER TABLE t ALTER a TYPE BIGINT` are the very same reshapes, written the short way. A
    /// guard you get past by omitting a keyword is not a guard — and nobody omits it on purpose,
    /// which is what makes this the form that would have slipped through.
    #[test]
    fn the_implicit_column_forms_are_not_expand_either_hub1163() {
        for (sql, expected) in [
            (
                "ALTER TABLE sales_sale RENAME tax_rate TO tax_category_key",
                "RENAME COLUMN",
            ),
            (
                "ALTER TABLE sales_sale ALTER quantity TYPE BIGINT USING (quantity * 1000000)",
                "ALTER COLUMN ... TYPE",
            ),
            (
                "ALTER TABLE sales_sale ALTER quantity SET DATA TYPE BIGINT",
                "ALTER COLUMN ... TYPE",
            ),
        ] {
            let refused = expand(sql);

            let GuardError::KindMismatch { found, .. } =
                refused.expect_err("omitir `COLUMN` no lo hace aditivo")
            else {
                panic!("tenía que ser un KindMismatch: `{sql}`");
            };
            assert_eq!(found, expected, "`{sql}`");
        }
    }

    /// …and the negative control of that same widening: `RENAME CONSTRAINT` is OUT on purpose —
    /// it moves no data and no query names a constraint — and the implicit-`COLUMN` form must not
    /// drag it in. `SET DEFAULT` written short stays additive too.
    #[test]
    fn the_implicit_form_does_not_drag_in_what_is_additive_hub1163() {
        for sql in [
            "ALTER TABLE sales_sale RENAME CONSTRAINT sales_sale_fk TO sales_sale_fkey",
            "ALTER TABLE sales_sale ALTER note SET DEFAULT \'\'",
            "ALTER TABLE sales_sale ALTER note DROP NOT NULL",
        ] {
            expand(sql).unwrap_or_else(|e| panic!("`{sql}` es aditivo y tiene que pasar: {e}"));
        }
    }

    /// 🔴 Every verb in [`NOT_EXPAND`] has to be REACHABLE, named exactly as the catalogue names
    /// it. Without this the constant is prose: it could list a verb no statement ever trips, and
    /// `engine.snapshot` would freeze a promise the guard does not keep.
    #[test]
    fn every_not_expand_verb_is_reachable_by_its_own_name_hub1163() {
        let samples: &[(&str, &str)] = &[
            (
                "ALTER COLUMN ... TYPE",
                "ALTER TABLE sales_sale ALTER COLUMN qty TYPE BIGINT",
            ),
            ("DELETE FROM", "DELETE FROM sales_sale WHERE id = 1"),
            ("DROP COLUMN", "ALTER TABLE sales_sale DROP COLUMN total"),
            (
                "DROP CONSTRAINT",
                "ALTER TABLE sales_sale DROP CONSTRAINT sales_sale_fk",
            ),
            ("DROP TABLE", "DROP TABLE sales_sale"),
            (
                "RENAME COLUMN",
                "ALTER TABLE sales_sale RENAME COLUMN a TO b",
            ),
            ("RENAME TO", "ALTER TABLE sales_sale RENAME TO sales_ticket"),
            (
                "SET NOT NULL",
                "ALTER TABLE sales_sale ALTER COLUMN note SET NOT NULL",
            ),
            ("TRUNCATE", "TRUNCATE sales_sale"),
        ];
        for verb in NOT_EXPAND {
            let (_, sql) = samples
                .iter()
                .find(|(name, _)| name == verb)
                .unwrap_or_else(|| {
                    panic!("`{verb}` está en NOT_EXPAND y no tiene control positivo")
                });
            assert_eq!(
                destructive_verb(sql).as_deref(),
                Some(*verb),
                "`{sql}` tenía que salir como `{verb}`"
            );
        }
        assert_eq!(
            samples.len(),
            NOT_EXPAND.len(),
            "sobra o falta un control positivo: NOT_EXPAND tiene {} verbos",
            NOT_EXPAND.len()
        );
    }

    // ── The hatch is `kind: contract`, and it has to name its version ───────────────

    /// 🔴 **A comment is not a hatch.** hub#1137 already cost real data: prose above a `DROP`
    /// defeated the translation. So `-- contract: 1.4.0` inside a migration DECLARED `expand`
    /// changes nothing — the hatch is the declared `kind`, which is reviewable in the manifest,
    /// not a line of text anybody can paste.
    #[test]
    fn a_contract_marker_does_not_turn_an_expand_into_a_contract_hub1163() {
        let refused = expand(
            "-- contract: 1.4.0\n\
             ALTER TABLE sales_sale RENAME COLUMN tax_rate TO tax_category_key",
        );

        assert!(
            matches!(refused, Err(GuardError::KindMismatch { .. })),
            "la marca solo vale bajo `kind: contract`: {refused:?}"
        );
    }

    /// A `contract` that reshapes has to say from WHICH version it is safe. Until hub#1163 a
    /// `contract` was accepted in any version at all: nothing in the file said when the previous
    /// binary had stopped using what it retires, so nobody could tell whether the update window
    /// had been respected.
    #[test]
    fn a_contract_that_reshapes_must_name_its_version_hub1163() {
        let refused = contract("ALTER TABLE sales_sale RENAME COLUMN tax_rate TO tax_category_key");

        let GuardError::ContractWithoutVersion { verb } =
            refused.expect_err("un contract que reshapea declara su ventana")
        else {
            panic!("tenía que ser un ContractWithoutVersion");
        };
        assert_eq!(verb, "RENAME COLUMN");
    }

    /// …and with the marker it goes through, untouched: a rename is not a `DROP`, so there is
    /// nothing to translate.
    #[test]
    fn a_contract_that_names_its_version_may_reshape_hub1163() {
        let plan = contract(
            "-- Sales · 015 — the column moves to the tax catalogue key.\n\
             -- contract: 1.4.0\n\
             ALTER TABLE sales_sale RENAME COLUMN tax_rate TO tax_category_key",
        )
        .expect("declara su ventana");

        let Plan::Rewritten(statements) = plan else {
            panic!("un contract se reescribe");
        };
        assert!(
            statements[0].contains("RENAME COLUMN tax_rate TO tax_category_key"),
            "no hay nada que traducir en un rename: {statements:?}"
        );
    }

    /// The marker has to name a VERSION. `-- contract:` on its own, or followed by prose, is the
    /// author saying nothing while looking like they said something.
    #[test]
    fn a_contract_marker_without_a_version_does_not_count_hub1163() {
        for marker in [
            "-- contract:",
            "-- contract: pronto",
            "-- contract: v próxima",
        ] {
            let refused = contract(&format!(
                "{marker}\nALTER TABLE sales_sale RENAME COLUMN a TO b"
            ));

            assert!(
                matches!(refused, Err(GuardError::ContractWithoutVersion { .. })),
                "`{marker}` no nombra una versión: {refused:?}"
            );
        }
    }

    /// A `contract` that only retires structure (the 4 published ones) does NOT need the marker:
    /// the rule lands on the reshape, which is what breaks N-1. Widening it would put published,
    /// installed work in red for nothing.
    #[test]
    fn a_contract_that_only_drops_needs_no_version_hub1163() {
        contract("ALTER TABLE sales_sale DROP COLUMN tax_rate").expect("es el caso ya publicado");
        contract("DROP TABLE sales_old_line").expect("es el caso ya publicado");
    }

    // ── Blast radius: what is already published keeps installing ────────────────────

    /// 🔴 **The grandfathered list may only SHRINK.** It is the only thing stopping «grandfather
    /// it» from becoming the way to keep publishing what the contract forbids — same rule, same
    /// reason, as [`GRANDFATHERED`].
    #[test]
    fn the_reshape_grandfathered_list_may_only_shrink_hub1163() {
        assert!(
            RESHAPE_GRANDFATHERED.len() <= 12,
            "la lista de reshapes abuelados ha CRECIDO ({}). No se añade nada: una migración \
             nueva que renombra o cambia un tipo se declara `contract` y nombra su versión.",
            RESHAPE_GRANDFATHERED.len()
        );
    }

    /// The pass is for the RESHAPE and for nothing else: a grandfathered file that also destroys
    /// is still refused. Otherwise one entry in the list would reopen the whole door.
    #[test]
    fn a_grandfathered_reshape_is_still_refused_a_drop_hub1163() {
        let (module_id, filename) = RESHAPE_GRANDFATHERED[0];
        let refused = check(
            module_id,
            filename,
            &format!("ALTER TABLE {module_id}_thing DROP COLUMN total"),
            Kind::Expand,
        );

        assert!(
            matches!(refused, Err(GuardError::KindMismatch { .. })),
            "el pase es para el reshape, no para todo: {refused:?}"
        );
    }

    /// …and it is per FILE, not per module: the next migration of the same module inherits
    /// nothing. Same rule as [`GRANDFATHERED`], and the reason the pairs are `(module, file)`.
    #[test]
    fn the_reshape_pass_does_not_extend_to_the_next_migration_hub1163() {
        let (module_id, _) = RESHAPE_GRANDFATHERED[0];
        let refused = check(
            module_id,
            "migrations/postgres/999_brand_new.sql",
            &format!("ALTER TABLE {module_id}_thing RENAME COLUMN a TO b"),
            Kind::Expand,
        );

        assert!(
            matches!(refused, Err(GuardError::KindMismatch { .. })),
            "el pase es por fichero: {refused:?}"
        );
    }
}
