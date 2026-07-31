//! Import de un blueprint en el hub (ADR-0113): restaura las secciones SELECCIONADAS de un
//! bundle (manifest + `data/*.sql`) inyectando el `hub_id` DESTINO (patrón ADR-0072), estilo
//! «migrate» de Django. La instalación de los módulos del manifest es del SERVER (flujo
//! `install_from_cloud`, ANTES de llamar aquí); este motor solo aplica datos.
//!
//! BEST-EFFORT (decisión Ioan): una sección que falla se registra en el informe y NO rompe
//! el resto. La INTEGRIDAD sí es dura: sha256 que no casa o `schema_version` desconocida →
//! rechazo entero SIN efectos (patrón ADR-0015: verificar antes de tocar nada).
//!
//! PROPUESTA de superficie (firma = contrato de los e2e `tests/import_test.rs`).
//! La implementación es columna del humano (plan Fase 2); este stub solo fija el contrato.

use std::collections::BTreeMap;

use serde::{Deserialize, Serialize};

use crate::export::BlueprintManifest;
use crate::Runtime;

/// Selección del formulario de import (checkboxes sobre lo que el bundle trae).
#[derive(Debug, Clone, Default)]
pub struct ImportSelection {
    /// Aplicar `data/hub_users.sql` (empleados + roles + permisos).
    pub users: bool,
    /// Aplicar `data/hub_settings.sql`.
    pub settings: bool,
    /// Restaurar `data/fiscal/` (config VeriFactu + certificado). El certificado lo aplica
    /// el server por su endpoint existente; aquí solo se contabiliza en el informe.
    pub fiscal: bool,
    /// Copiar `media/` (lo hace el server con el gestor media; aquí solo informe).
    pub media: bool,
    /// Módulos cuyos `data/<id>.sql` se aplican (deben estar instalados en destino).
    pub modules: Vec<String>,
}

/// Estado final de una sección tras el import (informe best-effort).
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub enum SectionStatus {
    /// Aplicada correctamente.
    Applied,
    /// No seleccionada (o ausente del bundle): no se tocó.
    Skipped,
    /// Falló; el motivo es legible para el informe de la UI. El resto del import continuó.
    Failed(String),
}

/// Resultado por sección (`hub_users`, `hub_settings`, `fiscal`, `media`, `modules/<id>`).
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct SectionResult {
    pub section: String,
    pub status: SectionStatus,
}

/// Informe final del import: una entrada por sección del bundle (la UI lo pinta tal cual).
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq, Default)]
pub struct ImportReport {
    pub sections: Vec<SectionResult>,
}

/// Aplica en el hub las secciones seleccionadas del bundle, bajo el tenant `target_hub_id`
/// (explícito: el import restaura en el hub DESTINO, que no tiene por qué ser el del runtime
/// de pruebas; en producción el server pasa el `hub_id` del despliegue).
///
/// Contrato (fijado por los e2e): verifica `schema_version` y los sha256 del manifest ANTES
/// de aplicar nada (fallo → `Err` sin efectos); después aplica sección a sección con el
/// `hub_id` destino inyectado (via [`crate::export::HUB_ID_PLACEHOLDER`]), best-effort, y
/// devuelve el informe. Una sección de un módulo no instalado falla nombrándolo.
pub async fn import_sections(
    rt: &mut Runtime,
    manifest: &BlueprintManifest,
    files: &BTreeMap<String, Vec<u8>>,
    selection: &ImportSelection,
    target_hub_id: &str,
) -> crate::Result<ImportReport> {
    // ── Integridad DURA, antes de tocar nada (ADR-0015) ─────────────────────
    if manifest.schema_version != crate::export::SCHEMA_VERSION {
        return Err(crate::RuntimeError::Other(format!(
            "import: schema_version {} desconocida (este runtime entiende v{})",
            manifest.schema_version,
            crate::export::SCHEMA_VERSION
        )));
    }
    for (path, bytes) in files {
        match manifest.sha256.get(path) {
            Some(expected) if *expected == crate::export::sha256_hex(bytes) => {}
            Some(_) => {
                return Err(crate::RuntimeError::Other(format!(
                    "import: sha256 de {path} no casa con el manifest — bundle manipulado, rechazado sin efectos"
                )))
            }
            None => {
                return Err(crate::RuntimeError::Other(format!(
                    "import: {path} no aparece en manifest.sha256 — bundle inconsistente, rechazado"
                )))
            }
        }
    }
    for path in manifest.sha256.keys() {
        if !files.contains_key(path) {
            return Err(crate::RuntimeError::Other(format!(
                "import: el manifest declara {path} pero el bundle no lo trae — rechazado"
            )));
        }
    }

    // ── Aplicación sección a sección, BEST-EFFORT (decisión Ioan) ───────────
    // Cada sección valida su SQL contra el subconjunto permitido ANTES de ejecutar nada de ella
    // (`import_sql`, hub#239): DDL o un INSERT en tablas de otra sección dejan la sección entera
    // en `Failed` sin tocar la BD. NO se aborta el import: el best-effort es la decisión de
    // producto (una sección rota no rompe el resto) y la garantía de seguridad —que ese SQL no se
    // ejecute— se cumple igual.
    // Un lote por importación, con el nombre del blueprint: es la unidad que el usuario
    // reconoce y deshace («quitar la demo del restaurante»). Si el registro del lote falla, el
    // import NO se aborta — se pierde la trazabilidad, no los datos.
    let batch_id = crate::reset::begin_batch(rt, target_hub_id, &manifest.name).await.ok();

    let mut report = ImportReport::default();
    for section in &manifest.sections {
        let status =
            apply_section(rt, section, files, selection, target_hub_id, batch_id.as_deref()).await;
        report.sections.push(SectionResult { section: section.clone(), status });
    }
    Ok(report)
}

/// Aplica una sección; cualquier fallo queda contenido en su `SectionStatus::Failed`.
async fn apply_section(
    rt: &Runtime,
    section: &str,
    files: &BTreeMap<String, Vec<u8>>,
    selection: &ImportSelection,
    target_hub_id: &str,
    batch_id: Option<&str>,
) -> SectionStatus {
    // ¿Está marcada en el formulario de import?
    let (selected, path): (bool, Option<String>) = match section {
        "hub_users" => (selection.users, Some("data/hub_users.sql".into())),
        "hub_settings" => (selection.settings, Some("data/hub_settings.sql".into())),
        // fiscal/media las materializa el SERVER (certificado por su endpoint, imágenes por el
        // gestor media); a nivel runtime se registran como Skipped y el server sobrescribe.
        "fiscal" => (false, None),
        "media" => (false, None),
        s => {
            if let Some(id) = s.strip_prefix("modules/") {
                (selection.modules.iter().any(|m| m == id), Some(format!("data/{id}.sql")))
            } else {
                (false, None)
            }
        }
    };
    if !selected {
        return SectionStatus::Skipped;
    }

    // Un módulo del manifest debe estar instalado en destino (lo instala el server ANTES).
    if let Some(id) = section.strip_prefix("modules/") {
        if !rt.registry().is_installed(id) {
            return SectionStatus::Failed(format!("módulo `{id}` no instalado en el hub destino"));
        }
    }

    let Some(path) = path else { return SectionStatus::Skipped };
    let Some(bytes) = files.get(&path) else {
        return SectionStatus::Failed(format!("fichero {path} ausente del bundle"));
    };
    let sql = match std::str::from_utf8(bytes) {
        Ok(s) => s.replace(crate::export::HUB_ID_PLACEHOLDER, target_hub_id),
        Err(_) => return SectionStatus::Failed(format!("{path} no es UTF-8 válido")),
    };
    if sql.trim().is_empty() {
        return SectionStatus::Applied; // sección presente pero sin filas: nada que hacer
    }
    // Subconjunto SQL del import (hub#239): la sección se valida ENTERA antes de ejecutar su
    // primera fila (solo `INSERT INTO` en sus propias tablas). Validar y ejecutar viven en la
    // misma función para que lo validado sea EXACTAMENTE lo ejecutado (mismo troceo).
    let Some(scope) = crate::import_sql::scope_for_data_file(&path) else {
        return SectionStatus::Failed(format!("{path} no corresponde a ninguna sección conocida"));
    };
    // REGENERAR los `id` del bundle por el hub DESTINO y acotar la guarda por (hub_id, id)
    // (hub#260): en una BD COMPARTIDA por varios hubs de una misma org, los `id` del hub ORIGEN
    // ya existen (bajo un hub hermano) y el INSERT chocaba contra la PK global, o el guard por
    // `id` solo evaluaba a falso y la sección insertaba 0 filas reportando `Applied` (fallo
    // silencioso). La PK de casi toda tabla de módulo es `id TEXT PRIMARY KEY` GLOBAL (no
    // `(hub_id, id)`), así que reutilizar el id de origen es inviable: se genera un uuid NUEVO
    // por fila y se remapean las FK internas del bundle (cualquier columna `id`/`*_id`/`parent_id`
    // cuyo literal apunte a un id reescrito). La guarda pasa a `hub_id = <dest> AND id = <nuevo>`,
    // que sigue siendo idempotente para una re-importación sobre el MISMO hub y deja de colisionar
    // con un hub hermano.
    let sql = remap_section_ids(&sql, target_hub_id);
    // Con lote abierto, el import REGISTRA qué filas inserta (ADR-0170): así esta importación
    // se puede deshacer después sin tocar lo que el usuario cree más tarde. Sin lote (llamadas
    // heredadas), se aplica igual que siempre. Ambas rutas pasan por la MISMA validación.
    let applied = match batch_id {
        Some(batch) => crate::reset::apply_tracked_into(rt, batch, target_hub_id, &sql, &scope)
            .await
            .map(|n| n as usize),
        None => crate::import_sql::apply(rt.db(), &sql, &scope).await,
    };
    match applied {
        Ok(_) => SectionStatus::Applied,
        Err(e) => SectionStatus::Failed(e.to_string()),
    }
}

/// Reescribe los `id` del SQL de una sección del bundle por ids NUEVOS derivados del hub DESTINO
/// (deterministas: uuid v5 sobre `(hub_id, id_origen)`), remapeando las FK internas del bundle y
/// reescribiendo la guarda de idempotencia para que vaya por `(hub_id, id)` (hub#260).
///
/// Trabaja sobre la forma EXACTA que emite `export::rows_to_sql`:
/// `INSERT INTO <t> ("col", …) SELECT <lit>, … WHERE NOT EXISTS (SELECT 1 FROM <t> WHERE <col> = <lit> [AND …])`.
/// Cualquier sentencia que no case se deja TAL CUAL (degradación segura: la guarda por `id` solo
/// del export sigue siendo idempotente para un re-import sobre el mismo hub; lo único que no se
/// arregla es el cross-hub en BD compartida para esa fila, pero no se rompe nada).
fn remap_section_ids(sql: &str, target_hub_id: &str) -> String {
    let Ok(stmts) = crate::import_sql::split_statements(sql) else {
        return sql.to_string(); // el import lo rechazará igual con el mismo troceo
    };
    if stmts.is_empty() {
        return sql.to_string();
    }

    // 1ª pasada: mapear cada id del bundle (literal de la columna `id`) a un id NUEVO. El nuevo id
    // es DETERMINÍSTICO en (hub DESTINO, id ORIGEN): mismo bundle importado en el mismo hub produce
    // el mismo id → re-import idempotente (la guarda `(hub_id, id)` casa y se salta). Hubs distintos
    // producen ids distintos → nunca colisionan contra la PK global en una BD compartida. Es la
    // versión «barata» del fix de fondo del issue: no reasigna ids al azar (rompería la idempotencia)
    // ni reutiliza los del origen (rompería la PK global). Se hace sobre TODAS las sentencias antes
    // de reescribir, así una fila HIJA que se emita ANTES que su padre sigue remapeando su FK.
    let mut id_map: std::collections::HashMap<String, String> = std::collections::HashMap::new();
    for stmt in &stmts {
        let Some(parsed) = parse_insert(stmt) else { continue };
        if let Some(old) = parsed.id_literal() {
            let derived = derive_id(target_hub_id, &old);
            id_map.entry(old).or_insert(derived);
        }
    }

    // 2ª pasada: reescribir cada sentencia con los nuevos ids y la guarda acotada.
    let mut out = String::with_capacity(sql.len());
    for stmt in &stmts {
        out.push_str(&rewrite_insert(stmt, &id_map, target_hub_id));
    }
    out
}

/// Sentencia INSERT parseada a su tabla, columnas y literales (la forma que emite `rows_to_sql`).
/// `None` si no casa con esa forma (se deja intacta).
struct ParsedInsert<'a> {
    #[allow(dead_code)]
    table: &'a str,
    cols: Vec<String>,
    vals: Vec<String>,
}

impl<'a> ParsedInsert<'a> {
    /// Valor LITERAL (con sus comillas) de la columna `id`, si la fila la tiene y es una cadena.
    fn id_literal(&self) -> Option<String> {
        let i = self.cols.iter().position(|c| c == "id")?;
        let v = self.vals.get(i)?;
        let s = unquote_string_literal(v)?;
        if s.is_empty() {
            None
        } else {
            Some(s)
        }
    }
}

/// Trocea `INSERT INTO <t> ( "c1", "c2", … ) SELECT <lit1>, <lit2>, …` (sin la guarda, que se
/// reescribe aparte). Acepta también la variante `VALUES (…)` por simetría, aunque el export no la
/// usa. Devuelve la posición de la sentencia justo después del `SELECT <literales>` o `VALUES (…)`.
fn parse_insert(stmt: &str) -> Option<ParsedInsert<'_>> {
    let trimmed = stmt.trim();
    let after_into = trimmed.strip_prefix("INSERT INTO ")?;
    // Tabla: hasta el primer blanco (identificador simple; el export no cualifica por esquema).
    let paren = after_into.find('(')?;
    let table = after_into[..paren].trim();
    if table.is_empty() || table.contains(|c: char| c.is_whitespace()) {
        return None;
    }
    // Lista de columnas entre `(` … `)`.
    let close = matching_paren(after_into, paren)?;
    let cols_inner = &after_into[paren + 1..close];
    let cols: Vec<String> = split_top_level_commas(cols_inner)
        .into_iter()
        .map(|c| unquote_ident(c.trim()))
        .collect();
    let rest = after_into[close + 1..].trim_start();
    // Solo nos interesa la parte de valores para construir el mapa y reescribir; la guarda se
    // descarta aquí y se regenera en `rewrite_insert`.
    let (val_rest, _guard) = split_off_guard(rest);
    let vals = parse_value_list(val_rest.trim())?;
    if vals.len() != cols.len() {
        return None;
    }
    Some(ParsedInsert { table, cols, vals })
}

/// Reescribe una sentencia INSERT: nuevos ids en `id`/`*_id`/`parent_id`, y guarda `(hub_id, id)`.
/// Si la sentencia no casa con la forma esperada se devuelve TAL CUAL.
fn rewrite_insert(stmt: &str, id_map: &std::collections::HashMap<String, String>, target_hub_id: &str) -> String {
    let trimmed = stmt.trim();
    let Some(after_into) = trimmed.strip_prefix("INSERT INTO ") else {
        return format!("{trimmed}\n");
    };
    let Some(paren) = after_into.find('(') else {
        return format!("{trimmed}\n");
    };
    let Some(close) = matching_paren(after_into, paren) else {
        return format!("{trimmed}\n");
    };
    let table = after_into[..paren].trim();
    let cols_inner = &after_into[paren + 1..close];
    let cols: Vec<String> = split_top_level_commas(cols_inner)
        .into_iter()
        .map(|c| unquote_ident(c.trim()))
        .collect();
    let rest = after_into[close + 1..].trim_start();
    let (val_rest, _guard) = split_off_guard(rest);
    let Some(vals) = parse_value_list(val_rest.trim()) else {
        return format!("{trimmed}\n");
    };
    if vals.len() != cols.len() {
        return format!("{trimmed}\n");
    }

    // Remapear: el `id` propio y cualquier FK interna (columnas `id`/`*_id`/`parent_id`) cuyo
    // literal esté en el mapa. La columna `id` siempre se reescribe con SU nuevo id.
    let mut new_vals = vals.clone();
    for (i, col) in cols.iter().enumerate() {
        let is_id_like = col == "id" || col.ends_with("_id");
        if !is_id_like {
            continue;
        }
        let Some(raw) = unquote_string_literal(&vals[i]) else { continue };
        let mapped = if col == "id" {
            // El propio id: siempre el nuevo (del mapa si se captó en la 1ª pasada; si no, se
            // deriva ahora de forma determinista para no romper la idempotencia del re-import).
            id_map.get(&raw).cloned().or_else(|| {
                if raw.is_empty() { None } else { Some(derive_id(target_hub_id, &raw)) }
            })
        } else {
            // FK interna: solo si apunta a un id del bundle que hemos remapeado.
            id_map.get(&raw).cloned()
        };
        if let Some(new) = mapped {
            new_vals[i] = quote_string_literal(&new);
        }
    }

    // Guarda de idempotencia REGENERADA con los valores ya remapeados. Para tablas CON `id`:
    // `(hub_id, id)` — idempotente por el hub DESTINO (hub#260). Para tablas SIN `id`
    // (`hub_settings` por `key`, vínculos M2M por su tupla): se CONSERVA la guarda ORIGINAL del
    // export (su clave natural: `hub_settings` va por `(key, hub_id)`, no por todas las columnas)
    // y solo se remapean en ella los literales que apuntan a ids del bundle (los `*_id` de un
    // vínculo M2M acaban de cambiar a los ids NUEVOS del hub destino).
    let col_list = cols
        .iter()
        .map(|c| quote_ident(c))
        .collect::<Vec<_>>()
        .join(", ");
    let val_list = new_vals.join(", ");
    let id_idx = cols.iter().position(|c| c == "id");
    let guard = if let Some(i) = id_idx {
        let id_lit = &new_vals[i];
        format!(
            " WHERE NOT EXISTS (SELECT 1 FROM {table} WHERE \"hub_id\" = {hub} AND id = {id})",
            hub = quote_string_literal(target_hub_id),
            id = id_lit,
        )
    } else {
        // Conserva la guarda original; remapea los ids del bundle que aparezcan como literales
        // (vínculos M2M: `product_id`/`category_id` acaban de pasar a los ids nuevos del destino).
        remap_literals_in_guard(_guard, id_map)
    };
    format!("INSERT INTO {table} ({col_list}) SELECT {val_list}{guard};\n")
}

/// Reemplaza, dentro del texto de una guarda `NOT EXISTS`, cada literal de cadena `'old'` cuyo
/// `old` sea un id del bundle por `'new'`. Operación segura aquí: los ids son UUIDs v4 y solo
/// aparecen como literales completos `'…'` (el export nunca los embebe dentro de otro dato), así
/// que sustituir el par completo `'old'` no toca subcadenas ajenas.
fn remap_literals_in_guard(guard: &str, id_map: &std::collections::HashMap<String, String>) -> String {
    let mut out = guard.to_string();
    for (old, new) in id_map {
        let from = quote_string_literal(old);
        let to = quote_string_literal(new);
        if out.contains(&from) {
            out = out.replace(&from, &to);
        }
    }
    out.trim_end_matches(';').to_string()
}

/// Divide `rest` en (parte de valores, parte de guarda). La guarda es lo que haya desde el primer
/// ` WHERE ` (a nivel de sentencia, no dentro de `NOT EXISTS`) hasta el final.
fn split_off_guard(rest: &str) -> (&str, &str) {
    match rest.find(" WHERE ") {
        Some(pos) => (&rest[..pos], &rest[pos..]),
        None => (rest, ""),
    }
}

/// Lista de literales de un `SELECT <lit>, <lit>, …` o de `VALUES (…), (…)`. Devuelve los literales
/// de la PRIMERA tupla (el export emite una fila por sentencia). Respeta comillas simples y `''`.
fn parse_value_list(s: &str) -> Option<Vec<String>> {
    let s = s.trim();
    if let Some(inner) = s.strip_prefix("VALUES") {
        let inner = inner.trim_start();
        let open = inner.find('(')?;
        let close = matching_paren(inner, open)?;
        return Some(split_top_level_commas(&inner[open + 1..close]));
    }
    let after_select = s.strip_prefix("SELECT")?;
    Some(split_top_level_commas(after_select.trim_start().trim_end_matches(';')))
}

/// Parte por comas que NO están dentro de `'…'` (un literal puede traer comas) ni de `"…"`.
fn split_top_level_commas(s: &str) -> Vec<String> {
    let mut out = Vec::new();
    let mut cur = String::new();
    let mut chars = s.chars().peekable();
    let mut in_single = false;
    let mut in_double = false;
    while let Some(c) = chars.next() {
        if in_single {
            cur.push(c);
            if c == '\'' {
                if chars.peek() == Some(&'\'') {
                    cur.push(chars.next().unwrap());
                } else {
                    in_single = false;
                }
            }
            continue;
        }
        if in_double {
            cur.push(c);
            if c == '"' {
                in_double = false;
            }
            continue;
        }
        match c {
            '\'' => {
                in_single = true;
                cur.push(c);
            }
            '"' => {
                in_double = true;
                cur.push(c);
            }
            ',' => {
                out.push(std::mem::take(&mut cur));
            }
            _ => cur.push(c),
        }
    }
    out.push(cur);
    out.iter().map(|p| p.trim().to_string()).filter(|p| !p.is_empty()).collect()
}

/// Índice del `)` que cierra el `(` en `pos`, respetando literales e identificadores.
fn matching_paren(s: &str, open: usize) -> Option<usize> {
    let bytes = s.as_bytes();
    if bytes.get(open) != Some(&b'(') {
        return None;
    }
    let mut depth = 0i32;
    let mut in_single = false;
    let mut in_double = false;
    let mut chars = s[open..].chars().peekable();
    let mut consumed = 0usize;
    while let Some(c) = chars.next() {
        consumed += c.len_utf8();
        if in_single {
            if c == '\'' {
                if chars.peek() == Some(&'\'') {
                    consumed += chars.next().unwrap().len_utf8();
                } else {
                    in_single = false;
                }
            }
            continue;
        }
        if in_double {
            if c == '"' {
                in_double = false;
            }
            continue;
        }
        match c {
            '\'' => in_single = true,
            '"' => in_double = true,
            '(' => depth += 1,
            ')' => {
                depth -= 1;
                if depth == 0 {
                    return Some(open + consumed - 1);
                }
            }
            _ => {}
        }
    }
    None
}

/// Quita las comillas dobles de un identificador de columna (`"key"` → `key`).
fn unquote_ident(s: &str) -> String {
    s.trim()
        .trim_matches('"')
        .replace("\"\"", "\"")
}

/// Convierte un literal de cadena SQL (`'Café'`) en su contenido (`Café`). Solo si es tal literal.
fn unquote_string_literal(lit: &str) -> Option<String> {
    let lit = lit.trim();
    let inner = lit.strip_prefix('\'')?.strip_suffix('\'')?;
    Some(inner.replace("''", "'"))
}

/// Pone comillas simples a una cadena para usarla como literal SQL (escapando `'`).
fn quote_string_literal(s: &str) -> String {
    format!("'{}'", s.replace('\'', "''"))
}

/// Entrecomilla un identificador (columna) como hace el export (`quote_ident`).
fn quote_ident(name: &str) -> String {
    format!("\"{}\"", name.replace('"', "\"\""))
}

/// Id NUEVO y DETERMINÍSTICO para una fila del bundle bajo el hub DESTINO (uuid v5 sobre
/// `(hub_id, id_origen)`). Es la pieza que hace que el cross-hub en una BD compartida no colisione
/// contra la PK global (`id TEXT PRIMARY KEY`) SIN romper la idempotencia del re-import: el mismo
/// bundle en el mismo hub produce siempre el mismo id (la guarda `(hub_id, id)` casa y se salta),
/// y dos hubs distintos producen ids distintos. El `id_origen` queda embebido en el nombre del v5,
/// así no hay dependencia del orden de import ni colisión entre filas.
fn derive_id(target_hub_id: &str, source_id: &str) -> String {
    // Namespace fijo propio del motor (no se deriva del hub: el hub va en el NOMBRE, para que dos
    // hubs den ids distintos a partir del mismo id origen).
    const NS: uuid::Uuid = uuid::Uuid::from_bytes([
        0x48, 0x55, 0x42, 0x42, 0x4c, 0x55, 0x45, 0x50, 0x52, 0x49, 0x4e, 0x54, 0x32, 0x36, 0x30,
        0x21,
    ]);
    let name = format!("{target_hub_id}\x1f{source_id}"); // \x1F separa hub de id (no aparece en ids)
    uuid::Uuid::new_v5(&NS, name.as_bytes()).to_string()
}

#[cfg(test)]
mod tests {
    use super::*;

    /// El informe hace round-trip serde: es el contrato JSON que la UI del shell pinta.
    #[test]
    fn report_serde_round_trip() {
        let r = ImportReport {
            sections: vec![
                SectionResult { section: "modules/taxes".into(), status: SectionStatus::Applied },
                SectionResult { section: "hub_users".into(), status: SectionStatus::Skipped },
                SectionResult {
                    section: "modules/inventory".into(),
                    status: SectionStatus::Failed("módulo no instalado".into()),
                },
            ],
        };
        let json = serde_json::to_string(&r).unwrap();
        let back: ImportReport = serde_json::from_str(&json).unwrap();
        assert_eq!(r, back);
    }

    /// `derive_id` es determinista: mismo `(hub, id)` → mismo id, siempre (la idempotencia del
    /// re-import depende de ello). Y distinto hub → distinto id (sin colisión de PK global).
    #[test]
    fn derive_id_es_determinista_y_distinta_por_hub() {
        let a1 = derive_id("h2", "src-1");
        let a2 = derive_id("h2", "src-1");
        assert_eq!(a1, a2, "mismo (hub,id) → mismo id derivado (idempotencia)");
        let b = derive_id("h3", "src-1");
        assert_ne!(a1, b, "distinto hub → distinto id (sin colisión de PK global)");
        let c = derive_id("h2", "src-2");
        assert_ne!(a1, c, "distinto id origen → distinto id");
        assert!(!a1.is_empty());
    }

    /// `remap_section_ids` reescribe el `id` por uno derivado del hub destino, deja intactas las
    /// columnas que no son id/FK (`name`, `sku`), remapea la FK interna (`category_id`) y acota la
    /// guarda por `(hub_id, id)` (hub#260).
    #[test]
    fn remap_reescribe_id_acota_guard_y_deja_los_datos() {
        // Forma real que emite `export::rows_to_sql` (placeholder ya sustituido por el hub destino).
        let sql = "INSERT INTO inventory_product (\"id\", \"hub_id\", \"name\", \"sku\") \
                   SELECT 'src-prod', 'h2', 'Café', 'CAF' \
                   WHERE NOT EXISTS (SELECT 1 FROM inventory_product WHERE id = 'src-prod');";
        let out = remap_section_ids(sql, "h2");
        // El id de origen NO aparece (fue reescrito por el derivado).
        assert!(!out.contains("'src-prod'"), "el id origen debe reescribirse: {out}");
        // Los datos del usuario se conservan.
        assert!(out.contains("'Café'") && out.contains("'CAF'"), "se perdieron datos: {out}");
        // La guarda va por (hub_id, id) destino — id ya NO va solo.
        assert!(
            out.contains("\"hub_id\" = 'h2' AND id = "),
            "la guarda debe acotarse por (hub_id, id): {out}"
        );
        // Idempotencia: misma entrada → misma salida (el id derivado es estable).
        assert_eq!(out, remap_section_ids(sql, "h2"), "el remap debe ser determinista");
    }

    /// Una FK interna (columna `*_id`) que apunta a otro id DEL BUNDLE se remapea al nuevo id;
    /// una que apunta a un id AJENO al bundle (un `tax_rate_id` cuya fila no viaja) se conserva.
    /// El remap solo conoce los ids de las filas PRESENTES en la sección (las que tienen `id`).
    #[test]
    fn remap_remapea_fk_interna_y_conserva_referencia_ajena() {
        // La categoría `src-cat` SÍ viaja en el bundle (otra fila con ese `id`); `ext-rate` no.
        let sql = "INSERT INTO inventory_category (\"id\") SELECT 'src-cat' \
                   WHERE NOT EXISTS (SELECT 1 FROM inventory_category WHERE id = 'src-cat');\n\
                   INSERT INTO inventory_product (\"id\", \"category_id\", \"tax_rate_id\") \
                   SELECT 'src-prod', 'src-cat', 'ext-rate' \
                   WHERE NOT EXISTS (SELECT 1 FROM inventory_product WHERE id = 'src-prod');";
        let out = remap_section_ids(sql, "h2");

        // `ext-rate` no es id de ninguna fila del bundle → se conserva (referencia externa).
        assert!(out.contains("'ext-rate'"), "una FK ajena al bundle no debe tocarse: {out}");

        // Los ids del bundle ya no aparecen con su valor origen.
        assert!(
            !out.contains("'src-cat'") && !out.contains("'src-prod'"),
            "los ids del bundle deben reescribirse: {out}"
        );

        // La FK interna `category_id` apunta ahora al MISMO id nuevo que la fila categoría: la
        // guarda de la categoría lleva su id nuevo, y ese mismo literal aparece como valor del
        // `category_id` del producto (la FK casa con el padre recién reescrito).
        let cat_line = out.lines().find(|l| l.contains("INSERT INTO inventory_category")).unwrap();
        let new_cat_id = cat_line
            .split("SELECT ")
            .nth(1)
            .and_then(|s| s.trim().strip_prefix('\''))
            .and_then(|s| s.split('\'').next())
            .expect("id nuevo de la categoría");
        let prod_line = out.lines().find(|l| l.contains("INSERT INTO inventory_product")).unwrap();
        assert!(
            prod_line.contains(&format!("'{}'", new_cat_id)),
            "category_id debe quedar remapeado al id nuevo de la categoría ({new_cat_id}):\n{prod_line}"
        );
    }
}
