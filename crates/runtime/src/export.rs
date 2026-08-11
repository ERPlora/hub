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

/// Section that carries the role set of a vertical (paso 2b, hub#354). It has **no `data/*.sql`**:
/// the keys travel in [`BlueprintManifest::active_roles`] and the import applies them through
/// `roles::set_active`, never as SQL. Listed in `sections` so the inventory the user confirms
/// before importing shows that the bundle brings a role set.
pub const ROLES_SECTION: &str = "roles";

/// Metadatos del hub de origen (informativos; el import NO los aplica como datos).
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct HubMeta {
    pub name: String,
    /// ISO-3166-1 alpha-2 (`ES`, `FR`).
    pub country: String,
    /// ISO-4217 (`EUR`).
    pub currency: String,
    /// `hub_id` of the ORIGIN hub. Lets the import tell a same-hub restore (the fiscal chain
    /// may be applied) from a cross-hub one (it must not — ADR-0202 §4.2, hub#312).
    /// `#[serde(default)]` ⇒ bundles older than this field read as "unknown origin", which
    /// imports conservatively (the chain section is discarded).
    #[serde(default)]
    pub hub_id: String,
}

/// Un módulo referenciado por el bundle: se instala al importar; `with_data` indica si el
/// bundle trae además sus filas (`data/<id>.sql`). Módulo marcado sin datos → solo install.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct ManifestModule {
    pub id: String,
    pub version: String,
    pub with_data: bool,
}

/// **Para qué es este bundle** (ADR-0195).
///
/// El mismo motor sirve a dos propósitos con requisitos OPUESTOS (ADR-0113 §1) y hasta ahora
/// producía el mismo zip para ambos:
///
/// - [`Backup`](Self::Backup) — copia o migración de un hub, **privada, del mismo dueño**: las
///   identidades **deben** viajar (sin ellas, restaurar pierde roles y PINs y
///   `get_or_link_cloud_user` recrearía a un `employee` como admin).
/// - [`Template`](Self::Template) — plantilla que se **publica** en el catálogo: es un artefacto
///   **público** y no puede llevar identidades, credenciales ni datos fiscales de nadie.
///
/// Ausente en el manifest ⇒ `Backup`: es el comportamiento histórico y lo que de hecho son los
/// bundles ya existentes.
#[derive(Debug, Clone, Copy, Default, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum BundlePurpose {
    /// Copia/migración privada: lo lleva todo.
    #[default]
    Backup,
    /// Plantilla publicable: sin identidades (`hub_users`) ni fiscal.
    Template,
}

impl BundlePurpose {
    /// ¿Puede este bundle transportar identidades del hub y su certificado fiscal? Solo un
    /// backup. Es la ÚNICA regla que consulta el export: una casilla no puede saltársela.
    pub fn allows_identity_sections(self) -> bool {
        matches!(self, Self::Backup)
    }

    /// ¿Es una plantilla, es decir, un artefacto pensado para OTRO negocio?
    ///
    /// Se pregunta aparte de [`allows_identity_sections`](Self::allows_identity_sections) porque
    /// son dos cosas distintas: aquélla habla de **identidad** (de quién es esto), y ésta de **de
    /// quién es la decisión** — la serie de facturación no identifica a nadie y aun así no puede
    /// venir hecha (ver [`TEMPLATE_EXCLUDED_TABLES`]). Mezclarlas en un solo booleano habría hecho
    /// que la próxima regla de este tipo se colgara del nombre equivocado.
    pub fn is_template(self) -> bool {
        matches!(self, Self::Template)
    }
}

/// Tablas que NO viajan en una **plantilla**, aunque su módulo entre con «datos» (hub#533).
///
/// No son identidad ni secretos —eso ya lo cierra ADR-0195 §2/§4—: son **decisiones del negocio
/// que importa la plantilla**, y venir hechas es peor que faltar. `invoice_series_series` fija el
/// prefijo, el formato y cuál es la serie por defecto, o sea **cómo se numera cada documento que
/// ese negocio emite ante Hacienda**; e `invoice_series_allocation` es el libro de números ya
/// entregados que el RD 1007/2023 exige sin huecos ni duplicados — historial de OTRA instalación.
///
/// Y hay un daño de segundo orden: al venir hechas, marcaban como «hecho» el ítem OBLIGATORIO
/// `invoice_series.setup` de la checklist ([ADR-0222](../../architecture/00-overview/decision-log.md)),
/// así que su dueño no lo revisaba nunca. Un falso «pendiente» se ve; un falso «hecho» esconde la
/// tarea para siempre (hub#426).
///
/// **Lista corta y del CORE, no un contrato en el manifest de módulo.** Lo que un módulo considere
/// plantilla lo elige quien exporta, tabla a tabla (hub#534); esto es el suelo que esa elección no
/// puede levantar, igual que `PORTABLE_SETTING_KEYS` es el suyo. Un **backup** se las lleva todas:
/// es la numeración de su dueño volviendo a su sitio (ADR-0113 §1).
///
/// Se descartó publicar la serie con el código `DEMO` y que el hub lo leyera como «sin configurar»:
/// una serie llamada `DEMO` existe de verdad y numeraría una factura real (`DEMO-2026-00001`), y
/// una cadena mágica la puede escribir un usuario — con lo que vuelve a ser una adivinanza.
pub const TEMPLATE_EXCLUDED_TABLES: [&str; 2] = ["invoice_series_series", "invoice_series_allocation"];

/// The leading `_` that RESERVES the runtime's own namespace (ADR-0273 D8 — hub#560).
///
/// It is broader than [`SYSTEM_TABLE_PREFIX`] on purpose, and the reason is the prefix rule itself:
/// a module owns `<id>` and `<id>_*`, so a section calling itself module `_hub` would reach every
/// `_hub_*` table there is. Checking `_hub_` alone would let that one through. Nothing a bundle can
/// legitimately name starts with `_` — module ids are lowercase words and dashes — so the whole
/// namespace is simply off limits.
pub const RESERVED_NAMESPACE_PREFIX: &str = "_";

/// Prefix of the hub's **own** system tables: `_hub_fiscal_profile`, `_hub_fiscal_regime_registry`,
/// `_hub_certificate`, `_hub_import_batch`/`_hub_import_row`, `_hub_meta`, `_hub_*_migrations`.
/// Created by [`crate::system_migrations`], owned by the RUNTIME, invisible to every module.
pub const SYSTEM_TABLE_PREFIX: &str = "_hub_";

/// Is `table` one of the hub's own system tables — i.e. **out of the bundle's world entirely**?
/// (ADR-0273 D8 — hub#560.)
///
/// This is the other side of the frontier `purpose` draws, and it needed a name of its own. ADR-0252
/// fixed that frontier by deciding the role set DOES travel: *«what `purpose` separates is who you
/// are (tax id, accounts, certificate), not what you call the posts on your staff»*. The fiscal
/// profile is squarely on the «who you are» side — the taxpayer id the emitted chain is anchored to,
/// the `system_id` of the installation, the stamp of the first record sent to the tax authority — and
/// so is the registry that says a country owes a regime at all. A bundle able to write either could
/// declare a hub **already live**, or hand it another installation's `system_id`: adopting somebody
/// else's installation by the back door, which hub#558 makes a deliberate act with a trace.
///
/// Note what this is NOT about: `hub_settings`, `hub_user` and `hub_role_activation` carry no
/// underscore and are not system tables — they travel by their own sections, under their own rules
/// (ADR-0195 §3/§4, ADR-0252). The `_hub_*` namespace is the runtime's own bookkeeping, and nothing
/// in it has ever been a section.
///
/// Folded case because both engines fold it (Postgres lowercases unquoted identifiers, SQLite is
/// case-insensitive): `_HUB_FISCAL_PROFILE` and `_hub_fiscal_profile` are the SAME table and must
/// not mean different things to a guard.
pub fn is_system_table(table: &str) -> bool {
    table.to_ascii_lowercase().starts_with(SYSTEM_TABLE_PREFIX)
}

/// Keys of `hub_settings` that may travel to a hub OTHER than the one that produced the bundle
/// (ADR-0195 §4 — hub#405). Plain configuration: what kind of business this is, where it operates,
/// in which language and money it works, how it looks.
///
/// It is an ALLOWLIST, and that is the whole point: `hub_settings` is a key/value table that grows
/// by adding a row, so a denylist would leak every setting invented after it was written, until
/// someone remembered to go back and forbid it. Here a new key is born NON-portable and travels
/// only once somebody decides it is configuration — the cost of the mistake is «my template did not
/// bring the palette», not «this hub is invoicing under another company's tax id».
///
/// Deliberately OUT: `business_tax_id` / `business_legal_name` / `business_address` (the fiscal
/// identity of ONE business — and exactly what the dispatcher's fiscal gate reads to decide the hub
/// may issue, ADR-0203), `notify_allowed_recipients` (the origin's own contacts, and the allowlist
/// that authorises sending to them) and `api_docs_enabled` (a security switch of the destination:
/// a file someone downloaded must not open this hub's API docs).
pub const PORTABLE_SETTING_KEYS: [&str; 6] = [
    "country_code",
    "region_code",
    "currency",
    "currency_decimals",
    "language",
    "theme_palette",
];

/// Is this `hub_settings` key plain configuration, i.e. may it travel to another hub?
/// See [`PORTABLE_SETTING_KEYS`] — anything not listed is not portable.
pub fn is_portable_setting(key: &str) -> bool {
    PORTABLE_SETTING_KEYS.contains(&key)
}

/// `manifest.json` del bundle — fuente de verdad del contenido (a prueba de renombres del zip).
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct BlueprintManifest {
    pub schema_version: u32,
    /// Para qué es el bundle (ADR-0195). `#[serde(default)]` ⇒ un manifest ANTERIOR a este campo
    /// se lee como [`BundlePurpose::Backup`], que es exactamente lo que es.
    #[serde(default)]
    pub purpose: BundlePurpose,
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
    /// `modules/<id>` por cada módulo con datos, [`ROLES_SECTION`] si trae juego de roles).
    pub sections: Vec<String>,
    /// Role keys the vertical switches ON in the hub that imports it (paso 2b, hub#354).
    ///
    /// Declarative on purpose — a LIST OF KEYS, never rows of `hub_role_activation`. The import
    /// walks it through the same door the administrator uses (`roles::set_active`), so the guards
    /// of hub#352 apply to a downloaded file exactly as they apply to a click: a key no installed
    /// module declares is refused, and a base or administrative one is refused too. Shipping it as
    /// a `data/roles.sql` section would have handed a bundle raw INSERTs into the table that
    /// decides which roles are live — the one place where "the write door is not somewhere to
    /// invent role keys" has to hold.
    ///
    /// `#[serde(default)]` ⇒ a bundle older than this field pre-activates nothing, which is what
    /// the four published blueprints do today.
    #[serde(default)]
    pub active_roles: Vec<String>,
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
    /// Para qué es el bundle (ADR-0195). **Manda sobre los checkboxes**: con
    /// [`BundlePurpose::Template`], `users`/`fiscal` se ignoran aunque vengan a `true`.
    pub purpose: BundlePurpose,
}

/// Fila de la tabla de selección: el módulo va al manifest; `with_data` añade `data/<id>.sql`.
#[derive(Debug, Clone)]
pub struct ModuleDataSelection {
    pub module_id: String,
    pub with_data: bool,
    /// Tablas del módulo a volcar. `None` = todas las suyas (lo que manda el shell hoy, y lo que
    /// significaba `with_data` antes de existir este campo).
    ///
    /// Es la **herramienta del operador** (hub#534): quien monta una plantilla deja fuera lo que no
    /// quiere publicar —las 25-28 citas pasadas, los ajustes de agenda del salón de origen— sin que
    /// nadie toque código. **No es un control de seguridad**, y por eso vive en el formulario: la
    /// garantía de una plantilla oficial es que la hacemos nosotros y la revisamos **viendo su
    /// contenido** (saas#1257).
    ///
    /// **ACOTA, nunca amplía** — misma propiedad que `settings_items` desde hub#405. Marcar aquí
    /// `invoice_series_series` en una plantilla no la mete: la regla del `purpose`
    /// ([`TEMPLATE_EXCLUDED_TABLES`]) es el suelo, y una casilla no puede levantarlo. Si pudiera,
    /// esta comodidad sería la puerta por la que vuelve justo lo que se decidió que no viaja.
    pub tables: Option<Vec<String>>,
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
    // ADR-0195: una PLANTILLA es un artefacto público. Las secciones de identidad y fiscal no se
    // «desmarcan» — no entran en el bundle, decida lo que decida el formulario. Una casilla no es
    // un control: la plantilla `restaurante` publicada llevaba 4 cuentas con rol y `pin_hash`
    // legacy con la sal DENTRO del zip descargable (Demo/admin, PIN `0000`).
    let carries_identity = selection.purpose.allows_identity_sections();
    // `fiscal` EFECTIVO: el certificado y la identidad fiscal del negocio (NIF, entorno,
    // auto_transmit) son del hub de ORIGEN, así que siguen la misma regla.
    let fiscal = selection.fiscal && carries_identity;
    if selection.users && carries_identity {
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
        // hub#464: the profile and preferences are half of «the person comes back whole». `hub_user`
        // carries name/role/PIN/access-email, but the display name, avatar, profile email
        // (`hub_user_profile`) and the language/theme/palette choices (`hub_user_pref`) live in their
        // own hub-scoped tables. Both key on `(hub_id, user_id)` and were left out of the export, so
        // restoring a backup reset every profile to blank — the person could log in, then had to redo
        // their preferences and retype their name. Same identity gate as `hub_user`: identity sections
        // never travel in a template (`carries_identity`), so a published blueprint still carries no
        // personal data.
        for table in ["hub_user_profile", "hub_user_pref"] {
            let rows = fetch_rows(db, table, Some(hub_id)).await.unwrap_or_default();
            if !rows.is_empty() {
                files.insert(
                    format!("data/{table}.sql"),
                    rows_to_sql(table, &rows, hub_id).into_bytes(),
                );
            }
        }
        sections.push("hub_users".into());
    }
    if selection.settings {
        let mut rows = fetch_rows(db, "hub_settings", Some(hub_id)).await.unwrap_or_default();
        if let Some(keys) = &selection.settings_items {
            // Paso de ajustes ítem a ítem: solo las claves marcadas.
            rows.retain(|r| r.get("key").and_then(|k| k.as_str()).map(|k| keys.iter().any(|w| w == k)).unwrap_or(false));
        }
        // ADR-0195 §4 (hub#405): a TEMPLATE only carries CONFIGURATION. `hub_settings` holds, in
        // the same table, what a sector template is for (country, currency, language, palette) and
        // the fiscal identity of ONE business — tax id, legal name, address — plus its contacts and
        // switches. Dumping it whole put the origin's NIF inside a published artefact, and the hub
        // that imported it went on to issue documents under that NIF (ADR-0203 reads exactly those
        // keys to let a sale be invoiced).
        //
        // The allowlist runs HERE, in the engine, and not on `settings_items`: the caller narrows,
        // it never widens. The shell sends `settings_items: null` («all of them»), which is fine
        // precisely because «all of them» is now decided by the rule and not by the form — the same
        // lesson as the identity sections above: a checkbox is not a control.
        if !carries_identity {
            rows.retain(|r| {
                r.get("key").and_then(|k| k.as_str()).map(is_portable_setting).unwrap_or(false)
            });
        }
        files.insert("data/hub_settings.sql".into(), rows_to_sql("hub_settings", &rows, hub_id).into_bytes());
        sections.push("hub_settings".into());
    }
    // fiscal/media: el runtime solo REGISTRA la sección; los bytes (certificado, imágenes)
    // los añade el server al empaquetar (gestor media ADR-0047 / almacén del certificado).
    if fiscal {
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
            // Casillas por tabla del formulario (hub#534). Se interseca con las que el módulo POSEE,
            // así que la selección no puede nombrar la tabla de otro ni una que no exista: acota
            // dentro de lo que ya se iba a volcar. Lo que la regla del `purpose` deja fuera sigue
            // fuera —se filtra más abajo, no aquí— porque el llamador nunca amplía.
            .filter(|t| match &m.tables {
                Some(marcadas) => marcadas.iter().any(|s| s == *t),
                None => true,
            })
            .cloned()
            .collect();
        order_by_dependency(db, &mut mine).await;

        let mut sql = String::new();
        for table in &mine {
            // La identidad fiscal del NEGOCIO (NIF y nombre del emisor, entorno, auto_transmit,
            // certificado) solo viaja si se marca `fiscal` —la sección que ya mueve el `.p12`—.
            // Iba como una tabla más del módulo, así que el blueprint publicado sembraba el NIF
            // del hub demo y `auto_transmit=1` en el hub de cada cliente que lo importaba.
            if table == "verifactu_config" && !fiscal {
                continue;
            }
            // Y una PLANTILLA tampoco trae las decisiones fiscales del negocio que la importa
            // (hub#533): la serie de facturación y su libro de números entregados. Ver
            // `TEMPLATE_EXCLUDED_TABLES` — es el suelo del core, por debajo de lo que el operador
            // elige tabla a tabla al exportar.
            if selection.purpose.is_template() && TEMPLATE_EXCLUDED_TABLES.contains(&table.as_str()) {
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

    // ── El juego de ROLES del vertical (paso 2b, hub#354) ────────────────────
    // Las CLAVES que este hub tiene encendidas, declarativas en el manifest: nunca filas de
    // `hub_role_activation` en un `data/*.sql`. Así el bundle no puede escribir a mano en la tabla
    // que decide qué roles están vivos — al importar, cada clave pasa por `roles::set_active`, la
    // misma puerta que usa el administrador, y ahí es donde se rechaza lo que nadie declara y lo
    // administrativo.
    //
    // Sin casilla, a propósito, y en las dos puntas: el juego de roles es lo que ES el vertical, no
    // un extra que se marca (y una casilla nunca ha sido un control aquí — ADR-0195). Tampoco lo
    // filtra `purpose`: un rol es vocabulario del negocio, no la identidad de nadie — de hecho es
    // la mitad de ADR-0195 §5 que SÍ viaja («una plantilla activa ROLES, nunca crea usuarios»).
    //
    // Se vuelca lo que el hub tiene encendido, sin comprobar si sigue declarado: quien decide es el
    // CONSUMIDOR (mismo criterio que las identidades y la cadena fiscal), que además es el único
    // que sabe qué módulos acabará teniendo instalados.
    let active_roles: Vec<String> = crate::roles::active_keys(db, hub_id)
        .await
        .unwrap_or_default()
        .into_iter()
        .collect();
    if !active_roles.is_empty() {
        sections.push(ROLES_SECTION.to_string());
    }

    // ── Manifest (fuente de verdad) + integridad ─────────────────────────────
    let mut sha256 = BTreeMap::new();
    for (path, bytes) in &files {
        sha256.insert(path.clone(), sha256_hex(bytes));
    }
    let manifest = BlueprintManifest {
        schema_version: SCHEMA_VERSION,
        purpose: selection.purpose,
        name: name.to_string(),
        locale: locale.to_string(),
        hub: HubMeta {
            name: setting(db, hub_id, "business_name").await.unwrap_or_default(),
            country: setting(db, hub_id, "country").await.unwrap_or_else(|| "ES".into()),
            currency: setting(db, hub_id, "currency").await.unwrap_or_else(|| "EUR".into()),
            hub_id: hub_id.to_string(),
        },
        created_at: created_at.to_string(),
        modules: manifest_modules,
        sections,
        active_roles,
        sha256,
    };
    Ok(ExportBundle { manifest, files })
}

/// Una tabla del módulo y cuántas filas volcaría el export (hub#534).
#[derive(Debug, Clone, Serialize)]
pub struct TableCount {
    pub table: String,
    pub rows: i64,
}

/// Las tablas de un módulo instalado, con su recuento.
#[derive(Debug, Clone, Serialize)]
pub struct ModuleTables {
    pub module_id: String,
    pub tables: Vec<TableCount>,
}

/// Qué tablas tiene cada módulo y **cuántas filas** volcaría el export de cada una (hub#534).
///
/// Es lo que hace que la lista de casillas sea una decisión y no una fila de nombres: «Citas: 28»
/// es lo que hace que quien monta la plantilla las desmarque. Mismo argumento que el resumen del
/// publicador (saas#1257) — sin el número, mirar no sirve de nada.
///
/// **Cuenta lo que se volcaría de verdad**, no `SELECT count(*)`: reutiliza `fetch_rows`/
/// `fetch_join_rows`, así que aplica el mismo acotado por hub, la misma exclusión de soft-deleted y
/// la misma de filas sembradas por el módulo ([`is_module_seeded`]). Un número que no casara con lo
/// que sale sería peor que no darlo.
///
/// **Una tabla vacía se declara con su 0, nunca se omite**: si desaparece de la lista, quien monta
/// la plantilla no puede saber que existe — y el 0 es justo la información.
pub async fn module_table_counts(
    rt: &Runtime,
    hub_id: &str,
    module_ids: &[String],
) -> crate::Result<Vec<ModuleTables>> {
    let db = rt.db();
    let all_tables = list_tables(db).await?;
    let installed_ids: Vec<String> = rt.registry().installed.iter().map(|m| m.id.clone()).collect();

    let mut out = Vec::with_capacity(module_ids.len());
    for module_id in module_ids {
        if !rt.registry().is_installed(module_id) {
            continue;
        }
        let mut tables = Vec::new();
        for table in all_tables
            .iter()
            .filter(|t| table_owner(t, &installed_ids).as_deref() == Some(module_id.as_str()))
        {
            let rows = if has_column(db, table, "hub_id").await {
                fetch_rows(db, table, Some(hub_id)).await.unwrap_or_default().len()
            } else {
                fetch_join_rows(db, table, hub_id).await.unwrap_or_default().len()
            };
            tables.push(TableCount { table: table.clone(), rows: rows as i64 });
        }
        // Por volumen descendente: lo gordo es lo que hay que ver primero. Empate → por nombre, para
        // que dos cargas de la misma pantalla den la misma lista.
        tables.sort_by(|a, b| b.rows.cmp(&a.rows).then_with(|| a.table.cmp(&b.table)));
        out.push(ModuleTables { module_id: module_id.clone(), tables });
    }
    Ok(out)
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
///
/// Las tablas de SISTEMA del hub ([`is_system_table`]) no son de nadie: ni se exportan ni se
/// borran, porque el reset es el espejo de este mismo inventario (`reset.rs`). Sin esta línea la
/// regla del prefijo se las daría a un módulo llamado `_hub` — hoy no existe ninguno, y «hoy no
/// existe» es justo lo que ADR-0273 D8 (hub#560) pide dejar de dar por supuesto.
pub(crate) fn table_owner(table: &str, installed_ids: &[String]) -> Option<String> {
    if is_system_table(table) {
        return None;
    }
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

/// Una **clave natural** de la tabla: las columnas de un índice ÚNICO que NO es la clave primaria.
///
/// Es la identidad REAL del dato, la que el negocio reconoce — el `code` de una serie de
/// facturación, el `sku` de un producto, la `key` de una categoría fiscal— frente al `id`, que es
/// identidad técnica y cambia de instalación a instalación. Sale del CATÁLOGO de la BD del hub
/// DESTINO (no se adivina por el nombre ni se declara en el manifest de módulo): lo que decide si
/// un INSERT choca es el índice que está creado ahí, no lo que diga un fichero.
pub(crate) struct NaturalKey {
    /// Columnas del índice único.
    pub(crate) cols: Vec<String>,
    /// Condiciones `columna = literal` del predicado, cuando el índice es PARCIAL
    /// (`… WHERE is_deleted = 0`). Sin ellas la guarda miraría filas que el índice no cubre y
    /// saltaría una fila que sí cabía (una serie borrada no impide volver a crear su código).
    pub(crate) predicate: Vec<(String, String)>,
}

/// Claves naturales DECLARADAS por `table` en la BD (índices únicos no primarios), leídas del
/// catálogo (ADR-0154: Postgres, esquema activo).
///
/// **Fail-open y a propósito**: un índice que no se pueda leer con certeza —sobre expresiones
/// (`lower(email)`), con columnas `INCLUDE`, o con un predicado que no sea una conjunción de
/// `columna = literal`— se DESCARTA en vez de traducirse a medias. Una guarda construida a partir
/// de un índice mal entendido saltaría filas legítimas en silencio, que es peor que el fallo ruidoso
/// que ya teníamos. Lo que se descarta aquí se comporta como antes de hub#753.
pub(crate) async fn natural_keys(db: &dyn erplora_db::DatabaseAdapter, table: &str) -> Vec<NaturalKey> {
    if !safe_ident(table) {
        return Vec::new();
    }
    let sql = format!(
        "SELECT i.indnatts::int AS natts, i.indnkeyatts::int AS nkeyatts, \
                pg_get_expr(i.indpred, i.indrelid) AS predicate, \
                (SELECT string_agg(a.attname, ',' ORDER BY a.attnum) FROM pg_attribute a \
                  WHERE a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey)) AS cols \
         FROM pg_index i \
         JOIN pg_class c ON c.oid = i.indrelid \
         JOIN pg_namespace n ON n.oid = c.relnamespace \
         WHERE c.relname = '{table}' AND n.nspname = current_schema() \
           AND i.indisunique AND NOT i.indisprimary AND i.indisvalid"
    );
    let Ok(res) = db.query(&sql, &erplora_db::Params::new()).await else { return Vec::new() };
    res.rows
        .iter()
        .filter_map(|r| {
            let natts = r.get("natts")?.as_i64()?;
            let nkeyatts = r.get("nkeyatts")?.as_i64()?;
            // Columnas `INCLUDE`: no participan en la unicidad. Meterlas en la guarda la haría
            // MÁS estricta que el índice y la fila volvería a chocar.
            if natts != nkeyatts {
                return None;
            }
            let cols: Vec<String> = r
                .get("cols")
                .and_then(|v| v.as_str())?
                .split(',')
                .map(str::to_string)
                .collect();
            // Menos columnas que las del índice ⇒ alguna es una EXPRESIÓN (`attnum` 0, sin fila en
            // `pg_attribute`): la guarda sería más laxa que el índice y saltaría filas legítimas.
            if cols.len() as i64 != nkeyatts || !cols.iter().all(|c| safe_ident(c)) {
                return None;
            }
            let predicate = match r.get("predicate").and_then(|v| v.as_str()) {
                None | Some("") => Vec::new(),
                Some(expr) => parse_index_predicate(expr)?,
            };
            Some(NaturalKey { cols, predicate })
        })
        .collect()
}

/// Traduce el predicado de un índice PARCIAL (`pg_get_expr`) a pares `(columna, literal)`.
///
/// Solo entiende una conjunción de igualdades contra un literal —`(is_deleted = 0)`, que es la
/// forma que usan los módulos—; cualquier otra cosa (`source_id IS NOT NULL`, un `OR`, una llamada
/// a función) devuelve `None` y su índice se descarta entero. Fail-open deliberado: ver
/// [`natural_keys`].
fn parse_index_predicate(expr: &str) -> Option<Vec<(String, String)>> {
    let mut out = Vec::new();
    for part in expr.split(" AND ") {
        let part = part.trim().trim_start_matches('(').trim_end_matches(')').trim();
        let (col, lit) = part.split_once('=')?;
        let (col, lit) = (col.trim(), lit.trim());
        if !safe_ident(col) {
            return None;
        }
        // Literal escalar: número o cadena entrecomillada. Nada de casts (`'x'::text`) ni funciones.
        let numeric = !lit.is_empty() && lit.chars().all(|c| c.is_ascii_digit() || c == '.' || c == '-');
        let quoted = lit.len() >= 2 && lit.starts_with('\'') && lit.ends_with('\'') && !lit[1..lit.len() - 1].contains('\'');
        if !numeric && !quoted {
            return None;
        }
        out.push((col.to_string(), lit.to_string()));
    }
    (!out.is_empty()).then_some(out)
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
    // Postgres-only (ADR-0154), scoped to the active schema (`current_schema()`). The joins MUST
    // also match `constraint_schema`: constraint names are only unique per schema, and joining by
    // name alone pulls homonymous constraints from every other schema (duplicated FKs + a
    // combinatorial join on databases with many schemas).
    let sql = format!(
        "SELECT kcu.column_name AS col_from, ccu.column_name AS col_to, \
                ccu.table_name AS parent \
         FROM information_schema.table_constraints tc \
         JOIN information_schema.key_column_usage kcu \
           ON kcu.constraint_schema = tc.constraint_schema \
          AND kcu.constraint_name = tc.constraint_name \
         JOIN information_schema.constraint_column_usage ccu \
           ON ccu.constraint_schema = tc.constraint_schema \
          AND ccu.constraint_name = tc.constraint_name \
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
    use erplora_db::{DatabaseAdapter, testutil::fresh_db};

    /// El manifest hace round-trip serde sin perder campos: es el contrato del fichero
    /// `manifest.json` (la fuente de verdad del bundle, a prueba de renombres del zip).
    #[test]
    fn manifest_serde_round_trip() {
        let m = BlueprintManifest {
            schema_version: SCHEMA_VERSION,
            purpose: BundlePurpose::Backup,
            name: "barberia".into(),
            locale: "es".into(),
            hub: HubMeta {
                name: "Demo".into(),
                country: "ES".into(),
                currency: "EUR".into(),
                hub_id: "6c9e7a52-0f1b-4b2e-9c1d-2f8a5e3d7b10".into(),
            },
            created_at: "2026-07-11T18:00:00Z".into(),
            modules: vec![ManifestModule { id: "taxes".into(), version: "2.1.1".into(), with_data: true }],
            sections: vec!["hub_settings".into(), "modules/taxes".into()],
            active_roles: Vec::new(),
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

    /// ADR-0195 §4 (hub#405): of `hub_settings`, only CONFIGURATION leaves the hub that owns it.
    /// The identity of the business — and the switches that guard it — stay behind, and a key
    /// nobody has classified stays behind too: the list is an allowlist, so a setting added
    /// tomorrow is born non-portable instead of leaking until someone remembers it.
    #[test]
    fn only_configuration_settings_are_portable() {
        for key in PORTABLE_SETTING_KEYS {
            assert!(is_portable_setting(key), "`{key}` is plain configuration and must travel");
        }
        for key in [
            "business_tax_id",
            "business_legal_name",
            "business_address",
            crate::host_notify::ALLOWED_RECIPIENTS_SETTING,
            "api_docs_enabled",
        ] {
            assert!(
                !is_portable_setting(key),
                "`{key}` is identity, a contact of the origin business or a security switch: it must NOT travel"
            );
        }
        // A key nobody classified — a printer address, a module's API key, tomorrow's setting.
        assert!(!is_portable_setting("printer_ip"), "an unknown key is not portable by default");
        assert!(!is_portable_setting(""), "an empty key is not portable either");
    }

    /// **The hub's OWN system tables belong to no module** — ADR-0273 D8 (hub#560).
    ///
    /// `table_owner` is the single inventory both the export and the reset walk (`reset.rs` is its
    /// mirror), so a system table that no module can own is a table no bundle can dump and no reset
    /// can clear. The prefix rule would otherwise hand every `_hub_*` table to a module id of
    /// `_hub`: today no such module exists, which is exactly the kind of «it holds by accident»
    /// this names out loud.
    #[test]
    fn a_system_table_belongs_to_no_module() {
        let installed = vec!["_hub".to_string(), "inventory".to_string()];
        for table in [
            "_hub_fiscal_profile",
            "_hub_fiscal_regime_registry",
            "_hub_certificate",
            "_hub_import_row",
        ] {
            assert!(is_system_table(table), "`{table}` is a system table of the hub");
            assert_eq!(table_owner(table, &installed), None, "`{table}` is nobody's to export");
        }
        // The rule is about the `_hub_*` namespace, not about everything that says «hub»: the
        // shared tables of the hub travel by their own sections and must keep doing so.
        for table in ["hub_settings", "hub_user", "hub_role_activation"] {
            assert!(!is_system_table(table), "`{table}` has its own section, it is not a system table");
        }
        assert_eq!(table_owner("inventory_product", &installed).as_deref(), Some("inventory"));
    }

    /// Constraint names are only unique PER SCHEMA: two schemas holding the same tables carry
    /// identically-named FKs. The catalog query must not join `key_column_usage` /
    /// `constraint_column_usage` rows that belong to a homonymous constraint in ANOTHER schema —
    /// doing so returns the same FK duplicated (and, with many schemas, the join explodes
    /// combinatorially: the 100%-CPU incident on the shared test database, 2026-08-06).
    #[tokio::test]
    async fn foreign_keys_ignores_homonymous_constraints_in_other_schemas() {
        let db_a = fresh_db().await;
        let db_b = fresh_db().await;
        let ddl = "CREATE TABLE fk_parent (id TEXT PRIMARY KEY); \
                   CREATE TABLE fk_child (id TEXT PRIMARY KEY, \
                     parent_id TEXT CONSTRAINT fk_child_parent REFERENCES fk_parent(id));";
        db_a.execute_batch(ddl).await.unwrap();
        db_b.execute_batch(ddl).await.unwrap();

        let fks = foreign_keys(&db_a, "fk_child").await;
        assert_eq!(
            fks.len(),
            1,
            "one declared FK must come back exactly once, not multiplied by other schemas' homonyms"
        );
        assert_eq!(fks[0].from, "parent_id");
        assert_eq!(fks[0].parent, "fk_parent");
        assert_eq!(fks[0].to, "id");
    }
}
