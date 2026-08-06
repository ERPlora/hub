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
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct ScopeEntry {
    pub module: String,
    #[serde(default)]
    pub read: bool,
    #[serde(default)]
    pub write: bool,
}

/// Metadatos de una API key (lo que se devuelve en listados/altas — **sin** el secreto).
#[derive(Debug, Clone, serde::Serialize)]
pub struct ApiKeyInfo {
    pub id: String,
    pub name: String,
    pub prefix: String,
    pub scope: Vec<ScopeEntry>,
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
    pub rate_limit_per_minute: i64,
}

/// Principal autenticado antes de consumir su cuota. Mantiene el id separado del `user_id`
/// para que el rate limiter nunca tenga que volver a parsear una identidad textual.
#[derive(Debug, Clone)]
pub struct ApiKeyPrincipal {
    pub key_id: String,
    pub rate_limit_per_minute: i64,
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
fn random_secret() -> String {
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

fn row_to_info(row: &serde_json::Value) -> ApiKeyInfo {
    let scope: Vec<ScopeEntry> = row["scope_json"]
        .as_str()
        .and_then(|s| serde_json::from_str(s).ok())
        .unwrap_or_default();
    ApiKeyInfo {
        id: row["id"].as_str().unwrap_or_default().to_string(),
        name: row["name"].as_str().unwrap_or_default().to_string(),
        prefix: row["prefix"].as_str().unwrap_or_default().to_string(),
        scope,
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
    scope: &[ScopeEntry],
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
        scope: scope.to_vec(),
        rate_limit_per_minute,
    })
}

/// Lista las API keys de `hub_id` (sin el secreto), ordenadas por fecha de creación desc.
pub async fn list(db: &dyn DatabaseAdapter, hub_id: &str) -> Result<Vec<ApiKeyInfo>> {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    let res = db
        .query(
            "SELECT id, name, prefix, scope_json, status, created_at, last_used_at, rate_limit_per_minute \
              FROM hub_api_key WHERE hub_id = :hub_id ORDER BY created_at DESC",
            &p,
        )
        .await?;
    Ok(res.rows.iter().map(row_to_info).collect())
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
            "SELECT id, name, prefix, scope_json, status, created_at, last_used_at, rate_limit_per_minute \
              FROM hub_api_key WHERE id = :id AND hub_id = :hub_id",
            &p,
        )
        .await?;
    let Some(row) = res.rows.first() else {
        return Ok(None);
    };
    let info = row_to_info(row);

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
        rate_limit_per_minute: info.rate_limit_per_minute,
    }))
}

/// Revoca una key (kill-switch inmediato): `status='revoked'`. Idempotente. La fila se conserva
/// (auditoría/listado); [`verify_and_resolve`] rechaza al instante cualquier key no `active`.
/// Devuelve `false` si no existía en este hub.
pub async fn revoke(db: &dyn DatabaseAdapter, hub_id: &str, id: &str) -> Result<bool> {
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
    let stored = row["secret_hash"].as_str().unwrap_or_default();
    if !verify_secret_argon2(stored, &secret) {
        return Ok(None);
    }

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

    let scope: Vec<ScopeEntry> = row["scope_json"]
        .as_str()
        .and_then(|s| serde_json::from_str(s).ok())
        .unwrap_or_default();
    let permissions = expand_scope(registry, &scope);

    Ok(Some(ApiKeyPrincipal {
        key_id: id.clone(),
        rate_limit_per_minute: row["rate_limit_per_minute"]
            .as_i64()
            .unwrap_or(DEFAULT_RATE_LIMIT_PER_MINUTE),
        context: RequestContext::new(hub_id.to_string(), format!("apikey:{id}"), permissions),
    }))
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

        let scope = vec![ScopeEntry {
            module: "inventory".into(),
            read: true,
            write: false,
        }];
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
