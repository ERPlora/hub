//! Export del hub a un blueprint (ADR-0113): volcado SECCIONAL del estado del hub
//! (usuarios, settings, fiscal, datos por módulo) a un bundle `manifest.json` + `data/*.sql`
//! que el server empaqueta como `<nombre>_<idioma>.blueprint.zip` (añadiendo `media/`).
//!
//! Modelo mental = backup/restore; mecánica = como `migrate` de Django al importar.
//! El manifest es la FUENTE DE VERDAD (locale, país, módulos, secciones) — el nombre del
//! fichero lo elige el usuario y no es fiable. SQL portable con `hub_id` placeholder
//! (patrón ADR-0072); al importar se inyecta el `hub_id` destino.
//!
//! PROPUESTA de superficie (firma = contrato de los e2e `tests/export_test.rs`).
//! La implementación es columna del humano (plan Fase 1); este stub solo fija el contrato.

use std::collections::BTreeMap;

use serde::{Deserialize, Serialize};

use crate::Runtime;

/// Versión del formato del bundle. Un import con versión desconocida se rechaza sin efectos.
pub const SCHEMA_VERSION: u32 = 1;

/// Placeholder del tenant en los `data/*.sql` exportados: el import lo sustituye por el
/// `hub_id` destino antes de aplicar (patrón ADR-0072, sustitución de hub_id).
pub const HUB_ID_PLACEHOLDER: &str = "__HUB_ID__";

/// Metadatos del hub de origen (informativos; el import NO los aplica como datos).
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct HubMeta {
    pub name: String,
    /// ISO-3166-1 alpha-2 (`ES`, `FR`).
    pub country: String,
    /// ISO-4217 (`EUR`).
    pub currency: String,
}

/// Un módulo referenciado por el bundle: se instala al importar; `with_data` indica si el
/// bundle trae además sus filas (`data/<id>.sql`). Módulo marcado sin datos → solo install.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct ManifestModule {
    pub id: String,
    pub version: String,
    pub with_data: bool,
}

/// `manifest.json` del bundle — fuente de verdad del contenido (a prueba de renombres del zip).
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct BlueprintManifest {
    pub schema_version: u32,
    /// Nombre lógico elegido por el usuario (`barberia`); el default de fichero sugerido es
    /// `<name>_<locale>.blueprint.zip`, pero el fichero puede renombrarse sin romper nada.
    pub name: String,
    /// Idioma del contenido (`es`, `fr`): un restaurante ES no es un restaurante FR.
    pub locale: String,
    pub hub: HubMeta,
    /// ISO-8601; lo aporta el llamador (el runtime no lee el reloj).
    pub created_at: String,
    pub modules: Vec<ManifestModule>,
    /// Secciones presentes en el bundle (`hub_users`, `hub_settings`, `fiscal`, `media`,
    /// `modules/<id>` por cada módulo con datos).
    pub sections: Vec<String>,
    /// SHA256 hex por fichero del bundle (ruta relativa → hash). Verificado al importar.
    pub sha256: BTreeMap<String, String>,
}

/// Selección del formulario de export (checkboxes): qué secciones incluir.
#[derive(Debug, Clone, Default)]
pub struct ExportSelection {
    /// Empleados + roles + permisos (`data/hub_users.sql`).
    pub users: bool,
    /// Settings del hub (`data/hub_settings.sql`).
    pub settings: bool,
    /// Paso de ajustes ítem a ítem: claves de `hub_settings` a incluir. `None` = todas las
    /// exportables (la lista blanca la define la implementación, no el llamador).
    pub settings_items: Option<Vec<String>>,
    /// Config VeriFactu + certificado de empresa (`data/fiscal/`). OFF salvo marca explícita;
    /// se exporta tal cual (el `.p12` ya va protegido por su propia contraseña).
    pub fiscal: bool,
    /// Imágenes de la carpeta media. El RUNTIME solo lo registra en `sections`; los bytes
    /// los añade el server (gestor media, ADR-0047) al empaquetar el zip.
    pub media: bool,
    /// Por módulo instalado: checkbox «módulo» (aparecer en el manifest) + checkbox «datos».
    pub modules: Vec<ModuleDataSelection>,
}

/// Fila de la tabla de selección: el módulo va al manifest; `with_data` añade `data/<id>.sql`.
#[derive(Debug, Clone)]
pub struct ModuleDataSelection {
    pub module_id: String,
    pub with_data: bool,
}

/// Resultado del export a nivel runtime: manifest + ficheros de datos (ruta relativa → bytes).
/// El server añade `media/*` (si procede), recalcula `sha256` de lo añadido y hace el zip.
#[derive(Debug, Clone)]
pub struct ExportBundle {
    pub manifest: BlueprintManifest,
    pub files: BTreeMap<String, Vec<u8>>,
}

/// Exporta el estado del hub `hub_id` según la selección. Garantías que fijan los e2e:
/// solo filas del `hub_id` pedido; sin `is_deleted=1`; SQL portable re-aplicable con
/// [`HUB_ID_PLACEHOLDER`]; `sha256` cubre exactamente `files`; módulo sin `with_data` →
/// en `manifest.modules` pero sin `data/<id>.sql`.
pub async fn export_hub(
    rt: &Runtime,
    hub_id: &str,
    selection: &ExportSelection,
    name: &str,
    locale: &str,
    created_at: &str,
) -> crate::Result<ExportBundle> {
    let db = rt.db();
    let mut files: BTreeMap<String, Vec<u8>> = BTreeMap::new();
    let mut sections: Vec<String> = Vec::new();

    // ── Secciones a nivel hub ────────────────────────────────────────────────
    if selection.users {
        // `hub_user` NO lleva hub_id (identidad por despliegue, identity.rs): se vuelca entera.
        let rows = fetch_rows(db, "hub_user", None).await.unwrap_or_default();
        files.insert("data/hub_users.sql".into(), rows_to_sql("hub_user", &rows, hub_id).into_bytes());
        sections.push("hub_users".into());
    }
    if selection.settings {
        let mut rows = fetch_rows(db, "hub_settings", Some(hub_id)).await.unwrap_or_default();
        if let Some(keys) = &selection.settings_items {
            // Paso de ajustes ítem a ítem: solo las claves marcadas.
            rows.retain(|r| r.get("key").and_then(|k| k.as_str()).map(|k| keys.iter().any(|w| w == k)).unwrap_or(false));
        }
        files.insert("data/hub_settings.sql".into(), rows_to_sql("hub_settings", &rows, hub_id).into_bytes());
        sections.push("hub_settings".into());
    }
    // fiscal/media: el runtime solo REGISTRA la sección; los bytes (certificado, imágenes)
    // los añade el server al empaquetar (gestor media ADR-0047 / almacén del certificado).
    if selection.fiscal {
        sections.push("fiscal".into());
    }
    if selection.media {
        sections.push("media".into());
    }

    // ── Datos por módulo ─────────────────────────────────────────────────────
    // Propiedad de tablas por convención de prefijo `<module>_*` (Fase 0f). Para no asignar
    // `kitchen_orders_x` al módulo `kitchen` existiendo `kitchen_orders`, cada tabla se asigna
    // al id INSTALADO con el prefijo coincidente MÁS LARGO.
    let all_tables = list_tables(db).await?;
    let installed_ids: Vec<String> = rt.registry().installed.iter().map(|m| m.id.clone()).collect();
    let mut manifest_modules: Vec<ManifestModule> = Vec::new();

    for m in &selection.modules {
        if !rt.registry().is_installed(&m.module_id) {
            continue; // no instalado → no se puede volcar ni referenciar con versión real
        }
        let version = rt.registry().module_version(&m.module_id);
        manifest_modules.push(ManifestModule { id: m.module_id.clone(), version, with_data: m.with_data });
        if !m.with_data {
            continue; // checkbox «módulo» sin «datos»: solo va al manifest (se instalará, vacío)
        }

        let mut sql = String::new();
        for table in &all_tables {
            if table_owner(table, &installed_ids).as_deref() != Some(m.module_id.as_str()) {
                continue;
            }
            // La mayoría de tablas llevan `hub_id` (contrato de fila §2.5) → se acotan por él.
            // Las tablas de VÍNCULO (M2M) son joins puros SIN `hub_id` (`inventory_product_
            // categories`, `customers_customer_{groups,tags}`): antes se saltaban en silencio y
            // el bundle perdía la categoría de cada producto. Se vuelcan acotadas por su tabla
            // PADRE a través de la FK DECLARADA (metadato de la BD, no adivinar nombres).
            let rows = if has_column(db, table, "hub_id").await {
                fetch_rows(db, table, Some(hub_id)).await.unwrap_or_default()
            } else {
                match fetch_join_rows(db, table, hub_id).await {
                    Some(rows) => rows,
                    // Sin `hub_id` y sin FK a un padre con `hub_id` no hay forma de acotar el
                    // tenant: no se vuelca (volcarla entera filtraría datos de otros hubs).
                    None => continue,
                }
            };
            sql.push_str(&rows_to_sql(table, &rows, hub_id));
        }
        files.insert(format!("data/{}.sql", m.module_id), sql.into_bytes());
        sections.push(format!("modules/{}", m.module_id));
    }

    // ── Manifest (fuente de verdad) + integridad ─────────────────────────────
    let mut sha256 = BTreeMap::new();
    for (path, bytes) in &files {
        sha256.insert(path.clone(), sha256_hex(bytes));
    }
    let manifest = BlueprintManifest {
        schema_version: SCHEMA_VERSION,
        name: name.to_string(),
        locale: locale.to_string(),
        hub: HubMeta {
            name: setting(db, hub_id, "business_name").await.unwrap_or_default(),
            country: setting(db, hub_id, "country").await.unwrap_or_else(|| "ES".into()),
            currency: setting(db, hub_id, "currency").await.unwrap_or_else(|| "EUR".into()),
        },
        created_at: created_at.to_string(),
        modules: manifest_modules,
        sections,
        sha256,
    };
    Ok(ExportBundle { manifest, files })
}

/// SHA256 hex de unos bytes (integridad del bundle, patrón ADR-0015).
pub fn sha256_hex(bytes: &[u8]) -> String {
    use sha2::{Digest, Sha256};
    let mut h = Sha256::new();
    h.update(bytes);
    format!("{:x}", h.finalize())
}

/// Lista las tablas de usuario del backend activo (catálogo por dialecto).
async fn list_tables(db: &dyn erplora_db::DatabaseAdapter) -> crate::Result<Vec<String>> {
    let sql = match db.dialect() {
        erplora_db::Dialect::Sqlite => {
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        }
        erplora_db::Dialect::Postgres => {
            "SELECT table_name AS name FROM information_schema.tables WHERE table_schema = 'public'"
        }
    };
    let res = db.query(sql, &erplora_db::Params::new()).await.map_err(|e| crate::RuntimeError::Other(format!("export: catálogo de tablas: {e}")))?;
    Ok(res.rows.iter().filter_map(|r| r.get("name").and_then(|n| n.as_str()).map(str::to_string)).collect())
}

/// Módulo instalado dueño de `table` por prefijo más largo (`<id>_*` o nombre exacto).
fn table_owner(table: &str, installed_ids: &[String]) -> Option<String> {
    installed_ids
        .iter()
        .filter(|id| table == id.as_str() || table.starts_with(&format!("{id}_")))
        .max_by_key(|id| id.len())
        .cloned()
}

/// Nombre de tabla/columna seguro para interpolar (vienen del CATÁLOGO de la BD, no del usuario;
/// el guardarraíl es defensivo por si un módulo declara algo raro).
fn safe_ident(s: &str) -> bool {
    !s.is_empty() && s.chars().all(|c| c.is_ascii_alphanumeric() || c == '_')
}

/// ¿`table` tiene la columna `col`? (catálogo por dialecto).
async fn has_column(db: &dyn erplora_db::DatabaseAdapter, table: &str, col: &str) -> bool {
    if !safe_ident(table) {
        return false;
    }
    let sql = match db.dialect() {
        erplora_db::Dialect::Sqlite => format!("SELECT name FROM pragma_table_info('{table}')"),
        erplora_db::Dialect::Postgres => format!(
            "SELECT column_name AS name FROM information_schema.columns \
             WHERE table_schema = 'public' AND table_name = '{table}'"
        ),
    };
    let Ok(res) = db.query(&sql, &erplora_db::Params::new()).await else { return false };
    res.rows
        .iter()
        .filter_map(|r| r.get("name").and_then(|n| n.as_str()))
        .any(|n| n == col)
}

/// Una FK declarada por la tabla: `from` (columna local) → `parent`.`to`.
struct ForeignKey {
    from: String,
    parent: String,
    to: String,
}

/// FKs declaradas de `table`, leídas del catálogo de la BD (no se infieren por nombre).
async fn foreign_keys(db: &dyn erplora_db::DatabaseAdapter, table: &str) -> Vec<ForeignKey> {
    if !safe_ident(table) {
        return Vec::new();
    }
    let sql = match db.dialect() {
        // `pragma_foreign_key_list` como tabla-función: columnas `from`/`to`/`table`.
        erplora_db::Dialect::Sqlite => format!(
            "SELECT \"from\" AS col_from, \"to\" AS col_to, \"table\" AS parent \
             FROM pragma_foreign_key_list('{table}')"
        ),
        erplora_db::Dialect::Postgres => format!(
            "SELECT kcu.column_name AS col_from, ccu.column_name AS col_to, \
                    ccu.table_name AS parent \
             FROM information_schema.table_constraints tc \
             JOIN information_schema.key_column_usage kcu \
               ON kcu.constraint_name = tc.constraint_name \
             JOIN information_schema.constraint_column_usage ccu \
               ON ccu.constraint_name = tc.constraint_name \
             WHERE tc.constraint_type = 'FOREIGN KEY' AND tc.table_name = '{table}'"
        ),
    };
    let Ok(res) = db.query(&sql, &erplora_db::Params::new()).await else { return Vec::new() };
    res.rows
        .iter()
        .filter_map(|r| {
            let from = r.get("col_from")?.as_str()?.to_string();
            let parent = r.get("parent")?.as_str()?.to_string();
            // En SQLite `to` puede venir NULL → referencia implícita a la PK del padre (`id`).
            let to = r.get("col_to").and_then(|v| v.as_str()).unwrap_or("id").to_string();
            (safe_ident(&from) && safe_ident(&parent) && safe_ident(&to))
                .then_some(ForeignKey { from, parent, to })
        })
        .collect()
}

/// Filas de una tabla de VÍNCULO (sin `hub_id` propio) acotadas al tenant a través de la primera
/// FK cuyo PADRE sí lleva `hub_id`. `None` = no hay por dónde acotar → el llamador no la vuelca.
async fn fetch_join_rows(
    db: &dyn erplora_db::DatabaseAdapter,
    table: &str,
    hub_id: &str,
) -> Option<Vec<serde_json::Value>> {
    for fk in foreign_keys(db, table).await {
        if !has_column(db, &fk.parent, "hub_id").await {
            continue;
        }
        let (parent, to, from) = (&fk.parent, &fk.to, &fk.from);
        let sql = format!(
            "SELECT t.* FROM {table} t WHERE EXISTS \
             (SELECT 1 FROM {parent} p WHERE p.{to} = t.{from} AND p.hub_id = :hub_id)"
        );
        let mut p = erplora_db::Params::new();
        p.insert("hub_id".into(), serde_json::Value::String(hub_id.to_string()));
        if let Ok(res) = db.query(&sql, &p).await {
            return Some(res.rows);
        }
    }
    None
}

/// Filas de `table` (opcionalmente scoped por hub_id), sin las soft-deleted.
async fn fetch_rows(
    db: &dyn erplora_db::DatabaseAdapter,
    table: &str,
    hub_id: Option<&str>,
) -> Result<Vec<serde_json::Value>, erplora_db::DbError> {
    let (sql, params) = match hub_id {
        Some(h) => {
            let mut p = erplora_db::Params::new();
            p.insert("hub_id".into(), serde_json::Value::String(h.to_string()));
            (format!("SELECT * FROM {table} WHERE hub_id = :hub_id"), p)
        }
        None => (format!("SELECT * FROM {table}"), erplora_db::Params::new()),
    };
    let res = db.query(&sql, &params).await?;
    // El filtro de soft-delete va en Rust (no todas las tablas tienen la columna).
    Ok(res.rows.into_iter().filter(|r| !truthy(r.get("is_deleted"))).collect())
}

fn truthy(v: Option<&serde_json::Value>) -> bool {
    match v {
        Some(serde_json::Value::Bool(b)) => *b,
        Some(serde_json::Value::Number(n)) => n.as_f64().map(|f| f != 0.0).unwrap_or(false),
        Some(serde_json::Value::String(s)) => s == "1" || s == "true",
        _ => false,
    }
}

/// Convierte filas JSON en INSERTs portables (SQLite↔Postgres) idempotentes por (id, hub_id),
/// con el hub_id sustituido por [`HUB_ID_PLACEHOLDER`]. Sin filas → cadena vacía.
fn rows_to_sql(table: &str, rows: &[serde_json::Value], hub_id: &str) -> String {
    let mut out = String::new();
    for row in rows {
        let Some(obj) = row.as_object() else { continue };
        let cols: Vec<&String> = obj.keys().collect();
        let vals: Vec<String> = cols
            .iter()
            .map(|c| {
                if *c == "hub_id" {
                    format!("'{HUB_ID_PLACEHOLDER}'")
                } else {
                    let lit = sql_literal(&obj[*c].clone());
                    // Guardarraíl anti-fuga POR COLUMNA: el hub_id de ORIGEN no viaja aunque
                    // OTRA columna lo repita. Excepción: `id` (clave primaria) y las columnas
                    // de auditoría (`created_by`/`updated_by`), que en Dev valen igual que el
                    // hub_id (`local`) pero guardan identidad propia — el hub destino las
                    // re-inyecta al aplicar y no deben perder su valor. (Antes un `replace`
                    // ciego de `'{hub_id}'` sobre todo el SQL las arrastraba: bug dev-only.)
                    if !matches!(c.as_str(), "id" | "created_by" | "updated_by")
                        && lit == format!("'{hub_id}'")
                    {
                        format!("'{HUB_ID_PLACEHOLDER}'")
                    } else {
                        lit
                    }
                }
            })
            .collect();
        // Identificadores ENTRECOMILLADOS (comillas dobles = SQL estándar, válidas en SQLite y en
        // Postgres). Sin esto, una columna que sea PALABRA RESERVADA revienta el INSERT al
        // importar: `inventory_category`/`staff_role` tienen una columna `order` y el bundle
        // aterrizaba con «near "order": syntax error» — perdiendo la sección ENTERA (el módulo se
        // aplica en bloque), así que 19 categorías + 280 productos se quedaban en nada.
        let col_list = cols.iter().map(|c| quote_ident(c)).collect::<Vec<_>>().join(", ");
        let val_list = vals.join(", ");
        // Guard NOT EXISTS por (id, hub_id) cuando hay `id` (contrato de fila): re-importar el
        // mismo bundle no duplica. Sin `id` (p.ej. hub_settings, PK compuesta) → guard por PK real.
        let guard = if obj.contains_key("id") {
            let id_lit = sql_literal(&obj["id"]);
            if obj.contains_key("hub_id") {
                format!(" WHERE NOT EXISTS (SELECT 1 FROM {table} WHERE id = {id_lit} AND hub_id = '{HUB_ID_PLACEHOLDER}')")
            } else {
                format!(" WHERE NOT EXISTS (SELECT 1 FROM {table} WHERE id = {id_lit})")
            }
        } else if table == "hub_settings" && obj.contains_key("key") {
            // `key` también es palabra reservada en algunos dialectos → entrecomillada.
            let key_lit = sql_literal(&obj["key"]);
            format!(" WHERE NOT EXISTS (SELECT 1 FROM {table} WHERE \"key\" = {key_lit} AND hub_id = '{HUB_ID_PLACEHOLDER}')")
        } else {
            // Sin `id`: tablas de VÍNCULO (M2M), donde la PK ES la tupla entera. La guarda va por
            // todas las columnas → re-aplicar el bundle no duplica (mismo contrato idempotente).
            let conds: Vec<String> = cols
                .iter()
                .zip(vals.iter())
                .map(|(c, v)| {
                    let col = quote_ident(c);
                    if v == "NULL" {
                        format!("{col} IS NULL")
                    } else {
                        format!("{col} = {v}")
                    }
                })
                .collect();
            format!(" WHERE NOT EXISTS (SELECT 1 FROM {table} WHERE {})", conds.join(" AND "))
        };
        out.push_str(&format!("INSERT INTO {table} ({col_list}) SELECT {val_list}{guard};\n"));
    }
    // El barrido anti-fuga del hub_id de ORIGEN va ya POR COLUMNA arriba (respetando id y
    // auditoría), no con un replace ciego sobre todo el SQL.
    out
}

/// Entrecomilla un identificador (columna) con comillas dobles — SQL estándar, lo entienden tanto
/// SQLite como Postgres. Es lo que permite volcar columnas cuyo nombre es una PALABRA RESERVADA
/// (`order`, `key`…). Los nombres salen del catálogo de la BD, pero se escapa la comilla doble por
/// si acaso (defensivo: nunca se construye SQL con texto del usuario).
fn quote_ident(name: &str) -> String {
    format!("\"{}\"", name.replace('"', "\"\""))
}

/// Literal SQL portable a partir de un valor JSON (escape de comillas simples).
fn sql_literal(v: &serde_json::Value) -> String {
    match v {
        serde_json::Value::Null => "NULL".into(),
        serde_json::Value::Bool(b) => if *b { "TRUE".into() } else { "FALSE".into() },
        serde_json::Value::Number(n) => n.to_string(),
        serde_json::Value::String(s) => format!("'{}'", s.replace('\'', "''")),
        other => format!("'{}'", other.to_string().replace('\'', "''")),
    }
}

/// Lee un setting del hub (best-effort; para los metadatos informativos del manifest).
async fn setting(db: &dyn erplora_db::DatabaseAdapter, hub_id: &str, key: &str) -> Option<String> {
    let mut p = erplora_db::Params::new();
    p.insert("hub_id".into(), serde_json::Value::String(hub_id.to_string()));
    p.insert("key".into(), serde_json::Value::String(key.to_string()));
    let res = db.query("SELECT value FROM hub_settings WHERE hub_id = :hub_id AND key = :key", &p).await.ok()?;
    res.rows.first().and_then(|r| r.get("value")).and_then(|v| v.as_str()).map(str::to_string)
}

#[cfg(test)]
mod tests {
    use super::*;

    /// El manifest hace round-trip serde sin perder campos: es el contrato del fichero
    /// `manifest.json` (la fuente de verdad del bundle, a prueba de renombres del zip).
    #[test]
    fn manifest_serde_round_trip() {
        let m = BlueprintManifest {
            schema_version: SCHEMA_VERSION,
            name: "barberia".into(),
            locale: "es".into(),
            hub: HubMeta { name: "Demo".into(), country: "ES".into(), currency: "EUR".into() },
            created_at: "2026-07-11T18:00:00Z".into(),
            modules: vec![ManifestModule { id: "taxes".into(), version: "2.1.1".into(), with_data: true }],
            sections: vec!["hub_settings".into(), "modules/taxes".into()],
            sha256: BTreeMap::from([("data/taxes.sql".into(), "ab".repeat(32))]),
        };
        let json = serde_json::to_string(&m).unwrap();
        let back: BlueprintManifest = serde_json::from_str(&json).unwrap();
        assert_eq!(m, back);
    }

    /// El placeholder del tenant y la versión del formato son estables: cambiarlos
    /// rompería todos los bundles ya publicados.
    #[test]
    fn format_constants_are_stable() {
        assert_eq!(HUB_ID_PLACEHOLDER, "__HUB_ID__");
        assert_eq!(SCHEMA_VERSION, 1);
    }

    /// Anti-fuga POR COLUMNA: en Dev el `hub_id` y las columnas de auditoría
    /// (`created_by`/`updated_by`) comparten el literal `local`. El export debe sustituir
    /// SOLO la columna `hub_id` por el placeholder y CONSERVAR la identidad de auditoría
    /// (el hub destino la re-inyecta al aplicar). Un `replace` ciego de `'local'` sobre todo
    /// el SQL las arrastraba (bug dev-only del informe de review 2026-07-12, hallazgo #3).
    #[test]
    fn rows_to_sql_no_arrastra_auditoria_cuando_hub_id_coincide() {
        let rows = vec![serde_json::json!({
            "id": "prod-1",
            "hub_id": "local",
            "created_by": "local",
            "updated_by": "local",
            "name": "Café",
        })];
        let sql = rows_to_sql("inventory_product", &rows, "local");
        // La columna hub_id (valor + guard NOT EXISTS) va como placeholder: 2 apariciones.
        assert!(sql.contains("'__HUB_ID__'"), "el hub_id debe viajar como placeholder");
        // created_by y updated_by conservan 'local' (identidad): exactamente 2 apariciones.
        assert_eq!(
            sql.matches("'local'").count(),
            2,
            "created_by/updated_by deben conservar su valor 'local', no convertirse en placeholder:\n{sql}"
        );
    }
}
