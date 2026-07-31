//! Subconjunto SQL permitido en el IMPORT de blueprints (ERPlora/hub#239).
//!
//! Los `data/*.sql` de un bundle se ejecutaban **crudos** (`seed::apply` → `execute_batch`): un
//! `.blueprint.zip` es un fichero que aporta el USUARIO, así que eso equivalía a dar `SQL
//! arbitrario` (DDL incluido: `DROP TABLE`, `ALTER`, `CREATE ROLE`…) a cualquiera que pudiera
//! subir un blueprint. El sha256 del manifest NO protege de esto: quien fabrica el bundle
//! también fabrica el manifest.
//!
//! Contrato: el import solo puede **insertar filas en las tablas de su propia sección**, que es
//! exactamente lo que el export produce (`export::rows_to_sql` emite únicamente
//! `INSERT INTO <tabla> (…) SELECT … WHERE NOT EXISTS (…)`). Todo lo demás se rechaza ANTES de
//! tocar la BD:
//!  - **solo `INSERT INTO`** — nada de DDL (`CREATE`/`ALTER`/`DROP`/`TRUNCATE`/`GRANT`/`COPY`)
//!    ni `UPDATE`/`DELETE`. El esquema lo cambian las MIGRACIONES del módulo, no un blueprint;
//!  - **solo tablas de la sección** — `data/hub_users.sql` → `hub_user`;
//!    `data/hub_settings.sql` → `hub_settings`; `data/<módulo>.sql` → las tablas del módulo por
//!    la misma convención de prefijo con la que el export las eligió (`<id>` o `<id>_*`);
//!  - **sin comentarios de bloque** (`/* … */`) ni literales sin cerrar: son el vehículo clásico
//!    para colar una segunda sentencia en un parser léxico.
//!
//! ⚠️ **Limitación conocida (anotada a propósito):** esto es una validación **léxica**, no un
//! parser SQL completo. Es defendible porque el conjunto legítimo es muy estrecho (una forma de
//! sentencia generada por nosotros) y porque falla CERRADO: cualquier cosa que el lexer no sepa
//! trocear se rechaza. El confinamiento fuerte de verdad (rol Postgres por hub sin DDL + RLS) es
//! trabajo de provisioning del SaaS y queda fuera de este ámbito.

use erplora_db::DatabaseAdapter;

use crate::errors::{Result, RuntimeError};

/// Tablas que una sección del bundle puede tocar.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum TableScope {
    /// Sección a nivel hub: UNA tabla concreta.
    Exact(String),
    /// Sección de módulo: sus tablas por convención de prefijo (`<id>` o `<id>_*`), la misma
    /// regla con la que `export::table_owner` decide qué volcar.
    Module(String),
}

impl TableScope {
    /// ¿`table` pertenece a esta sección?
    pub fn allows(&self, table: &str) -> bool {
        match self {
            Self::Exact(t) => table == t,
            Self::Module(id) => table == id || table.starts_with(&format!("{id}_")),
        }
    }

    /// Descripción legible para el mensaje de rechazo.
    pub fn describe(&self) -> String {
        match self {
            Self::Exact(t) => format!("`{t}`"),
            Self::Module(id) => format!("las tablas del módulo `{id}` (`{id}`/`{id}_*`)"),
        }
    }
}

/// Scope de un fichero de datos del bundle a partir de su RUTA (`data/…`).
///
/// `None` = ruta que el export nunca produce → el llamador la rechaza (un bundle no puede
/// inventarse ficheros de datos).
pub fn scope_for_data_file(path: &str) -> Option<TableScope> {
    let name = path.strip_prefix("data/")?.strip_suffix(".sql")?;
    if name.contains('/') {
        return None; // `data/fiscal/…` no es SQL; nada anidado es una sección de datos.
    }
    match name {
        "hub_users" => Some(TableScope::Exact("hub_user".into())),
        "hub_settings" => Some(TableScope::Exact("hub_settings".into())),
        id if is_module_id(id) => Some(TableScope::Module(id.to_string())),
        _ => None,
    }
}

/// Id de módulo aceptable como nombre de fichero de sección (mismo alfabeto que un identificador
/// SQL seguro: sin puntos, comillas ni separadores).
fn is_module_id(s: &str) -> bool {
    !s.is_empty()
        && s.chars()
            .all(|c| c.is_ascii_alphanumeric() || c == '_' || c == '-')
}

/// Parte un batch SQL en sentencias **respetando los literales**: un `;` dentro de `'…'` (o de un
/// identificador `"…"`) no separa. Quita los comentarios de línea `--` fuera de literales.
///
/// A diferencia del split ingenuo de [`crate::seed`], aquí importa que lo VALIDADO sea
/// exactamente lo EJECUTADO: si el troceo difiere del que ve el motor, la validación no vale nada.
/// Por eso este módulo también ejecuta ([`apply`]).
///
/// `Err` si el batch termina con un literal/identificador sin cerrar o si aparece un comentario
/// de bloque `/* … */` (fail-closed: el export nunca los emite).
pub fn split_statements(sql: &str) -> std::result::Result<Vec<String>, String> {
    let mut out = Vec::new();
    let mut current = String::new();
    let mut chars = sql.chars().peekable();
    // Estado del lexer: fuera de literal, dentro de `'…'` o dentro de `"…"`.
    let (mut in_single, mut in_double) = (false, false);
    while let Some(c) = chars.next() {
        if in_single {
            current.push(c);
            if c == '\'' {
                if chars.peek() == Some(&'\'') {
                    current.push(chars.next().unwrap()); // `''` = comilla escapada
                } else {
                    in_single = false;
                }
            }
            continue;
        }
        if in_double {
            current.push(c);
            if c == '"' {
                if chars.peek() == Some(&'"') {
                    current.push(chars.next().unwrap()); // `""` = comilla escapada
                } else {
                    in_double = false;
                }
            }
            continue;
        }
        match c {
            '\'' => {
                in_single = true;
                current.push(c);
            }
            '"' => {
                in_double = true;
                current.push(c);
            }
            '-' if chars.peek() == Some(&'-') => {
                // Comentario de línea: se descarta hasta el fin de línea.
                for c in chars.by_ref() {
                    if c == '\n' {
                        current.push('\n');
                        break;
                    }
                }
            }
            '/' if chars.peek() == Some(&'*') => {
                return Err(
                    "comentario de bloque `/* … */` no permitido en los datos del bundle".into(),
                );
            }
            ';' => {
                push_statement(&mut out, &mut current);
            }
            _ => current.push(c),
        }
    }
    if in_single || in_double {
        return Err("literal SQL sin cerrar en los datos del bundle".into());
    }
    push_statement(&mut out, &mut current);
    Ok(out)
}

/// Vuelca `current` como sentencia (con su `;`) si no está en blanco, y lo vacía.
fn push_statement(out: &mut Vec<String>, current: &mut String) {
    let stmt = current.trim();
    if !stmt.is_empty() {
        out.push(format!("{stmt};"));
    }
    current.clear();
}

/// Valida `sql` contra el subconjunto permitido para `scope` y devuelve las sentencias a
/// ejecutar (exactamente las validadas). `Err(mensaje)` = bundle rechazado.
pub fn validate(sql: &str, scope: &TableScope) -> std::result::Result<Vec<String>, String> {
    let stmts = split_statements(sql)?;
    for stmt in &stmts {
        let table = insert_target(stmt).ok_or_else(|| {
            format!(
                "solo se permiten sentencias `INSERT INTO` en los datos del bundle; se encontró: {}",
                preview(stmt)
            )
        })?;
        if !scope.allows(&table) {
            return Err(format!(
                "la sección solo puede escribir en {}; se encontró un INSERT en `{table}`",
                scope.describe()
            ));
        }
    }
    Ok(stmts)
}

/// Tabla destino de un `INSERT INTO <tabla>` (identificador simple, con o sin comillas dobles).
/// `None` si la sentencia no es un INSERT o el destino no es un identificador simple (esquema
/// cualificado, función, subconsulta…).
fn insert_target(stmt: &str) -> Option<String> {
    let rest = strip_keyword(stmt.trim_start(), "INSERT")?;
    let rest = strip_keyword(rest.trim_start(), "INTO")?;
    let rest = rest.trim_start();
    let mut chars = rest.chars();
    let (ident, next) = match chars.next()? {
        '"' => {
            let mut ident = String::new();
            loop {
                match chars.next()? {
                    '"' => break,
                    c => ident.push(c),
                }
            }
            (ident, chars.next())
        }
        c if c.is_ascii_alphabetic() || c == '_' => {
            let mut ident = String::from(c);
            let mut next = None;
            for c in chars.by_ref() {
                if c.is_ascii_alphanumeric() || c == '_' {
                    ident.push(c);
                } else {
                    next = Some(c);
                    break;
                }
            }
            (ident, next)
        }
        _ => return None,
    };
    // Tras el identificador solo puede venir la lista de columnas o espacio: un `.` significa
    // destino cualificado por esquema (`public.x`, `pg_catalog.y`) → fuera del subconjunto.
    match next {
        None => Some(ident),
        Some(c) if c.is_whitespace() || c == '(' => Some(ident),
        Some(_) => None,
    }
}

/// Consume `kw` (sin distinguir mayúsculas) al principio de `s` exigiendo separador después.
fn strip_keyword<'a>(s: &'a str, kw: &str) -> Option<&'a str> {
    if s.len() < kw.len() || !s[..kw.len()].eq_ignore_ascii_case(kw) {
        return None;
    }
    let rest = &s[kw.len()..];
    match rest.chars().next() {
        Some(c) if c.is_whitespace() => Some(rest),
        _ => None,
    }
}

/// Recorte legible de una sentencia para el mensaje de error (sin volcar datos enteros).
fn preview(stmt: &str) -> String {
    let one_line = stmt.split_whitespace().collect::<Vec<_>>().join(" ");
    if one_line.chars().count() > 80 {
        format!("{}…", one_line.chars().take(80).collect::<String>())
    } else {
        one_line
    }
}

/// Valida y aplica el SQL de una sección del bundle. Devuelve cuántas sentencias ejecutó.
///
/// La validación va ANTES de tocar la BD: un bundle con DDL no ejecuta ni su primera fila.
pub async fn apply(db: &dyn DatabaseAdapter, sql: &str, scope: &TableScope) -> Result<usize> {
    let stmts = validate(sql, scope).map_err(RuntimeError::Other)?;
    let mut applied = 0usize;
    for (i, stmt) in stmts.iter().enumerate() {
        db.execute_batch(stmt).await.map_err(|e| {
            RuntimeError::Other(format!(
                "import: fallo en la sentencia #{} de {}: {e}",
                i + 1,
                stmts.len()
            ))
        })?;
        applied += 1;
    }
    Ok(applied)
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Forma REAL que emite el export (`rows_to_sql`): INSERT idempotente con guard NOT EXISTS.
    const EXPORTED: &str = "INSERT INTO hub_settings (\"hub_id\", \"key\", \"value\") \
         SELECT '__HUB_ID__', 'business_name', 'Bar Paco' \
         WHERE NOT EXISTS (SELECT 1 FROM hub_settings WHERE \"key\" = 'business_name');";

    #[test]
    fn el_sql_que_produce_el_export_se_acepta() {
        let scope = TableScope::Exact("hub_settings".into());
        let stmts = validate(EXPORTED, &scope).expect("el SQL del export es válido");
        assert_eq!(stmts.len(), 1);
    }

    #[test]
    fn el_ddl_se_rechaza() {
        let scope = TableScope::Exact("hub_settings".into());
        for ddl in [
            "DROP TABLE hub_settings;",
            "ALTER TABLE hub_settings ADD COLUMN x TEXT;",
            "CREATE TABLE evil (id TEXT);",
            "TRUNCATE hub_settings;",
            "GRANT ALL ON hub_settings TO PUBLIC;",
            "COPY hub_settings FROM '/etc/passwd';",
            "CREATE ROLE evil SUPERUSER;",
        ] {
            let err = validate(ddl, &scope).unwrap_err();
            assert!(err.contains("INSERT INTO"), "{ddl} → {err}");
        }
    }

    #[test]
    fn update_delete_y_select_se_rechazan() {
        let scope = TableScope::Exact("hub_settings".into());
        for sql in [
            "UPDATE hub_settings SET value = 'x';",
            "DELETE FROM hub_settings;",
            "SELECT pg_sleep(10);",
        ] {
            assert!(validate(sql, &scope).is_err(), "{sql} debería rechazarse");
        }
    }

    /// El vector clásico: una sentencia legítima seguida de otra colada tras el `;`.
    #[test]
    fn una_segunda_sentencia_colada_tras_el_punto_y_coma_se_rechaza() {
        let scope = TableScope::Exact("hub_settings".into());
        let sql = format!("{EXPORTED} DROP TABLE hub_user;");
        let err = validate(&sql, &scope).unwrap_err();
        assert!(err.contains("INSERT INTO"), "{err}");
    }

    #[test]
    fn insertar_en_otra_tabla_de_la_seccion_se_rechaza() {
        let scope = TableScope::Exact("hub_settings".into());
        let sql = "INSERT INTO hub_user (id, name, role) SELECT 'x', 'Mallory', 'owner';";
        let err = validate(sql, &scope).unwrap_err();
        assert!(err.contains("hub_user"), "{err}");
    }

    #[test]
    fn una_seccion_de_modulo_solo_toca_sus_tablas() {
        let scope = TableScope::Module("inventory".into());
        assert!(scope.allows("inventory"));
        assert!(scope.allows("inventory_product"));
        assert!(scope.allows("inventory_product_categories"));
        assert!(!scope.allows("inventoryx"));
        assert!(!scope.allows("hub_user"));

        let ok = "INSERT INTO inventory_product (id) SELECT 'p1';";
        assert!(validate(ok, &scope).is_ok());
        let ko = "INSERT INTO hub_user (id) SELECT 'u1';";
        assert!(validate(ko, &scope).is_err());
    }

    /// Destino cualificado por esquema: fuera del subconjunto (el export nunca lo emite).
    #[test]
    fn destino_cualificado_por_esquema_se_rechaza() {
        let scope = TableScope::Module("inventory".into());
        assert!(validate("INSERT INTO public.inventory_product (id) SELECT 'p1';", &scope).is_err());
    }

    /// Un `;` DENTRO de un literal no parte la sentencia (dato legítimo: «Café; té»).
    #[test]
    fn el_punto_y_coma_dentro_de_un_literal_no_parte() {
        let scope = TableScope::Module("inventory".into());
        let sql = "INSERT INTO inventory_product (\"name\") SELECT 'Café; té';";
        let stmts = validate(sql, &scope).expect("el `;` del dato no parte la sentencia");
        assert_eq!(stmts.len(), 1, "{stmts:?}");
        assert!(stmts[0].contains("Café; té"));
    }

    /// Comilla escapada `''` dentro del literal (lo que emite `sql_literal`).
    #[test]
    fn comilla_escapada_dentro_del_literal() {
        let scope = TableScope::Module("inventory".into());
        let sql = "INSERT INTO inventory_product (\"name\") SELECT 'L''Oréal; 50%';";
        let stmts = validate(sql, &scope).expect("comilla escapada válida");
        assert_eq!(stmts.len(), 1, "{stmts:?}");
    }

    #[test]
    fn comentarios_de_linea_fuera_de_literal_se_descartan() {
        let scope = TableScope::Exact("hub_settings".into());
        let sql = format!("-- volcado del hub; generado\n{EXPORTED}\n-- fin;\n");
        let stmts = validate(&sql, &scope).expect("los comentarios no son sentencias");
        assert_eq!(stmts.len(), 1, "{stmts:?}");
    }

    #[test]
    fn comentario_de_bloque_y_literal_sin_cerrar_se_rechazan() {
        assert!(split_statements("INSERT INTO t /* ; */ (a) SELECT 1;").is_err());
        assert!(split_statements("INSERT INTO t (a) SELECT 'sin cerrar;").is_err());
    }

    #[test]
    fn el_scope_sale_de_la_ruta_del_fichero() {
        assert_eq!(
            scope_for_data_file("data/hub_users.sql"),
            Some(TableScope::Exact("hub_user".into()))
        );
        assert_eq!(
            scope_for_data_file("data/hub_settings.sql"),
            Some(TableScope::Exact("hub_settings".into()))
        );
        assert_eq!(
            scope_for_data_file("data/inventory.sql"),
            Some(TableScope::Module("inventory".into()))
        );
        // Rutas que el export nunca produce → sin scope (el import las rechaza).
        assert_eq!(scope_for_data_file("data/fiscal/evil.sql"), None);
        assert_eq!(scope_for_data_file("data/../evil.sql"), None);
        assert_eq!(scope_for_data_file("media/foo.sql"), None);
        assert_eq!(scope_for_data_file("data/fiscal/certificate.p12"), None);
    }
}
