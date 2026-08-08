//! Subconjunto SQL permitido en el IMPORT de blueprints (ERPlora/hub#239).
//!
//! Los `data/*.sql` de un bundle se ejecutaban **crudos** (`seed::apply` → `execute_batch`): un
//! `.blueprint.zip` es un fichero que aporta el USUARIO, así que eso equivalía a dar `SQL
//! arbitrario` (DDL incluido: `DROP TABLE`, `ALTER`, `CREATE ROLE`…) a cualquiera que pudiera
//! subir un blueprint. El sha256 del manifest NO protege de esto: quien fabrica el bundle
//! también fabrica el manifest.
//!
//! Contrato: el import solo puede **insertar literales en las tablas de su propia sección**, que
//! es exactamente lo que el export produce (`export::rows_to_sql` emite únicamente
//! `INSERT INTO <tabla> (…) SELECT <literales> WHERE NOT EXISTS (SELECT 1 FROM <la misma tabla>
//! WHERE …)`). No basta con mirar el prefijo: se valida la **forma completa** de la sentencia
//! contra esa gramática mínima y todo lo demás se rechaza ANTES de tocar la BD:
//!  - **solo `INSERT INTO`** — nada de DDL (`CREATE`/`ALTER`/`DROP`/`TRUNCATE`/`GRANT`/`COPY`)
//!    ni `UPDATE`/`DELETE`. El esquema lo cambian las MIGRACIONES del módulo, no un blueprint;
//!  - **solo tablas de la sección** — `data/hub_users.sql` → `hub_user`;
//!    `data/hub_settings.sql` → `hub_settings`; `data/<módulo>.sql` → las tablas del módulo por
//!    la misma convención de prefijo con la que el export las eligió (`<id>` o `<id>_*`);
//!  - **solo literales como fuente** — `VALUES (…)` o `SELECT <literales>`. Un
//!    `INSERT INTO <tabla propia> SELECT … FROM hub_user` es léxicamente un INSERT en una tabla
//!    permitida, pero **exfiltra** datos de otra sección (hashes de PIN, certificados) a una
//!    tabla que el módulo sí puede leer luego. Igual de vetados: llamadas a función
//!    (`pg_read_file`, `current_setting`), CTEs que modifican
//!    (`INSERT INTO t … WITH x AS (DELETE …) SELECT …`, válido en PG), `ON CONFLICT DO UPDATE`
//!    con subconsulta y `RETURNING`. La única lectura permitida es la guarda de idempotencia
//!    `WHERE NOT EXISTS (SELECT 1 FROM <tabla de la sección> WHERE <col> = <literal>)`;
//!  - **sin comentarios de bloque** (`/* … */`), sin `$` (dollar-quoting de PG: el troceador no
//!    lo conoce ⇒ lo validado podría no ser lo ejecutado) ni literales sin cerrar.
//!
//! ⚠️ **Limitación conocida (anotada a propósito):** esto es una validación **léxica y de forma**,
//! no un parser SQL completo. Es defendible porque el conjunto legítimo es muy estrecho (una forma
//! de sentencia generada por nosotros) y porque falla CERRADO: cualquier token que la gramática no
//! contemple se rechaza. El confinamiento fuerte de verdad (rol Postgres por hub sin DDL + RLS) es
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
    /// ¿`table` pertenece a esta sección? La comparación pliega mayúsculas ASCII porque los dos
    /// motores lo hacen (Postgres pasa a minúsculas los identificadores sin comillas; SQLite es
    /// case-insensitive): `INSERT INTO HUB_USER` y `hub_user` son la MISMA tabla y no pueden
    /// significar cosas distintas para el validador. No depende del sistema de ficheros.
    ///
    /// **Suelo por debajo de todo scope** (ADR-0273 D8, hub#560): las tablas de SISTEMA del hub
    /// (`_hub_*` — perfil fiscal, registro de regímenes, certificado, lotes de import) no las
    /// alcanza ninguna sección. La regla del prefijo se las daría a una sección de módulo `_hub`,
    /// y el perfil fiscal es la IDENTIDAD de esta instalación: un bundle que pudiera escribirlo
    /// declararía el hub como ya activado o le cambiaría el `system_id`.
    pub fn allows(&self, table: &str) -> bool {
        if crate::export::is_system_table(table) {
            return false;
        }
        let table = table.to_ascii_lowercase();
        match self {
            Self::Exact(t) => table == t.to_ascii_lowercase(),
            Self::Module(id) => {
                let id = id.to_ascii_lowercase();
                table == id || table.starts_with(&format!("{id}_"))
            }
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
///
/// El `_` inicial queda fuera: es el namespace del RUNTIME (ADR-0273 D8, hub#560). Un
/// `data/_hub.sql` daría un scope `Module("_hub")`, que por la propia regla del prefijo alcanzaría
/// todas las `_hub_*` — el perfil fiscal del hub entre ellas. Ningún módulo se llama así, y ahora
/// tampoco puede llamarse así un fichero del bundle.
fn is_module_id(s: &str) -> bool {
    !s.is_empty()
        && !s.starts_with(crate::export::RESERVED_NAMESPACE_PREFIX)
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
            // Dollar-quoting de Postgres (`$$…$$`, `$tag$…$tag$`) y parámetros (`$1`): este
            // troceador NO los entiende, así que un `;` dentro de un `$$…$$` partiría donde el
            // motor no parte y lo VALIDADO dejaría de ser lo EJECUTADO. El export nunca emite `$`
            // fuera de un literal → se rechaza el batch entero (fail-closed).
            '$' => {
                return Err(
                    "`$` fuera de un literal (dollar-quoting) no permitido en los datos del bundle"
                        .into(),
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
        check_statement(stmt, scope)?;
    }
    Ok(stmts)
}

/// Token del subconjunto. Cualquier carácter que no produzca uno de estos se rechaza (fail-closed).
#[derive(Debug, Clone, PartialEq)]
enum Tok {
    /// Identificador sin comillas o palabra clave, tal cual se escribió.
    Word(String),
    /// Identificador entrecomillado (`"key"`).
    Quoted(String),
    /// Literal escalar: cadena `'…'` o número (`1`, `-2.5`, `1e10`).
    Lit,
    /// Puntuación del subconjunto: `(`, `)`, `,`, `=`, `*`, `;`.
    Punct(char),
}

impl Tok {
    /// ¿Es esta palabra clave (sin distinguir mayúsculas)?
    fn is_kw(&self, kw: &str) -> bool {
        matches!(self, Self::Word(w) if w.eq_ignore_ascii_case(kw))
    }
    /// Nombre de tabla/columna si el token es un identificador (o `None` si no lo es). Las
    /// palabras clave del subconjunto ya las consume el parser antes de llegar aquí.
    fn ident(&self) -> Option<&str> {
        match self {
            Self::Word(w) => Some(w),
            Self::Quoted(w) => Some(w),
            _ => None,
        }
    }
    /// ¿Vale como literal escalar? (`'…'`, número, `NULL`, `TRUE`, `FALSE`).
    fn is_literal(&self) -> bool {
        match self {
            Self::Lit => true,
            Self::Word(w) => ["null", "true", "false"]
                .contains(&w.to_ascii_lowercase().as_str()),
            _ => false,
        }
    }
}

/// Trocea UNA sentencia en tokens. `Err` con el carácter ofensivo si aparece algo que el
/// subconjunto no contempla (`$`, `.`, `:`, `[`…).
fn tokenize(stmt: &str) -> std::result::Result<Vec<Tok>, String> {
    let mut out = Vec::new();
    let mut chars = stmt.chars().peekable();
    while let Some(c) = chars.next() {
        match c {
            c if c.is_whitespace() => {}
            '\'' => {
                // Literal de cadena (el troceador ya garantizó que está cerrado).
                while let Some(q) = chars.next() {
                    if q == '\'' {
                        if chars.peek() == Some(&'\'') {
                            chars.next();
                        } else {
                            break;
                        }
                    }
                }
                out.push(Tok::Lit);
            }
            '"' => {
                let mut ident = String::new();
                loop {
                    match chars.next() {
                        Some('"') if chars.peek() == Some(&'"') => {
                            chars.next();
                            ident.push('"');
                        }
                        Some('"') | None => break,
                        Some(c) => ident.push(c),
                    }
                }
                out.push(Tok::Quoted(ident));
            }
            c if c.is_ascii_alphabetic() || c == '_' => {
                let mut w = String::from(c);
                while let Some(&n) = chars.peek() {
                    if n.is_ascii_alphanumeric() || n == '_' {
                        w.push(n);
                        chars.next();
                    } else {
                        break;
                    }
                }
                out.push(Tok::Word(w));
            }
            c if c.is_ascii_digit()
                || (c == '-' && chars.peek().is_some_and(|n| n.is_ascii_digit()))
                || (c == '+' && chars.peek().is_some_and(|n| n.is_ascii_digit())) =>
            {
                // Número: dígitos, punto decimal y notación científica (`1e-3`).
                let mut prev = c;
                while let Some(&n) = chars.peek() {
                    let cont = n.is_ascii_digit()
                        || n == '.'
                        || n == 'e'
                        || n == 'E'
                        || ((n == '-' || n == '+') && (prev == 'e' || prev == 'E'));
                    if !cont {
                        break;
                    }
                    prev = n;
                    chars.next();
                }
                out.push(Tok::Lit);
            }
            '(' | ')' | ',' | '=' | '*' | ';' => out.push(Tok::Punct(c)),
            other => {
                return Err(format!(
                    "carácter `{other}` no permitido en los datos del bundle"
                ))
            }
        }
    }
    Ok(out)
}

/// Valida la FORMA completa de una sentencia contra la gramática del subconjunto:
///
/// ```text
/// INSERT INTO <tabla> ( <col> {, <col>} )
///     ( VALUES ( <lit> {, <lit>} ) {, ( … )} | SELECT <lit> {, <lit>} )
///     [ WHERE NOT EXISTS ( SELECT 1 FROM <tabla> WHERE <col> ( = <lit> | IS NULL ) {AND …} ) ] ;
/// ```
///
/// Las dos `<tabla>` deben pertenecer al `scope`. Mirar solo el prefijo `INSERT INTO` no basta:
/// con eso pasaban `… SELECT pin_hash FROM hub_user` (exfiltración), `… WITH x AS (DELETE …)`
/// (borrado vía CTE, válido en PG) y `pg_read_file(…)`.
fn check_statement(stmt: &str, scope: &TableScope) -> std::result::Result<(), String> {
    let toks = tokenize(stmt).map_err(|e| shape_error(stmt, &e))?;
    let mut p = 0usize;
    // INSERT INTO <tabla>
    if !toks.get(p).is_some_and(|t| t.is_kw("INSERT")) || !toks.get(p + 1).is_some_and(|t| t.is_kw("INTO")) {
        return Err(format!(
            "solo se permiten sentencias `INSERT INTO` en los datos del bundle; se encontró: {}",
            preview(stmt)
        ));
    }
    p += 2;
    let table = toks
        .get(p)
        .and_then(Tok::ident)
        .ok_or_else(|| shape_error(stmt, "la tabla destino no es un identificador simple"))?;
    if crate::export::is_system_table(table) {
        return Err(system_table_error(table, "escribir en"));
    }
    if !scope.allows(table) {
        return Err(format!(
            "la sección solo puede escribir en {}; se encontró un INSERT en `{table}`",
            scope.describe()
        ));
    }
    p += 1;
    // ( <col> {, <col>} )
    p = idents_in_parens(&toks, p).ok_or_else(|| shape_error(stmt, "falta la lista de columnas"))?;
    // VALUES (…) {, (…)}  |  SELECT <literales>
    if toks.get(p).is_some_and(|t| t.is_kw("VALUES")) {
        p += 1;
        loop {
            p = literals_in_parens(&toks, p)
                .ok_or_else(|| shape_error(stmt, "los valores deben ser literales"))?;
            if toks.get(p) == Some(&Tok::Punct(',')) {
                p += 1;
            } else {
                break;
            }
        }
    } else if toks.get(p).is_some_and(|t| t.is_kw("SELECT")) {
        p += 1;
        p = literal_list(&toks, p).ok_or_else(|| {
            shape_error(
                stmt,
                "la fuente del INSERT solo puede ser una lista de literales (nada de `FROM`, \
                 subconsultas ni llamadas a función)",
            )
        })?;
    } else {
        return Err(shape_error(
            stmt,
            "tras las columnas solo se admite `VALUES (…)` o `SELECT <literales>`",
        ));
    }
    // Guarda de idempotencia opcional (la que emite el export).
    if toks.get(p).is_some_and(|t| t.is_kw("WHERE")) {
        p = not_exists_guard(&toks, p, scope, stmt)?;
    }
    // Solo puede quedar el `;` final.
    match toks.get(p) {
        Some(Tok::Punct(';')) if p + 1 == toks.len() => Ok(()),
        None => Ok(()),
        _ => Err(shape_error(
            stmt,
            "sobra texto tras el INSERT (p. ej. `ON CONFLICT`, `RETURNING` o una subconsulta)",
        )),
    }
}

/// Rechazo por tocar una tabla de SISTEMA del hub (ADR-0273 D8, hub#560). Mensaje propio, y no el
/// genérico del scope, porque el motivo es otro: no es «esta sección no llega ahí» sino «ahí no
/// llega ninguna sección» — el perfil fiscal y su registro de regímenes son la identidad de esta
/// instalación, no vocabulario del negocio que trae el bundle.
fn system_table_error(table: &str, verbo: &str) -> String {
    format!(
        "`{table}` es una tabla de SISTEMA del hub: ninguna sección de un bundle puede {verbo} el \
         perfil fiscal, el certificado ni los lotes de importación de esta instalación"
    )
}

/// Mensaje de rechazo por forma. Nombra siempre el subconjunto (`INSERT INTO`) para que el informe
/// del import explique el contrato, y recorta la sentencia para no volcar datos enteros.
fn shape_error(stmt: &str, detail: &str) -> String {
    format!(
        "los datos del bundle solo admiten `INSERT INTO <tabla> (…) VALUES/SELECT <literales>`: \
         {detail}; se encontró: {}",
        preview(stmt)
    )
}

/// `( <ident> {, <ident>} )` a partir de `p`; devuelve la posición siguiente al `)`.
fn idents_in_parens(toks: &[Tok], mut p: usize) -> Option<usize> {
    if toks.get(p) != Some(&Tok::Punct('(')) {
        return None;
    }
    p += 1;
    loop {
        toks.get(p)?.ident()?;
        p += 1;
        match toks.get(p) {
            Some(Tok::Punct(',')) => p += 1,
            Some(Tok::Punct(')')) => return Some(p + 1),
            _ => return None,
        }
    }
}

/// `( <lit> {, <lit>} )` a partir de `p`; devuelve la posición siguiente al `)`.
fn literals_in_parens(toks: &[Tok], mut p: usize) -> Option<usize> {
    if toks.get(p) != Some(&Tok::Punct('(')) {
        return None;
    }
    p += 1;
    let p = literal_list(toks, p)?;
    if toks.get(p) == Some(&Tok::Punct(')')) {
        Some(p + 1)
    } else {
        None
    }
}

/// `<lit> {, <lit>}` a partir de `p`; devuelve la posición del primer token que ya no forma parte.
fn literal_list(toks: &[Tok], mut p: usize) -> Option<usize> {
    loop {
        if !toks.get(p)?.is_literal() {
            return None;
        }
        p += 1;
        if toks.get(p) == Some(&Tok::Punct(',')) {
            p += 1;
        } else {
            return Some(p);
        }
    }
}

/// `WHERE NOT EXISTS ( SELECT 1 FROM <tabla> WHERE <col> (= <lit> | IS NULL) {AND …} )` — la ÚNICA
/// lectura que admite el subconjunto (la guarda de idempotencia del export), y solo sobre una
/// tabla de la propia sección.
fn not_exists_guard(
    toks: &[Tok],
    mut p: usize,
    scope: &TableScope,
    stmt: &str,
) -> std::result::Result<usize, String> {
    let bad = |detail: &str| shape_error(stmt, detail);
    let expect_kw = |p: usize, kw: &str| -> std::result::Result<usize, String> {
        if toks.get(p).is_some_and(|t| t.is_kw(kw)) {
            Ok(p + 1)
        } else {
            Err(bad("la única guarda admitida es `WHERE NOT EXISTS (SELECT 1 FROM … WHERE …)`"))
        }
    };
    p = expect_kw(p, "WHERE")?;
    p = expect_kw(p, "NOT")?;
    p = expect_kw(p, "EXISTS")?;
    if toks.get(p) != Some(&Tok::Punct('(')) {
        return Err(bad("falta el paréntesis de la guarda `NOT EXISTS`"));
    }
    p += 1;
    p = expect_kw(p, "SELECT")?;
    if !toks.get(p).is_some_and(Tok::is_literal) {
        return Err(bad("la guarda solo puede proyectar un literal (`SELECT 1`)"));
    }
    p += 1;
    p = expect_kw(p, "FROM")?;
    let table = toks
        .get(p)
        .and_then(Tok::ident)
        .ok_or_else(|| bad("la tabla de la guarda no es un identificador simple"))?;
    if crate::export::is_system_table(table) {
        return Err(system_table_error(table, "leer"));
    }
    if !scope.allows(table) {
        return Err(format!(
            "la sección solo puede leer {}; se encontró una guarda sobre `{table}`",
            scope.describe()
        ));
    }
    p += 1;
    p = expect_kw(p, "WHERE")?;
    // <col> = <lit> | <col> IS NULL, encadenados por AND.
    loop {
        toks.get(p)
            .and_then(Tok::ident)
            .ok_or_else(|| bad("la condición de la guarda debe comparar una columna"))?;
        p += 1;
        if toks.get(p) == Some(&Tok::Punct('=')) {
            if !toks.get(p + 1).is_some_and(Tok::is_literal) {
                return Err(bad(
                    "la condición de la guarda solo compara contra literales (nada de subconsultas)",
                ));
            }
            p += 2;
        } else if toks.get(p).is_some_and(|t| t.is_kw("IS"))
            && toks.get(p + 1).is_some_and(|t| t.is_kw("NULL"))
        {
            p += 2;
        } else {
            return Err(bad("condición no admitida en la guarda"));
        }
        if toks.get(p).is_some_and(|t| t.is_kw("AND")) {
            p += 1;
        } else {
            break;
        }
    }
    if toks.get(p) != Some(&Tok::Punct(')')) {
        return Err(bad("falta el cierre de la guarda `NOT EXISTS`"));
    }
    Ok(p + 1)
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

    /// EXFILTRACIÓN: un `INSERT` léxicamente válido en la tabla PERMITIDA cuya FUENTE es una tabla
    /// AJENA copia datos de otra sección (hashes de PIN, certificados…) a una tabla que el módulo
    /// sí puede leer después. El subconjunto solo admite literales como fuente.
    #[test]
    fn insert_que_lee_de_otra_tabla_se_rechaza() {
        let scope = TableScope::Exact("hub_settings".into());
        for sql in [
            "INSERT INTO hub_settings (\"hub_id\", \"key\", \"value\") SELECT 'h', 'robado', pin_hash FROM hub_user;",
            "INSERT INTO hub_settings (\"hub_id\", \"key\", \"value\") SELECT 'h', 'robado', value FROM _hub_certificate;",
            "INSERT INTO hub_settings (\"hub_id\", \"key\", \"value\") SELECT 'h', 'robado', usename FROM pg_user;",
            "INSERT INTO hub_settings (\"key\") SELECT 'x' WHERE NOT EXISTS (SELECT 1 FROM hub_user WHERE id = 'u1');",
            "INSERT INTO hub_settings (\"key\") SELECT 'x' WHERE NOT EXISTS (SELECT 1 FROM hub_settings WHERE \"key\" = (SELECT pin_hash FROM hub_user));",
            "INSERT INTO hub_settings SELECT * FROM hub_user;",
        ] {
            assert!(validate(sql, &scope).is_err(), "debería rechazarse: {sql}");
        }
    }

    /// CTE que MODIFICA dentro del INSERT (`INSERT INTO t … WITH x AS (DELETE …) SELECT …`): PG lo
    /// acepta, así que un filtro que solo mire el prefijo `INSERT INTO` deja pasar un DELETE.
    #[test]
    fn cte_que_modifica_dentro_del_insert_se_rechaza() {
        let scope = TableScope::Exact("hub_settings".into());
        let sql = "INSERT INTO hub_settings (\"key\") WITH victima AS (DELETE FROM hub_user RETURNING id) SELECT id FROM victima;";
        assert!(validate(sql, &scope).is_err());
    }

    /// Llamadas a función en la proyección (`pg_read_file`, `pg_sleep`, `dblink`): fuera del
    /// subconjunto — el export solo emite literales escalares.
    #[test]
    fn llamadas_a_funcion_se_rechazan() {
        let scope = TableScope::Exact("hub_settings".into());
        for sql in [
            "INSERT INTO hub_settings (\"hub_id\", \"key\", \"value\") SELECT 'h', 'x', pg_read_file('/etc/passwd');",
            "INSERT INTO hub_settings (\"hub_id\", \"key\", \"value\") SELECT 'h', 'x', current_setting('cloud.token');",
            "INSERT INTO hub_settings (\"hub_id\", \"key\", \"value\") VALUES ('h', 'x', pg_sleep(10));",
        ] {
            assert!(validate(sql, &scope).is_err(), "debería rechazarse: {sql}");
        }
    }

    /// `ON CONFLICT DO UPDATE` y `RETURNING` no los emite el export y abren escritura/lectura
    /// arbitraria (subconsultas en el SET): fuera del subconjunto.
    #[test]
    fn on_conflict_y_returning_se_rechazan() {
        let scope = TableScope::Exact("hub_settings".into());
        for sql in [
            "INSERT INTO hub_settings (\"key\", \"value\") VALUES ('a', 'b') ON CONFLICT (\"key\") DO UPDATE SET value = (SELECT pin_hash FROM hub_user);",
            "INSERT INTO hub_settings (\"key\", \"value\") VALUES ('a', 'b') RETURNING *;",
        ] {
            assert!(validate(sql, &scope).is_err(), "debería rechazarse: {sql}");
        }
    }

    /// Dollar-quoting de Postgres (`$$…$$`, `$tag$…$tag$`): el troceador no lo conoce, así que
    /// LO VALIDADO podría no ser LO EJECUTADO → se rechaza el `$` fuera de literal (fail-closed).
    #[test]
    fn dollar_quoting_se_rechaza() {
        let scope = TableScope::Exact("hub_settings".into());
        for sql in [
            "INSERT INTO hub_settings (\"key\") SELECT $$x; DROP TABLE hub_user$$;",
            "INSERT INTO hub_settings (\"key\") SELECT $tag$x$tag$;",
            "INSERT INTO hub_settings (\"key\") SELECT $1;",
        ] {
            let err = validate(sql, &scope).unwrap_err();
            assert!(err.contains('$'), "{sql} → {err}");
        }
    }

    /// Los caracteres «peligrosos» DENTRO de un literal son datos legítimos y no deben tumbar la
    /// sección: precios en dólares (`5$`), guiones dobles de un nombre, `/*` en una descripción.
    #[test]
    fn los_caracteres_especiales_dentro_del_literal_son_datos() {
        let scope = TableScope::Module("inventory".into());
        let sql = "INSERT INTO inventory_product (\"name\", \"note\") \
                   SELECT 'Menú 5$ -- oferta', 'usa /* y ; sin problema';";
        let stmts = validate(sql, &scope).expect("son datos, no sintaxis");
        assert_eq!(stmts.len(), 1, "{stmts:?}");
    }

    /// La forma legítima con `VALUES` (bundles no generados por el export) también se admite,
    /// siempre que los valores sean literales.
    #[test]
    fn la_forma_values_con_literales_se_acepta() {
        let scope = TableScope::Exact("hub_settings".into());
        let sql = "INSERT INTO hub_settings (\"hub_id\", \"key\", \"value\") VALUES ('h1', 'a', 'b'), ('h1', 'c', NULL);";
        assert_eq!(validate(sql, &scope).unwrap().len(), 1);
    }

    /// Las tres formas de guarda que emite `rows_to_sql` (por `id`, por `key`+`hub_id`, y la de
    /// tablas de VÍNCULO con `IS NULL`) siguen pasando: es el SQL real de un blueprint.
    #[test]
    fn las_tres_guardas_del_export_se_aceptan() {
        let scope = TableScope::Module("inventory".into());
        for sql in [
            "INSERT INTO inventory_product (\"id\", \"price\") SELECT 'p1', -12.5 WHERE NOT EXISTS (SELECT 1 FROM inventory_product WHERE id = 'p1');",
            "INSERT INTO inventory_product_tags (\"product_id\", \"tag\", \"note\") SELECT 'p1', 'x', NULL WHERE NOT EXISTS (SELECT 1 FROM inventory_product_tags WHERE \"product_id\" = 'p1' AND \"tag\" = 'x' AND \"note\" IS NULL);",
            "INSERT INTO inventory_product (\"id\", \"active\", \"stock\") SELECT 'p2', TRUE, 3 WHERE NOT EXISTS (SELECT 1 FROM inventory_product WHERE id = 'p2');",
        ] {
            assert!(validate(sql, &scope).is_ok(), "el SQL real del export: {sql}");
        }
    }

    /// **No section of a bundle writes a system table of the hub** — ADR-0273 D8 (hub#560).
    ///
    /// The floor is asked UNDER a scope that would otherwise allow it: `Module("_hub")` reaches
    /// `_hub_*` by the very prefix rule that decides what a module owns. That is the point — a rule
    /// that only holds because no module happens to be called `_hub` is not a rule.
    ///
    /// What is at stake is not one more table: `_hub_fiscal_profile` is the hub's fiscal identity
    /// (the tax id the chain is anchored to, its `system_id`, whether it has gone live) and
    /// `_hub_fiscal_regime_registry` is what says the country owes anything at all.
    #[test]
    fn a_bundle_never_writes_a_system_table() {
        let scope = TableScope::Module("_hub".into());
        for table in ["_hub_fiscal_profile", "_hub_fiscal_regime_registry", "_hub_certificate"] {
            assert!(!scope.allows(table), "`{table}` is out of reach of every section");
        }
        for sql in [
            "INSERT INTO _hub_fiscal_profile (\"hub_id\", \"status\") SELECT 'h2', 'ACTIVE';",
            "INSERT INTO _HUB_FISCAL_PROFILE (\"hub_id\", \"status\") SELECT 'h2', 'ACTIVE';",
            "INSERT INTO _hub_fiscal_regime_registry (\"country_code\", \"regime_key\") SELECT 'ES', '';",
            "INSERT INTO _hub_certificate (\"hub_id\", \"slot\") SELECT 'h2', 'own';",
            "INSERT INTO _hub_import_row (\"batch_id\", \"table_name\", \"row_id\") SELECT 'b', 't', 'r';",
        ] {
            assert!(validate(sql, &scope).is_err(), "should be refused: {sql}");
        }
        // And it cannot be READ either: the idempotence guard is a query, and a bundle that could
        // point it at the profile would leak whether this hub is live and under which tax id.
        let leak = "INSERT INTO _hub (\"a\") SELECT 'x' \
                    WHERE NOT EXISTS (SELECT 1 FROM _hub_fiscal_profile WHERE hub_id = 'h2');";
        assert!(validate(leak, &scope).is_err(), "a guard must not read a system table either");

        // …and the door BEFORE that one: a data file cannot even name the namespace, so a bundle
        // does not get to build the scope in the first place.
        assert_eq!(scope_for_data_file("data/_hub.sql"), None);
        assert_eq!(scope_for_data_file("data/_hub_fiscal_profile.sql"), None);
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
