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
        let mut rows = fetch_rows(db, "hub_user", None).await.unwrap_or_default();
        // …pero DESVINCULADA de las cuentas Cloud. `cloud_user_id` es la identidad de una
        // PERSONA del SaaS: el usuario que dispara el export acaba dentro del bundle y, si se
        // publica como blueprint, cada hub que lo importe se lo lleva como usuario suyo —con su
        // rol— y el login cloud casa por ese id y entra. Pasó de verdad: los blueprints
        // regenerados el 2026-07-31 llevaban a support@erplora.com como `owner`.
        //
        // Se corta el VÍNCULO, no la fila. `export_hub` es también el motor del backup y de la
        // migración de un hub entre despliegues (ADR-0113 §1): tirar la fila perdería el rol de
        // cada usuario Cloud, y al restaurar los recrearía `get_or_link_cloud_user` con
        // `HUB_DEFAULT_ROLE` (por defecto `admin`) — un `employee` volvería como ADMIN. Con el
        // id a NULL viajan nombre, rol y PIN, y no viaja la cuenta del SaaS.
        for r in rows.iter_mut() {
            if let Some(v) = r.get_mut("cloud_user_id") {
                *v = serde_json::Value::Null;
            }
        }
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

        // Las tablas del módulo, ORDENADAS por dependencia: el padre antes que quien lo
        // referencia (ver `order_by_dependency`). Sin esto el volcado sale en el orden de
        // `information_schema` y el import se cae por FK, perdiendo la sección entera.
        let mut mine: Vec<String> = all_tables
            .iter()
            .filter(|t| table_owner(t, &installed_ids).as_deref() == Some(m.module_id.as_str()))
            .cloned()
            .collect();
        order_by_dependency(db, &mut mine).await;

        let mut sql = String::new();
        for table in &mine {
            // La identidad fiscal del NEGOCIO (NIF y nombre del emisor, entorno, auto_transmit,
            // certificado) solo viaja si se marca `fiscal` —la sección que ya mueve el `.p12`—.
            // Iba como una tabla más del módulo, así que el blueprint publicado sembraba el NIF
            // del hub demo y `auto_transmit=1` en el hub de cada cliente que lo importaba.
            if table == "verifactu_config" && !selection.fiscal {
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
            // Ordenar las tablas entre sí no basta: una tabla con FK a SÍ MISMA
            // (`services_category.parent_id`, `taxes_rule.parent_id`) puede devolver la fila
            // hija antes que la padre —`fetch_rows` no ordena y el orden físico manda—, y el
            // INSERT revienta por FK igual, un nivel más abajo.
            let rows = order_rows_parent_first(db, table, rows).await;
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
pub(crate) async fn list_tables(db: &dyn erplora_db::DatabaseAdapter) -> crate::Result<Vec<String>> {
    // Postgres-only (ADR-0154). `current_schema()` acota al esquema activo del hub (en prod
    // `public`; en los tests, el esquema efímero por test).
    let sql = "SELECT table_name AS name FROM information_schema.tables \
               WHERE table_schema = current_schema()";
    let res = db.query(sql, &erplora_db::Params::new()).await.map_err(|e| crate::RuntimeError::Other(format!("export: catálogo de tablas: {e}")))?;
    Ok(res.rows.iter().filter_map(|r| r.get("name").and_then(|n| n.as_str()).map(str::to_string)).collect())
}

/// Ordena `tables` para que una tabla vaya SIEMPRE detrás de aquellas a las que referencia.
///
/// El volcado se aplica al importar en el orden del fichero, así que si el hijo va primero el
/// INSERT revienta por FK y **se pierde la sección entera** (el módulo se aplica en bloque).
/// `list_tables` devuelve el orden de `information_schema`, que no garantiza nada: en un hub
/// real `inventory_category` salió DESPUÉS de `inventory_product_categories` y el import murió
/// con `violates foreign key constraint …_category_id_fkey` tirando 280 productos + 19
/// categorías. Los blueprints publicados en julio colaban por casualidad.
///
/// Las dependencias salen de las FK DECLARADAS (catálogo de la BD), no de adivinar por el
/// nombre. Orden estable y a prueba de ciclos: una FK a sí misma (`parent_id`) o un ciclo entre
/// tablas no cuelga ni descarta nada — lo que no se puede ordenar conserva su posición.
async fn order_by_dependency(db: &dyn erplora_db::DatabaseAdapter, tables: &mut Vec<String>) {
    let mut deps: Vec<std::collections::HashSet<String>> = Vec::with_capacity(tables.len());
    for t in tables.iter() {
        let padres = foreign_keys(db, t)
            .await
            .into_iter()
            .map(|fk| fk.parent)
            .filter(|p| p != t && tables.contains(p))
            .collect();
        deps.push(padres);
    }

    // Kahn estable: de las que ya no esperan a nadie sale siempre la de índice más bajo.
    let mut salida: Vec<String> = Vec::with_capacity(tables.len());
    let mut colocadas: std::collections::HashSet<String> = std::collections::HashSet::new();
    while salida.len() < tables.len() {
        let siguiente = (0..tables.len())
            .find(|&i| !colocadas.contains(&tables[i]) && deps[i].iter().all(|p| colocadas.contains(p)));
        match siguiente {
            Some(i) => {
                colocadas.insert(tables[i].clone());
                salida.push(tables[i].clone());
            }
            // Ciclo: nada más se puede colocar. El resto va en su orden original (no se pierde
            // ninguna tabla; un ciclo real de FK no lo puede resolver ningún orden).
            None => {
                for t in tables.iter() {
                    if !colocadas.contains(t) {
                        colocadas.insert(t.clone());
                        salida.push(t.clone());
                    }
                }
            }
        }
    }
    *tables = salida;
}

/// Ordena las FILAS de `table` para que un padre vaya antes que quien lo referencia, cuando la
/// tabla tiene una FK a **sí misma** (`services_category.parent_id`, `taxes_rule.parent_id`).
///
/// [`order_by_dependency`] resuelve el orden ENTRE tablas; esto resuelve el de DENTRO. Sin ello
/// el mismo fallo salta un nivel más abajo: `fetch_rows` no ordena, así que las filas salen en
/// orden físico y basta un `UPDATE` de la fila padre (que la reescribe al final del heap) para
/// que la hija se vuelque primero y el import muera por FK, perdiendo la sección entera.
///
/// Si la tabla no se autorreferencia, devuelve las filas tal cual (coste cero). Estable y a
/// prueba de ciclos: lo que no se puede colocar conserva su orden original.
async fn order_rows_parent_first(
    db: &dyn erplora_db::DatabaseAdapter,
    table: &str,
    rows: Vec<serde_json::Value>,
) -> Vec<serde_json::Value> {
    let self_fks: Vec<String> = foreign_keys(db, table)
        .await
        .into_iter()
        .filter(|fk| fk.parent == table && fk.to == "id")
        .map(|fk| fk.from)
        .collect();
    if self_fks.is_empty() || rows.len() < 2 {
        return rows;
    }

    let id_de = |r: &serde_json::Value| r.get("id").and_then(|v| v.as_str()).map(str::to_string);
    let pendiente_de = |r: &serde_json::Value| -> Option<String> {
        // El padre al que apunta esta fila (por cualquiera de sus FK a sí misma), si lo hay.
        self_fks
            .iter()
            .filter_map(|c| r.get(c).and_then(|v| v.as_str()).map(str::to_string))
            .next()
    };

    let mut salida: Vec<serde_json::Value> = Vec::with_capacity(rows.len());
    let mut colocados: std::collections::HashSet<String> = std::collections::HashSet::new();
    let mut restantes: Vec<serde_json::Value> = rows;
    while !restantes.is_empty() {
        // Colocables: las que no esperan padre, o cuyo padre ya salió (o no está en el lote:
        // apunta a una fila filtrada —soft-deleted, sembrada— y el guard NOT EXISTS lo cubre).
        let ids_restantes: std::collections::HashSet<String> =
            restantes.iter().filter_map(id_de).collect();
        let (listas, esperando): (Vec<_>, Vec<_>) = restantes.into_iter().partition(|r| {
            match pendiente_de(r) {
                None => true,
                Some(p) => colocados.contains(&p) || !ids_restantes.contains(&p),
            }
        });
        if listas.is_empty() {
            // Ciclo entre filas: se emiten tal cual (ningún orden lo resuelve) y no se pierde nada.
            salida.extend(esperando);
            break;
        }
        for r in listas {
            if let Some(id) = id_de(&r) {
                colocados.insert(id);
            }
            salida.push(r);
        }
        restantes = esperando;
    }
    salida
}

/// Módulo instalado dueño de `table` por prefijo más largo (`<id>_*` o nombre exacto).
pub(crate) fn table_owner(table: &str, installed_ids: &[String]) -> Option<String> {
    installed_ids
        .iter()
        .filter(|id| table == id.as_str() || table.starts_with(&format!("{id}_")))
        .max_by_key(|id| id.len())
        .cloned()
}

/// Nombre de tabla/columna seguro para interpolar (vienen del CATÁLOGO de la BD, no del usuario;
/// el guardarraíl es defensivo por si un módulo declara algo raro).
pub(crate) fn safe_ident(s: &str) -> bool {
    !s.is_empty() && s.chars().all(|c| c.is_ascii_alphanumeric() || c == '_')
}

/// ¿`table` tiene la columna `col`? (catálogo por dialecto).
pub(crate) async fn has_column(db: &dyn erplora_db::DatabaseAdapter, table: &str, col: &str) -> bool {
    if !safe_ident(table) {
        return false;
    }
    // Postgres-only (ADR-0154), acotado al esquema activo (`current_schema()`).
    let sql = format!(
        "SELECT column_name AS name FROM information_schema.columns \
         WHERE table_schema = current_schema() AND table_name = '{table}'"
    );
    let Ok(res) = db.query(&sql, &erplora_db::Params::new()).await else { return false };
    res.rows
        .iter()
        .filter_map(|r| r.get("name").and_then(|n| n.as_str()))
        .any(|n| n == col)
}

/// Una FK declarada por la tabla: `from` (columna local) → `parent`.`to`.
pub(crate) struct ForeignKey {
    pub(crate) from: String,
    pub(crate) parent: String,
    pub(crate) to: String,
}

/// FKs declaradas de `table`, leídas del catálogo de la BD (no se infieren por nombre).
pub(crate) async fn foreign_keys(db: &dyn erplora_db::DatabaseAdapter, table: &str) -> Vec<ForeignKey> {
    if !safe_ident(table) {
        return Vec::new();
    }
    // Postgres-only (ADR-0154), acotado al esquema activo (`current_schema()`).
    let sql = format!(
        "SELECT kcu.column_name AS col_from, ccu.column_name AS col_to, \
                ccu.table_name AS parent \
         FROM information_schema.table_constraints tc \
         JOIN information_schema.key_column_usage kcu \
           ON kcu.constraint_name = tc.constraint_name \
         JOIN information_schema.constraint_column_usage ccu \
           ON ccu.constraint_name = tc.constraint_name \
         WHERE tc.constraint_type = 'FOREIGN KEY' AND tc.table_schema = current_schema() \
           AND tc.table_name = '{table}'"
    );
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
    // Filtros en Rust (no todas las tablas tienen estas columnas): fuera las soft-deleted y fuera
    // los datos PROPIEDAD DEL MÓDULO (los re-siembra al instalarse) — ver `is_module_seeded`.
    Ok(res.rows.into_iter().filter(|r| !truthy(r.get("is_deleted")) && !is_module_seeded(r)).collect())
}

/// Fila de referencia PROPIEDAD DEL MÓDULO: la crea el propio módulo al instalarse (migración/
/// bloque `seed`) y la RE-SIEMBRA en cada hub — categorías fiscales canónicas (`is_system=1`),
/// alias de fábrica (`source='shipped'`) y reglas de IVA (`taxes_rule`), ADR-0085. NO debe viajar
/// en el bundle: al restaurar sobre un hub que ya re-sembró las suyas, chocaría contra las claves
/// únicas (`(hub_id,key)`/`(hub_id,alias)`) —el `duplicate key ix_tax_cat_hub_key` que tumbaba la
/// demo del SaaS— o, en tablas SIN índice único de clave natural (`taxes_rule`), DUPLICARÍA en
/// silencio (guard-por-`id` no la ve: el `id` embebe el hub ORIGEN) dejando el lookup de IVA
/// ambiguo. Los datos de USUARIO sí viajan.
///
/// Marcadores: `is_system=1` y `source='shipped'` son específicos de `taxes_category`/alias;
/// `created_by='system'` es UNIFORME —lo pone `apply_module_seed` en TODA fila que siembra un
/// módulo, incluida `taxes_rule`— y distingue lo sembrado (system) de lo que crea un usuario (su
/// id). Excluir por él es seguro para las secciones a nivel hub: `hub_settings`/`hub_user` no
/// tienen columna `created_by`, así que nunca casan.
pub(crate) fn is_module_seeded(row: &serde_json::Value) -> bool {
    truthy(row.get("is_system"))
        || row.get("source").and_then(|v| v.as_str()) == Some("shipped")
        || row.get("created_by").and_then(|v| v.as_str()) == Some("system")
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
        // Guard NOT EXISTS por `id` SOLO cuando hay `id` (contrato de fila): re-importar el mismo
        // bundle no duplica. Sin `id` (p.ej. hub_settings, PK compuesta) → guard por PK real.
        //
        // El guard NO puede llevar `AND hub_id = destino`, aunque parezca lo natural: `id` es la
        // CLAVE PRIMARIA y no sabe de hubs. Con el hub_id en la condición, una fila cuyo id ya
        // existe bajo OTRO hub pasaba el guard y el INSERT chocaba contra la PK — perdiendo la
        // SECCIÓN ENTERA (el módulo se aplica en bloque): 19 categorías fiscales a la basura por
        // una fila. Salió al cablear el bloque `seed` (ADR-0147), porque los datos de referencia
        // llevan el hub_id DENTRO del id por convención (`h1|taxcat|restaurant.food`) y el export
        // excluye `id` del placeholder a propósito (ver el guardarraíl anti-fuga de arriba).
        let guard = if obj.contains_key("id") {
            let id_lit = sql_literal(&obj["id"]);
            format!(" WHERE NOT EXISTS (SELECT 1 FROM {table} WHERE id = {id_lit})")
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
