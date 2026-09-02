//! API keys de la **API pública por módulo** (ADR-0057, `architecture/hub/public-api.md`).
//!
//! Una API key es una credencial **LOCAL** del hub (validada por el runtime, identidad
//! local-autoritativa — hermana del login por PIN / `X-Hub-Session`), **no** un plano Hub↔Cloud.
//! La gestiona un admin (owner/admin) en *Usuarios → API keys*. Cada key lleva un **scope =
//! matriz de módulos × {lectura, escritura}**; el runtime la **expande** a los `permission` de las
//! queries (`read`) y commands (`write`) `expose_api` de cada módulo y resuelve la petición al
//! **mismo `RequestContext { hub_id, user_id, permissions }`** que ya consume el dispatcher → todo
//! el gating existente funciona sin tocarse (§6/§7).
//!
//! ## Credencial
//! Token bearer **opaco** con formato `erpl_live_<id>_<secret>`:
//!  - `id`      — uuid v4 (sin guiones), localiza la fila `hub_api_key`.
//!  - `secret`  — 32 bytes aleatorios en hex (alta entropía), **hasheado** con argon2id (mismo
//!    helper que el PIN, [`crate::identity`]). Solo se guarda el hash; el token en claro se
//!    devuelve **UNA sola vez** al crear/rotar.
//!  - `prefix`  — primeros chars visibles del token (`erpl_live_<id8>…`), para que la UI muestre
//!    una etiqueta reconocible sin revelar el secreto.
//!
//! El secreto vive **solo en el runtime Rust**: el navegador nunca lo ve (las rutas de gestión las
//! sirve el server con sesión admin, y el data-surface lo consume el tercero directo con su Bearer).
use erplora_db::{DatabaseAdapter, Params};
use serde_json::json;

use crate::errors::Result;
use crate::identity::{hash_secret_argon2, verify_secret_argon2};
use crate::registry::{new_id, now_rfc3339, Registry, RequestContext};

/// Prefijo de marca + entorno del token (`erpl` = ERPlora, `live` = producción). El diseño deja
/// abierto un `erpl_test_…` futuro (decisión menor §9); hoy solo `live`.
pub const TOKEN_PREFIX: &str = "erpl_live_";

/// Estado de una API key.
pub const STATUS_ACTIVE: &str = "active";
pub const STATUS_REVOKED: &str = "revoked";

/// Cuota conservadora por defecto para una integración nueva. Se persiste por key y se consume
/// con un contador atómico en PostgreSQL, por lo que no se reinicia al reiniciar el contenedor.
pub const DEFAULT_RATE_LIMIT_PER_MINUTE: i64 = 60;
pub const MAX_RATE_LIMIT_PER_MINUTE: i64 = 10_000;

/// Una entrada del scope de una key: un módulo y si concede lectura/escritura (§7).
/// `read` → permisos de las queries `expose_api` del módulo; `write` → los de sus commands.
#[derive(Debug, Clone, PartialEq, Eq, serde::Serialize, serde::Deserialize)]
pub struct ScopeEntry {
    pub module: String,
    #[serde(default)]
    pub read: bool,
    #[serde(default)]
    pub write: bool,
}

/// What a key may do, expressed the same way a user's role is (hub#504, ADR-0057 §7 extended).
///
/// The per-module matrix ([`ApiKeyAccess::Custom`]) is what ADR-0057 shipped, and it cannot say
/// "everything this hub reads": a module installed **after** the key was issued is not in the
/// matrix, so a key meant as "read-only integration" would silently stop covering the business as
/// it grows. The three blanket modes say it once and keep saying it.
#[derive(Debug, Clone, Copy, Default, PartialEq, Eq, serde::Serialize, serde::Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ApiKeyAccess {
    /// Read and write on every module with a public API, present and future.
    Full,
    /// Reads everything, writes nothing. What the hub issues to our own app.
    ReadOnly,
    /// Writes everything, reads nothing (an inbound feed that must not be able to look around).
    WriteOnly,
    /// The per-module checkboxes. Default because that is what every key written before this
    /// existed carries, and because a key that says nothing must grant nothing.
    #[default]
    Custom,
}

/// The whole permission of a key: a mode plus, when the mode is [`ApiKeyAccess::Custom`], the
/// per-module checkboxes.
///
/// Persisted in `scope_json`. **Two shapes are accepted on the way in**: the object written since
/// hub#504 (`{"access":…,"modules":[…]}`) and the bare array ADR-0057 wrote
/// (`[{"module":…,"read":…,"write":…}]`), which reads back as `Custom` with those modules — a key
/// issued before this change keeps exactly the permissions it had. On the way out only the object
/// is written.
#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct ApiKeyScope {
    pub access: ApiKeyAccess,
    pub modules: Vec<ScopeEntry>,
}

impl ApiKeyScope {
    /// The per-module matrix of ADR-0057 (`Custom`).
    pub fn custom(modules: Vec<ScopeEntry>) -> Self {
        Self {
            access: ApiKeyAccess::Custom,
            modules,
        }
    }

    /// A blanket mode (no matrix).
    pub fn blanket(access: ApiKeyAccess) -> Self {
        Self {
            access,
            modules: Vec::new(),
        }
    }

    /// May this key read **anything**? The question the event stream asks: a channel that only
    /// pushes is a read, so a write-only key has no business listening on it.
    pub fn can_read(&self) -> bool {
        match self.access {
            ApiKeyAccess::Full | ApiKeyAccess::ReadOnly => true,
            ApiKeyAccess::WriteOnly => false,
            ApiKeyAccess::Custom => self.modules.iter().any(|m| m.read),
        }
    }

    /// May this key write **anything**?
    pub fn can_write(&self) -> bool {
        match self.access {
            ApiKeyAccess::Full | ApiKeyAccess::WriteOnly => true,
            ApiKeyAccess::ReadOnly => false,
            ApiKeyAccess::Custom => self.modules.iter().any(|m| m.write),
        }
    }
}

impl serde::Serialize for ApiKeyScope {
    fn serialize<S: serde::Serializer>(&self, s: S) -> std::result::Result<S::Ok, S::Error> {
        use serde::ser::SerializeStruct;
        let mut out = s.serialize_struct("ApiKeyScope", 2)?;
        out.serialize_field("access", &self.access)?;
        out.serialize_field("modules", &self.modules)?;
        out.end()
    }
}

impl<'de> serde::Deserialize<'de> for ApiKeyScope {
    fn deserialize<D: serde::Deserializer<'de>>(d: D) -> std::result::Result<Self, D::Error> {
        #[derive(serde::Deserialize)]
        #[serde(untagged)]
        enum Wire {
            /// Since hub#504.
            Modern {
                #[serde(default)]
                access: ApiKeyAccess,
                #[serde(default)]
                modules: Vec<ScopeEntry>,
            },
            /// ADR-0057's bare matrix.
            Legacy(Vec<ScopeEntry>),
        }
        Ok(match Wire::deserialize(d)? {
            Wire::Modern { access, modules } => ApiKeyScope { access, modules },
            Wire::Legacy(modules) => ApiKeyScope::custom(modules),
        })
    }
}

/// `created_by` of a key **the hub issued to itself**. Every key a human creates carries
/// `hub_user:<id>`, written server-side from the admin's session, so this value cannot be forged
/// through the management API: it is the mark that says "nobody may delete this".
pub const SYSTEM_CREATED_BY: &str = "system";

/// The name of the key our own app reads the event stream with. One per hub.
pub const APP_KEY_NAME: &str = "ERPlora app";

/// Refusal code for the management doors when the target is a key the hub issued to itself.
pub const ERR_KEY_IS_SYSTEM: &str = "api_key.system_key";

/// Metadatos de una API key (lo que se devuelve en listados/altas — **sin** el secreto).
#[derive(Debug, Clone, serde::Serialize)]
pub struct ApiKeyInfo {
    pub id: String,
    pub name: String,
    pub prefix: String,
    pub scope: Vec<ScopeEntry>,
    /// The mode of [`ApiKeyScope`]. Additive on the wire: a client that predates hub#504 ignores it.
    pub access: ApiKeyAccess,
    /// `true` = issued by the hub to itself; the UI offers no delete for it and the doors refuse.
    pub system: bool,
    pub status: String,
    pub created_at: String,
    pub last_used_at: Option<String>,
    pub rate_limit_per_minute: i64,
}

/// Resultado de crear/rotar una key: el secreto en claro (mostrado **UNA vez**) + metadatos.
#[derive(Debug, Clone, serde::Serialize)]
pub struct ApiKeySecret {
    pub id: String,
    pub name: String,
    /// El token completo `erpl_live_<id>_<secret>`. Se muestra una sola vez; no se persiste.
    pub secret: String,
    pub prefix: String,
    pub scope: Vec<ScopeEntry>,
    pub access: ApiKeyAccess,
    pub rate_limit_per_minute: i64,
}

/// Principal autenticado antes de consumir su cuota. Mantiene el id separado del `user_id`
/// para que el rate limiter nunca tenga que volver a parsear una identidad textual.
#[derive(Debug, Clone)]
pub struct ApiKeyPrincipal {
    pub key_id: String,
    pub rate_limit_per_minute: i64,
    /// What this key is allowed to do, as stored — not as expanded into permissions. The event
    /// stream (hub#504) asks it "may you read at all?", a question no single module permission
    /// can answer.
    pub scope: ApiKeyScope,
    pub context: RequestContext,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct RateLimitDecision {
    pub allowed: bool,
    pub limit: i64,
    pub remaining: i64,
    pub retry_after_seconds: i64,
}

/// Genera un secreto aleatorio (32 bytes → 64 hex). Alta entropía (no es un PIN corto).
///
/// Público porque **toda** credencial del hub sale de aquí: la del server para los tickets del
/// canal de eventos (hub#504) incluida. Un segundo generador es un segundo sitio donde equivocarse
/// de fuente de entropía.
pub fn random_secret() -> String {
    use argon2::password_hash::rand_core::{OsRng, RngCore};
    let mut bytes = [0u8; 32];
    OsRng.fill_bytes(&mut bytes);
    bytes.iter().map(|b| format!("{b:02x}")).collect()
}

/// Construye el token en claro a partir de id + secreto: `erpl_live_<id>_<secret>`.
fn build_token(id: &str, secret: &str) -> String {
    format!("{TOKEN_PREFIX}{id}_{secret}")
}

/// Prefijo visible para la UI: `erpl_live_<primeros 8 del id>…`. No revela el secreto.
fn prefix_for(id: &str) -> String {
    let head: String = id.chars().take(8).collect();
    format!("{TOKEN_PREFIX}{head}…")
}

/// Parsea un token `erpl_live_<id>_<secret>` → `(id, secret)`. `None` si no tiene el formato.
/// El `id` es un uuid sin guiones (solo hex), así que el primer `_` tras el prefijo separa
/// id de secreto sin ambigüedad.
pub fn parse_token(token: &str) -> Option<(String, String)> {
    let rest = token.strip_prefix(TOKEN_PREFIX)?;
    let (id, secret) = rest.split_once('_')?;
    if id.is_empty() || secret.is_empty() {
        return None;
    }
    Some((id.to_string(), secret.to_string()))
}

/// Reads `scope_json` back. An unreadable value grants **nothing** (`Custom` with no modules):
/// the only safe reading of a permission nobody can parse.
fn scope_of_row(row: &serde_json::Value) -> ApiKeyScope {
    row["scope_json"]
        .as_str()
        .and_then(|s| serde_json::from_str(s).ok())
        .unwrap_or_default()
}

fn row_to_info(row: &serde_json::Value) -> ApiKeyInfo {
    let scope = scope_of_row(row);
    ApiKeyInfo {
        id: row["id"].as_str().unwrap_or_default().to_string(),
        name: row["name"].as_str().unwrap_or_default().to_string(),
        prefix: row["prefix"].as_str().unwrap_or_default().to_string(),
        access: scope.access,
        system: row["created_by"].as_str() == Some(SYSTEM_CREATED_BY),
        scope: scope.modules,
        status: row["status"].as_str().unwrap_or_default().to_string(),
        created_at: row["created_at"].as_str().unwrap_or_default().to_string(),
        last_used_at: row["last_used_at"].as_str().map(|s| s.to_string()),
        rate_limit_per_minute: row["rate_limit_per_minute"]
            .as_i64()
            .unwrap_or(DEFAULT_RATE_LIMIT_PER_MINUTE),
    }
}

/// Crea una API key para `hub_id` con `scope`. Genera id + secreto aleatorios, guarda el secreto
/// **hasheado** (argon2id) y devuelve el token en claro **una sola vez** ([`ApiKeySecret`]).
/// `created_by` = identidad del admin que la crea (auditoría, p. ej. `hub_user:<id>`).
pub async fn create(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    name: &str,
    scope: &ApiKeyScope,
    rate_limit_per_minute: i64,
    created_by: &str,
) -> Result<ApiKeySecret> {
    if !(1..=MAX_RATE_LIMIT_PER_MINUTE).contains(&rate_limit_per_minute) {
        return Err(crate::errors::RuntimeError::Other(format!(
            "rate_limit_per_minute debe estar entre 1 y {MAX_RATE_LIMIT_PER_MINUTE}"
        )));
    }
    let id = new_id().replace('-', "");
    let secret = random_secret();
    let secret_hash = hash_secret_argon2(&secret)?;
    let prefix = prefix_for(&id);
    let scope_json = serde_json::to_string(scope).unwrap_or_else(|_| "[]".to_string());

    let mut p = Params::new();
    p.insert("id".into(), json!(id));
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("name".into(), json!(name));
    p.insert("prefix".into(), json!(prefix));
    p.insert("secret_hash".into(), json!(secret_hash));
    p.insert("scope_json".into(), json!(scope_json));
    p.insert("status".into(), json!(STATUS_ACTIVE));
    p.insert("now".into(), json!(now_rfc3339()));
    p.insert("created_by".into(), json!(created_by));
    p.insert("rate_limit_per_minute".into(), json!(rate_limit_per_minute));
    db.execute(
        "INSERT INTO hub_api_key \
          (id, hub_id, name, prefix, secret_hash, scope_json, status, created_at, last_used_at, created_by, rate_limit_per_minute) \
          VALUES (:id, :hub_id, :name, :prefix, :secret_hash, :scope_json, :status, :now, NULL, :created_by, :rate_limit_per_minute)",
        &p,
    )
    .await?;

    Ok(ApiKeySecret {
        secret: build_token(&id, &secret),
        id,
        name: name.to_string(),
        prefix,
        access: scope.access,
        scope: scope.modules.clone(),
        rate_limit_per_minute,
    })
}

/// Columns every read of a key needs. `created_by` is in the list because it carries the
/// "the hub issued this to itself" mark ([`SYSTEM_CREATED_BY`]) the delete guard reads.
const KEY_COLUMNS: &str = "id, name, prefix, scope_json, status, created_at, last_used_at, \
     created_by, rate_limit_per_minute";

/// Lista las API keys de `hub_id` (sin el secreto), ordenadas por fecha de creación desc.
pub async fn list(db: &dyn DatabaseAdapter, hub_id: &str) -> Result<Vec<ApiKeyInfo>> {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    let res = db
        .query(
            &format!(
                "SELECT {KEY_COLUMNS} FROM hub_api_key WHERE hub_id = :hub_id \
                  ORDER BY created_at DESC"
            ),
            &p,
        )
        .await?;
    Ok(res.rows.iter().map(row_to_info).collect())
}

/// **The key the hub issues to itself** (hub#504), so our own app reads the event stream through
/// the same door as everybody else instead of through a hole cut for it.
///
/// Idempotent: returns the id of the existing one, or mints it. Three properties are the design:
///
///  - **`read_only`.** The app listens; it never writes through this credential (it writes as the
///    logged-in person, with that person's permissions).
///  - **Its secret is thrown away.** Nothing ever presents this key as a bearer — the app reaches
///    it through a short-lived stream ticket bound to the key **id**. A secret nobody holds is a
///    secret nobody can leak, and there is no long-lived credential in a browser tab.
///  - **Re-issued, never restored.** A hub poured from a blueprint or restored from a backup has
///    no `hub_api_key` rows (credentials must not travel in an export, same reasoning hub#361 used
///    for the elevation window). The app asks again on connect and gets a **new** key.
///
/// If this function is ever deleted, the app stops reading the stream — loudly, on the next
/// connect. That is the intended failure: an auth hole would be silent.
pub async fn ensure_app_key(db: &dyn DatabaseAdapter, hub_id: &str) -> Result<String> {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("name".into(), json!(APP_KEY_NAME));
    p.insert("created_by".into(), json!(SYSTEM_CREATED_BY));
    p.insert("status".into(), json!(STATUS_ACTIVE));
    let res = db
        .query(
            "SELECT id FROM hub_api_key WHERE hub_id = :hub_id AND name = :name \
              AND created_by = :created_by AND status = :status ORDER BY created_at LIMIT 1",
            &p,
        )
        .await?;
    if let Some(id) = res.rows.first().and_then(|r| r["id"].as_str()) {
        return Ok(id.to_string());
    }
    let created = create(
        db,
        hub_id,
        APP_KEY_NAME,
        &ApiKeyScope::blanket(ApiKeyAccess::ReadOnly),
        DEFAULT_RATE_LIMIT_PER_MINUTE,
        SYSTEM_CREATED_BY,
    )
    .await?;
    // The plaintext token dies here, on purpose. See the doc comment.
    Ok(created.id)
}

/// Is this key one the hub issued to itself? `None` = there is no such key in this hub.
async fn is_system_key(db: &dyn DatabaseAdapter, hub_id: &str, id: &str) -> Result<Option<bool>> {
    let mut p = Params::new();
    p.insert("id".into(), json!(id));
    p.insert("hub_id".into(), json!(hub_id));
    let res = db
        .query(
            "SELECT created_by FROM hub_api_key WHERE id = :id AND hub_id = :hub_id",
            &p,
        )
        .await?;
    Ok(res
        .rows
        .first()
        .map(|r| r["created_by"].as_str() == Some(SYSTEM_CREATED_BY)))
}

fn system_key_refusal() -> crate::errors::RuntimeError {
    crate::errors::RuntimeError::Domain {
        code: ERR_KEY_IS_SYSTEM.to_string(),
        message: "this key belongs to the hub itself and cannot be rotated or revoked".into(),
    }
}

/// Rota el secreto de una key (genera uno nuevo, invalida el anterior). El `scope`/`name` se
/// preservan. Devuelve el nuevo token en claro **una sola vez**. `None` si la key no existe en
/// este hub. Rotar **re-activa** la key (status='active'): el caso de uso es "el secreto se
/// filtró, dame uno nuevo" — el secreto viejo deja de funcionar al cambiar el hash.
pub async fn rotate(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    id: &str,
) -> Result<Option<ApiKeySecret>> {
    // Lee la fila (scope/name para devolverlos) y comprueba pertenencia al hub.
    let mut p = Params::new();
    p.insert("id".into(), json!(id));
    p.insert("hub_id".into(), json!(hub_id));
    let res = db
        .query(
            &format!("SELECT {KEY_COLUMNS} FROM hub_api_key WHERE id = :id AND hub_id = :hub_id"),
            &p,
        )
        .await?;
    let Some(row) = res.rows.first() else {
        return Ok(None);
    };
    let info = row_to_info(row);
    // hub#504: the hub's own key has no secret anybody holds, so rotating it would only break the
    // app's next connect. Refused with its own code, like revoking.
    if info.system {
        return Err(system_key_refusal());
    }

    let secret = random_secret();
    let secret_hash = hash_secret_argon2(&secret)?;
    let mut up = Params::new();
    up.insert("id".into(), json!(id));
    up.insert("hub_id".into(), json!(hub_id));
    up.insert("secret_hash".into(), json!(secret_hash));
    up.insert("status".into(), json!(STATUS_ACTIVE));
    db.execute(
        "UPDATE hub_api_key SET secret_hash = :secret_hash, status = :status \
          WHERE id = :id AND hub_id = :hub_id",
        &up,
    )
    .await?;

    Ok(Some(ApiKeySecret {
        secret: build_token(id, &secret),
        id: info.id,
        name: info.name,
        prefix: info.prefix,
        scope: info.scope,
        access: info.access,
        rate_limit_per_minute: info.rate_limit_per_minute,
    }))
}

/// Revoca una key (kill-switch inmediato): `status='revoked'`. Idempotente. La fila se conserva
/// (auditoría/listado); [`verify_and_resolve`] rechaza al instante cualquier key no `active`.
/// Devuelve `false` si no existía en este hub.
pub async fn revoke(db: &dyn DatabaseAdapter, hub_id: &str, id: &str) -> Result<bool> {
    // hub#504: the key the hub issued to itself is not the admin's to revoke. Checked BEFORE the
    // UPDATE, and scoped to this hub — the neighbour's key is not this hub's business either way.
    match is_system_key(db, hub_id, id).await? {
        Some(true) => return Err(system_key_refusal()),
        Some(false) => {}
        None => return Ok(false),
    }
    let mut p = Params::new();
    p.insert("id".into(), json!(id));
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("status".into(), json!(STATUS_REVOKED));
    let res = db
        .execute(
            "UPDATE hub_api_key SET status = :status WHERE id = :id AND hub_id = :hub_id",
            &p,
        )
        .await?;
    Ok(res.affected > 0)
}

/// Expande el `scope` de una key a un conjunto de permisos, consultando el `Registry`: para cada
/// `{module, read, write}` añade el `permission` de **cada query `expose_api`** del módulo si
/// `read`, y el de **cada command `expose_api`** si `write` (§7). Solo módulos **activos** aportan
/// (el `Registry` ya filtra por estado). Es defensa-en-profundidad: el gate por operación del
/// runtime sigue siendo la autoridad — esto solo construye el `RequestContext`.
pub fn expand_scope(
    registry: &Registry,
    scope: &[ScopeEntry],
) -> std::collections::HashSet<String> {
    let mut perms = std::collections::HashSet::new();
    for entry in scope {
        if entry.read {
            for (_, q) in registry.exposed_queries(&entry.module) {
                perms.insert(q.def.permission.clone());
            }
        }
        if entry.write {
            for (_, c) in registry.exposed_commands(&entry.module) {
                perms.insert(c.def.permission.clone());
            }
        }
    }
    perms
}

/// Expands a whole [`ApiKeyScope`] to permissions (hub#504). `Custom` is [`expand_scope`]; the
/// blanket modes are the same expansion applied to **every module with a public API**, which is
/// what makes "read-only" keep meaning read-only after the next install.
pub fn expand(registry: &Registry, scope: &ApiKeyScope) -> std::collections::HashSet<String> {
    if scope.access == ApiKeyAccess::Custom {
        return expand_scope(registry, &scope.modules);
    }
    let blanket: Vec<ScopeEntry> = registry
        .modules_with_public_api()
        .into_iter()
        .map(|module| ScopeEntry {
            module,
            read: scope.can_read(),
            write: scope.can_write(),
        })
        .collect();
    expand_scope(registry, &blanket)
}

/// Verifica un token bearer `erpl_live_<id>_<secret>` y, si es válido y la key está **activa**,
/// lo resuelve al `RequestContext { hub_id, user_id="apikey:<id>", permissions }` (§6). Pasos:
///  1. parsea el token → `(id, secret)`,
///  2. busca la fila por `id` **dentro de `hub_id`** (no cruza hubs en BD compartida),
///  3. exige `status='active'` y verifica `secret` con argon2id,
///  4. **actualiza `last_used_at`** (best-effort),
///  5. expande el `scope` a permisos contra el `Registry`.
///
/// `Ok(None)` = token mal formado, key inexistente, revocada o secreto incorrecto (el server lo
/// mapea a 401). El `user_id` `apikey:<id>` queda atribuido como `:current_user_id` en las
/// escrituras (auditoría, `created_by`) sin tocar el SQL de los módulos.
pub async fn verify_and_resolve(
    db: &dyn DatabaseAdapter,
    registry: &Registry,
    hub_id: &str,
    token: &str,
) -> Result<Option<ApiKeyPrincipal>> {
    let Some((id, secret)) = parse_token(token) else {
        return Ok(None);
    };
    let Some(row) = active_key_row(db, hub_id, &id).await? else {
        return Ok(None); // inexistente, de otro hub, o revocada → kill-switch
    };
    let stored = row["secret_hash"].as_str().unwrap_or_default();
    if !verify_secret_argon2(stored, &secret) {
        return Ok(None);
    }
    Ok(Some(
        principal_from_row(db, registry, hub_id, &id, &row).await,
    ))
}

/// Resolves a key **by id, without its secret** (hub#504). The one caller is the redemption of a
/// stream ticket, which is itself a credential the hub minted moments earlier and only ever hands
/// to an authenticated session — the id is not a secret and is never accepted from a caller
/// directly.
///
/// Every other check of [`verify_and_resolve`] still applies, on purpose: this must not become a
/// way around the kill-switch or around the hub boundary.
pub async fn resolve_key_id(
    db: &dyn DatabaseAdapter,
    registry: &Registry,
    hub_id: &str,
    key_id: &str,
) -> Result<Option<ApiKeyPrincipal>> {
    let Some(row) = active_key_row(db, hub_id, key_id).await? else {
        return Ok(None);
    };
    Ok(Some(
        principal_from_row(db, registry, hub_id, key_id, &row).await,
    ))
}

/// The row of an **active** key of **this hub**, or `None`. The `hub_id` filter is not decoration:
/// several hubs share one database (ADR-0005), and an id alone would cross the boundary.
async fn active_key_row(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    id: &str,
) -> Result<Option<serde_json::Value>> {
    let mut p = Params::new();
    p.insert("id".into(), json!(id));
    p.insert("hub_id".into(), json!(hub_id));
    let res = db
        .query(
            "SELECT id, secret_hash, scope_json, status, rate_limit_per_minute FROM hub_api_key \
              WHERE id = :id AND hub_id = :hub_id",
            &p,
        )
        .await?;
    let Some(row) = res.rows.first() else {
        return Ok(None);
    };
    if row["status"].as_str() != Some(STATUS_ACTIVE) {
        return Ok(None); // revocada → kill-switch
    }
    Ok(Some(row.clone()))
}

/// Builds the principal of an already-verified row: touches `last_used_at` and expands the scope.
async fn principal_from_row(
    db: &dyn DatabaseAdapter,
    registry: &Registry,
    hub_id: &str,
    id: &str,
    row: &serde_json::Value,
) -> ApiKeyPrincipal {
    // last_used_at (best-effort: no falla la auth si el UPDATE da error).
    let mut touch = Params::new();
    touch.insert("id".into(), json!(id));
    touch.insert("hub_id".into(), json!(hub_id));
    touch.insert("now".into(), json!(now_rfc3339()));
    let _ = db
        .execute(
            "UPDATE hub_api_key SET last_used_at = :now WHERE id = :id AND hub_id = :hub_id",
            &touch,
        )
        .await;

    let scope = scope_of_row(row);
    let permissions = expand(registry, &scope);

    ApiKeyPrincipal {
        key_id: id.to_string(),
        rate_limit_per_minute: row["rate_limit_per_minute"]
            .as_i64()
            .unwrap_or(DEFAULT_RATE_LIMIT_PER_MINUTE),
        scope,
        // hub#361: a machine principal. Built HERE, at the one place an API-key context is ever
        // constructed, so no surface can forget it: an integration is never offered the PIN
        // dialog and can never be approved — it has nobody standing at it, and a stored,
        // long-lived credential must not gain a second way in.
        context: RequestContext::new(hub_id.to_string(), format!("apikey:{id}"), permissions)
            .as_machine(),
    }
}

/// Consume una unidad de la ventana actual. El UPSERT es una única sentencia PostgreSQL, así que
/// dos workers concurrentes no pueden sobrepasar la cuota por una carrera read-then-write.
pub async fn consume_rate_limit(
    db: &dyn DatabaseAdapter,
    key_id: &str,
    limit: i64,
) -> Result<RateLimitDecision> {
    consume_rate_limit_at(db, key_id, limit, chrono::Utc::now().timestamp()).await
}

async fn consume_rate_limit_at(
    db: &dyn DatabaseAdapter,
    key_id: &str,
    limit: i64,
    epoch_seconds: i64,
) -> Result<RateLimitDecision> {
    let minute = epoch_seconds.div_euclid(60);
    let mut p = Params::new();
    p.insert("key_id".into(), json!(key_id));
    p.insert("minute".into(), json!(minute));
    let result = db
        .query(
            "INSERT INTO hub_api_key_rate_window (api_key_id, window_epoch_minute, request_count) \
             VALUES (:key_id, :minute, 1) \
             ON CONFLICT (api_key_id) DO UPDATE SET \
               request_count = CASE \
                 WHEN hub_api_key_rate_window.window_epoch_minute = EXCLUDED.window_epoch_minute \
                 THEN hub_api_key_rate_window.request_count + 1 ELSE 1 END, \
               window_epoch_minute = EXCLUDED.window_epoch_minute \
             RETURNING request_count",
            &p,
        )
        .await?;
    let count = result
        .rows
        .first()
        .and_then(|r| r["request_count"].as_i64())
        .unwrap_or(limit + 1);
    Ok(RateLimitDecision {
        allowed: count <= limit,
        limit,
        remaining: (limit - count).max(0),
        retry_after_seconds: 60 - epoch_seconds.rem_euclid(60),
    })
}

#[cfg(test)]
mod tests {
    use std::sync::Arc;

    use super::*;
    use crate::manifest::{CommandDef, Manifest, QueryDef};
    use crate::registry::{ModuleStatus, RegisteredCommand, RegisteredQuery};
    use erplora_db::{testutil::fresh_db, PgAdapter};

    /// Crea la tabla `hub_api_key` a mano (en prod la crea la migración de sistema v3).
    async fn ensure_table(db: &PgAdapter) {
        db.execute_batch(
            "CREATE TABLE hub_api_key (\
              id TEXT PRIMARY KEY, hub_id TEXT NOT NULL, name TEXT NOT NULL, prefix TEXT NOT NULL, \
              secret_hash TEXT NOT NULL, scope_json TEXT NOT NULL DEFAULT '[]', \
              status TEXT NOT NULL DEFAULT 'active', created_at TEXT NOT NULL, \
              last_used_at TEXT, created_by TEXT NOT NULL DEFAULT '', \
              rate_limit_per_minute INTEGER NOT NULL DEFAULT 60);\
             CREATE TABLE hub_api_key_rate_window (\
              api_key_id TEXT PRIMARY KEY, window_epoch_minute BIGINT NOT NULL, request_count BIGINT NOT NULL);",
        )
        .await
        .unwrap();
    }

    fn query_def(permission: &str, expose: bool) -> QueryDef {
        QueryDef {
            permission: permission.to_string(),
            sql: "SELECT 1".into(),
            schema: None,
            list: None,
            ai: None,
            expose_api: expose,
        }
    }

    fn command_def(permission: &str, expose: bool) -> CommandDef {
        CommandDef {
            permission: permission.to_string(),
            reads: Vec::new(),
            transaction: false,
            sql: vec![],
            schema: None,
            emit: vec![],
            min_affected_rows: None,
            expect_rows: None,
            handler: None,
            ai: None,
            expose_api: expose,
            internal: false,
        }
    }

    /// Registry con un módulo `inventory` activo: 1 query `expose_api` + 1 command `expose_api`
    /// + 1 query privada (no expuesta) para comprobar que NO entra en el scope.
    fn registry_with_inventory() -> Registry {
        let mut reg = Registry::new();
        let manifest: Manifest = serde_json::from_str(
            r#"{ "id": "inventory", "name": "Inventory", "version": "1.0.0" }"#,
        )
        .unwrap();
        reg.installed.push(manifest);
        reg.status.insert("inventory".into(), ModuleStatus::Active);
        reg.queries.insert(
            "inventory.products.list".into(),
            RegisteredQuery {
                module_id: "inventory".into(),
                def: query_def("inventory.read", true),
                sql: "SELECT 1".into(),
                schema: None,
            },
        );
        reg.queries.insert(
            "inventory.secret.list".into(),
            RegisteredQuery {
                module_id: "inventory".into(),
                def: query_def("inventory.read_secret", false),
                sql: "SELECT 1".into(),
                schema: None,
            },
        );
        reg.commands.insert(
            "inventory.category.create".into(),
            RegisteredCommand {
                module_id: "inventory".into(),
                def: command_def("inventory.write", true),
                sql: vec![],
                wasm: None,
                schema: None,
            },
        );
        reg
    }

    #[test]
    fn parse_token_roundtrip() {
        let t = build_token("abc123", "deadbeef");
        assert_eq!(t, "erpl_live_abc123_deadbeef");
        assert_eq!(parse_token(&t), Some(("abc123".into(), "deadbeef".into())));
        assert_eq!(parse_token("nope"), None);
        assert_eq!(parse_token("erpl_live_onlyid"), None);
        assert_eq!(parse_token("erpl_live__nosecret"), None);
    }

    #[test]
    fn expand_scope_only_includes_exposed_ops() {
        let reg = registry_with_inventory();
        // read+write de inventory → permisos de la query y el command expuestos (no el privado).
        let scope = vec![ScopeEntry {
            module: "inventory".into(),
            read: true,
            write: true,
        }];
        let perms = expand_scope(&reg, &scope);
        assert!(perms.contains("inventory.read"));
        assert!(perms.contains("inventory.write"));
        assert!(
            !perms.contains("inventory.read_secret"),
            "la query privada NO entra al scope"
        );

        // Solo lectura → solo el permiso de la query expuesta.
        let read_only = vec![ScopeEntry {
            module: "inventory".into(),
            read: true,
            write: false,
        }];
        let perms = expand_scope(&reg, &read_only);
        assert!(perms.contains("inventory.read"));
        assert!(!perms.contains("inventory.write"));
    }

    #[tokio::test]
    async fn create_verify_rotate_revoke_lifecycle() {
        let db = fresh_db().await;
        ensure_table(&db).await;
        let reg = registry_with_inventory();
        let hub = "hub-1";

        let scope = ApiKeyScope::custom(vec![ScopeEntry {
            module: "inventory".into(),
            read: true,
            write: false,
        }]);
        let created = create(&db, hub, "Gestoría", &scope, 60, "hub_user:42")
            .await
            .unwrap();
        assert!(created.secret.starts_with("erpl_live_"));

        // Resuelve al contexto correcto con el permiso de la query expuesta.
        let principal = verify_and_resolve(&db, &reg, hub, &created.secret)
            .await
            .unwrap()
            .unwrap();
        let ctx = principal.context;
        assert_eq!(ctx.hub_id, hub);
        assert_eq!(ctx.user_id, format!("apikey:{}", created.id));
        assert!(ctx.permissions.contains("inventory.read"));
        assert!(!ctx.permissions.contains("inventory.write"));

        // Secreto incorrecto / token basura → None (401).
        assert!(verify_and_resolve(&db, &reg, hub, "erpl_live_x_y")
            .await
            .unwrap()
            .is_none());
        // Otro hub no puede resolver esta key (BD compartida por org).
        assert!(verify_and_resolve(&db, &reg, "hub-2", &created.secret)
            .await
            .unwrap()
            .is_none());

        // last_used_at se rellena tras un uso correcto.
        let listed = list(&db, hub).await.unwrap();
        assert_eq!(listed.len(), 1);
        assert!(listed[0].last_used_at.is_some());

        // Rotar invalida el token anterior y emite uno nuevo válido.
        let rotated = rotate(&db, hub, &created.id).await.unwrap().unwrap();
        assert_ne!(rotated.secret, created.secret);
        assert!(verify_and_resolve(&db, &reg, hub, &created.secret)
            .await
            .unwrap()
            .is_none());
        assert!(verify_and_resolve(&db, &reg, hub, &rotated.secret)
            .await
            .unwrap()
            .is_some());

        // Revocar = kill-switch inmediato.
        assert!(revoke(&db, hub, &created.id).await.unwrap());
        assert!(verify_and_resolve(&db, &reg, hub, &rotated.secret)
            .await
            .unwrap()
            .is_none());
        // El listado conserva la fila marcada revoked.
        let listed = list(&db, hub).await.unwrap();
        assert_eq!(listed[0].status, "revoked");
    }

    // ── hub#504: the permission model of a key, and the key the hub issues to itself ─────────

    #[test]
    fn each_access_mode_answers_read_and_write_on_its_own() {
        // Four modes, four different answers. If two of them agreed, one could be deleted and
        // every test would still pass — which is how a "read-only" key ends up writing.
        assert!(ApiKeyScope::blanket(ApiKeyAccess::Full).can_read());
        assert!(ApiKeyScope::blanket(ApiKeyAccess::Full).can_write());
        assert!(ApiKeyScope::blanket(ApiKeyAccess::ReadOnly).can_read());
        assert!(!ApiKeyScope::blanket(ApiKeyAccess::ReadOnly).can_write());
        assert!(!ApiKeyScope::blanket(ApiKeyAccess::WriteOnly).can_read());
        assert!(ApiKeyScope::blanket(ApiKeyAccess::WriteOnly).can_write());

        // Custom answers from the checkboxes, and an EMPTY matrix grants nothing: a key that says
        // nothing must not become a key that may do anything.
        let read_box = ApiKeyScope::custom(vec![ScopeEntry {
            module: "inventory".into(),
            read: true,
            write: false,
        }]);
        assert!(read_box.can_read());
        assert!(!read_box.can_write());
        assert!(!ApiKeyScope::default().can_read());
        assert!(!ApiKeyScope::default().can_write());
    }

    #[test]
    fn a_scope_written_before_hub504_keeps_exactly_the_permissions_it_had() {
        // The rows already in `hub_api_key` hold ADR-0057's bare array. Reading one back as
        // anything other than the same checkboxes would either break a live integration or, worse,
        // widen it.
        let legacy = r#"[{"module":"inventory","read":true,"write":false}]"#;
        let scope: ApiKeyScope = serde_json::from_str(legacy).unwrap();
        assert_eq!(scope.access, ApiKeyAccess::Custom);
        assert_eq!(scope.modules.len(), 1);
        assert!(scope.can_read());
        assert!(!scope.can_write());

        // And the shape written since hub#504 round-trips.
        let modern = serde_json::to_string(&ApiKeyScope::blanket(ApiKeyAccess::ReadOnly)).unwrap();
        let back: ApiKeyScope = serde_json::from_str(&modern).unwrap();
        assert_eq!(back.access, ApiKeyAccess::ReadOnly);

        // Junk is not "everything": an unreadable scope falls back to granting nothing.
        let broken: ApiKeyScope = serde_json::from_str("[]").unwrap();
        assert!(!broken.can_read() && !broken.can_write());
    }

    #[test]
    fn a_blanket_mode_covers_a_module_the_key_never_named() {
        // The reason the mode exists at all: `inventory` is not in the matrix of a read-only key,
        // and it still has to be readable — otherwise every install would silently narrow the key.
        let reg = registry_with_inventory();
        let perms = expand(&reg, &ApiKeyScope::blanket(ApiKeyAccess::ReadOnly));
        assert!(perms.contains("inventory.read"));
        assert!(
            !perms.contains("inventory.write"),
            "read-only must not pick up the command permissions"
        );
        assert!(
            !perms.contains("inventory.read_secret"),
            "a private query is not public API, whatever the mode says"
        );

        let write_only = expand(&reg, &ApiKeyScope::blanket(ApiKeyAccess::WriteOnly));
        assert!(write_only.contains("inventory.write"));
        assert!(!write_only.contains("inventory.read"));

        let full = expand(&reg, &ApiKeyScope::blanket(ApiKeyAccess::Full));
        assert!(full.contains("inventory.read") && full.contains("inventory.write"));
    }

    #[tokio::test]
    async fn the_hub_issues_the_app_key_once_and_re_issues_it_after_a_restore() {
        let db = fresh_db().await;
        ensure_table(&db).await;
        let hub = "hub-app";

        let first = ensure_app_key(&db, hub).await.unwrap();
        let again = ensure_app_key(&db, hub).await.unwrap();
        assert_eq!(first, again, "asking twice must not mint a second key");
        assert_eq!(list(&db, hub).await.unwrap().len(), 1);

        let info = &list(&db, hub).await.unwrap()[0];
        assert_eq!(info.access, ApiKeyAccess::ReadOnly, "the app only listens");
        assert!(info.system, "the app key is marked as the hub's own");

        // A hub restored from a backup, or poured from a blueprint, does not carry this row —
        // credentials must not travel in an export. Connecting again re-issues it.
        db.execute("DELETE FROM hub_api_key", &Params::new())
            .await
            .unwrap();
        let after_restore = ensure_app_key(&db, hub).await.unwrap();
        assert_ne!(
            after_restore, first,
            "a re-issued key is a NEW credential, not the old one resurrected"
        );
        assert!(
            resolve_key_id(&db, &registry_with_inventory(), hub, &after_restore)
                .await
                .unwrap()
                .is_some()
        );
    }

    #[tokio::test]
    async fn the_app_key_of_one_hub_is_neither_reused_nor_broken_by_its_neighbour() {
        // Both hubs live in the SAME database and BOTH stay populated for the whole test: with the
        // neighbour's row deleted first, a query missing its `hub_id` would pass this just as well.
        let db = fresh_db().await;
        ensure_table(&db).await;
        let reg = registry_with_inventory();

        let mine = ensure_app_key(&db, "hub-a").await.unwrap();
        let neighbour = ensure_app_key(&db, "hub-b").await.unwrap();
        assert_ne!(mine, neighbour, "each hub issues its own");

        // My hub cannot resolve the neighbour's key…
        assert!(resolve_key_id(&db, &reg, "hub-a", &neighbour)
            .await
            .unwrap()
            .is_none());
        // …and the reason is not that it stopped working: it still resolves in ITS hub.
        assert!(resolve_key_id(&db, &reg, "hub-b", &neighbour)
            .await
            .unwrap()
            .is_some());
        assert_eq!(list(&db, "hub-b").await.unwrap().len(), 1);
    }

    #[tokio::test]
    async fn nobody_can_revoke_or_rotate_the_key_the_hub_issued_to_itself() {
        // "Not deletable" is the whole reason the app keeps working: if an admin could revoke it
        // from the keys screen, the printer would stop hearing about sales and nobody would know
        // why.
        let db = fresh_db().await;
        ensure_table(&db).await;
        let reg = registry_with_inventory();
        let hub = "hub-protected";
        let key_id = ensure_app_key(&db, hub).await.unwrap();

        let revoked = revoke(&db, hub, &key_id).await;
        assert!(
            matches!(&revoked, Err(crate::errors::RuntimeError::Domain { code, .. })
                if code == ERR_KEY_IS_SYSTEM),
            "revoking must be refused with its own code, got {revoked:?}"
        );
        let rotated = rotate(&db, hub, &key_id).await;
        assert!(
            matches!(&rotated, Err(crate::errors::RuntimeError::Domain { code, .. })
                if code == ERR_KEY_IS_SYSTEM),
            "rotating must be refused too, got {rotated:?}"
        );

        // Refused means refused: the key still works afterwards.
        assert!(resolve_key_id(&db, &reg, hub, &key_id)
            .await
            .unwrap()
            .is_some());

        // A human's key is untouched by the guard — it stays revocable.
        let human = create(
            &db,
            hub,
            "Gestoría",
            &ApiKeyScope::blanket(ApiKeyAccess::ReadOnly),
            60,
            "hub_user:7",
        )
        .await
        .unwrap();
        assert!(revoke(&db, hub, &human.id).await.unwrap());
    }

    #[tokio::test]
    async fn resolving_by_id_refuses_a_revoked_key() {
        // The ticket path resolves a key by id, without its secret. That must not become a way
        // around the kill-switch.
        let db = fresh_db().await;
        ensure_table(&db).await;
        let reg = registry_with_inventory();
        let hub = "hub-killswitch";
        let key = create(
            &db,
            hub,
            "Integration",
            &ApiKeyScope::blanket(ApiKeyAccess::ReadOnly),
            60,
            "hub_user:1",
        )
        .await
        .unwrap();

        assert!(resolve_key_id(&db, &reg, hub, &key.id)
            .await
            .unwrap()
            .is_some());
        revoke(&db, hub, &key.id).await.unwrap();
        assert!(resolve_key_id(&db, &reg, hub, &key.id)
            .await
            .unwrap()
            .is_none());
        assert!(resolve_key_id(&db, &reg, hub, "does-not-exist")
            .await
            .unwrap()
            .is_none());
    }

    #[tokio::test]
    async fn a_resolved_key_carries_its_scope_so_the_stream_can_ask_what_it_may_do() {
        let db = fresh_db().await;
        ensure_table(&db).await;
        let reg = registry_with_inventory();
        let hub = "hub-scope";
        let key = create(
            &db,
            hub,
            "Feed",
            &ApiKeyScope::blanket(ApiKeyAccess::WriteOnly),
            60,
            "hub_user:1",
        )
        .await
        .unwrap();
        let principal = verify_and_resolve(&db, &reg, hub, &key.secret)
            .await
            .unwrap()
            .unwrap();
        assert!(!principal.scope.can_read());
        assert!(principal.scope.can_write());
        assert_eq!(
            principal.context.principal,
            crate::registry::Principal::Machine
        );
    }

    #[tokio::test]
    async fn rate_limit_is_atomic_and_resets_on_the_next_minute() {
        let db = fresh_db().await;
        ensure_table(&db).await;
        let first = consume_rate_limit_at(&db, "key-1", 2, 120).await.unwrap();
        let second = consume_rate_limit_at(&db, "key-1", 2, 121).await.unwrap();
        let blocked = consume_rate_limit_at(&db, "key-1", 2, 122).await.unwrap();
        assert!(first.allowed);
        assert_eq!(second.remaining, 0);
        assert!(!blocked.allowed);
        let reset = consume_rate_limit_at(&db, "key-1", 2, 180).await.unwrap();
        assert!(reset.allowed);
        assert_eq!(reset.remaining, 1);
    }

    #[tokio::test]
    async fn concurrent_workers_allow_exactly_the_configured_limit() {
        let db = Arc::new(fresh_db().await);
        ensure_table(db.as_ref()).await;
        let mut workers = tokio::task::JoinSet::new();
        for _ in 0..32 {
            let db = Arc::clone(&db);
            workers.spawn(async move {
                consume_rate_limit_at(db.as_ref(), "key-concurrent", 7, 240)
                    .await
                    .unwrap()
                    .allowed
            });
        }
        let mut allowed = 0;
        while let Some(result) = workers.join_next().await {
            allowed += usize::from(result.unwrap());
        }
        assert_eq!(allowed, 7);
    }
}
