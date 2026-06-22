//! Identidad local del hub: **usuarios/roles/PIN** + **sesiones server-side** (ARQUITECTURA.md §2.9
//! + decisión 2026-06-09). La **autoridad de identidad y permisos es local**: el `role` del
//! `hub_user` mapea a permisos agregando los `role_permissions` de los módulos activos. Los métodos
//! de login (PIN local, JWT de usuario cloud, credencial de dispositivo) son **adaptadores** que
//! resuelven a un `hub_user` y abren una **sesión** (fila en SQLite, token opaco). El runtime gatea
//! con los permisos del rol resuelto — nunca con el método de login.
//!
//! Dos tipos de usuario (§2.9): **cloud** (`cloud_user_id` no nulo, vinculado al portal) y
//! **solo-local** (`cloud_user_id` nulo, p. ej. personal de tienda sin cuenta cloud).
use std::collections::HashSet;

use argon2::password_hash::{PasswordHash, PasswordHasher, PasswordVerifier, SaltString};
use argon2::Argon2;
use erplora_db::{DatabaseAdapter, Params};
use serde_json::json;
use sha2::{Digest, Sha256};

use crate::errors::Result;
use crate::registry::{new_id, now_rfc3339, Registry};

/// Duración por defecto de una sesión (segundos). 30 días — el día a día es por PIN/sesión local.
pub const DEFAULT_SESSION_TTL_SECS: i64 = 60 * 60 * 24 * 30;

const ENSURE_TABLES: &str = "\
CREATE TABLE IF NOT EXISTS hub_user (\
  id TEXT PRIMARY KEY, name TEXT NOT NULL, pin_hash TEXT NOT NULL DEFAULT '', \
  role TEXT NOT NULL DEFAULT '', cloud_user_id TEXT, is_active INTEGER NOT NULL DEFAULT 1, \
  created_at TEXT NOT NULL);\
CREATE TABLE IF NOT EXISTS hub_session (\
  token TEXT PRIMARY KEY, user_id TEXT NOT NULL, created_at TEXT NOT NULL, expires_at TEXT NOT NULL);\
CREATE INDEX IF NOT EXISTS ix_hub_user_cloud ON hub_user (cloud_user_id);";

/// Crea las tablas de identidad (idempotente).
pub async fn ensure_tables(db: &dyn DatabaseAdapter) -> Result<()> {
    db.execute_batch(ENSURE_TABLES).await?;
    Ok(())
}

/// Un usuario local del hub.
#[derive(Debug, Clone, PartialEq, Eq, serde::Serialize)]
pub struct HubUser {
    pub id: String,
    pub name: String,
    pub role: String,
    pub cloud_user_id: Option<String>,
    pub is_active: bool,
}

// ── PIN ─────────────────────────────────────────────────────────────────────────────────────
// **argon2id** con string PHC estándar (`$argon2id$v=19$...`), decisión humano hub#15. NOTA: el PIN
// es corto (4 dígitos), así que la seguridad real depende de que el dispositivo sea de confianza
// (device-trust, ver más abajo) + rate-limiting en el login; argon2id solo encarece el ataque
// offline si se filtra la BD. Cadena vacía = sin PIN (no autenticable). `set_pin`/`create_user`
// son los únicos que escriben el hash (siempre argon2id); `verify_pin` solo lo verifica.

/// Hash argon2id (string PHC) de un PIN con sal aleatoria. Parámetros = `Argon2::default()`
/// (argon2id, v=19) — razonables; el PIN es corto, ver nota arriba.
fn hash_pin_argon2(pin: &str) -> Result<String> {
    let salt = SaltString::generate(&mut argon2::password_hash::rand_core::OsRng);
    let hash = Argon2::default()
        .hash_password(pin.as_bytes(), &salt)
        .map_err(|e| crate::errors::RuntimeError::Other(format!("argon2 hash: {e}")))?;
    Ok(hash.to_string())
}

/// Verifica `pin` contra el hash almacenado. `true` si coincide. Hash vacío o corrupto
/// ⇒ `false` (no autenticable).
///
/// Acepta dos formatos:
///  - **argon2id** (string PHC `$argon2id$...`): el formato canónico que escriben
///    `create_user`/`set_pin`.
///  - **legacy** `salt:sha256_hex("{salt}:{pin}")` (el que usa el seed del despliegue demo,
///    `crates/server/seeds/demo.sql`): un PHC no parsea, así que se intenta este formato como
///    fallback. Un hub sembrado por terraform (`HUB_SEED_SQL`) puede hacer login por PIN sin
///    re-sembrar a argon2id. El rehash perezoso a argon2id en el primer login es una optimización
///    futura (no afecta a la verificación).
fn check_pin(stored: &str, pin: &str) -> bool {
    if stored.is_empty() {
        return false;
    }
    // 1) Hash PHC argon2id (formato canónico).
    if let Ok(parsed) = PasswordHash::new(stored) {
        return Argon2::default().verify_password(pin.as_bytes(), &parsed).is_ok();
    }
    // 2) Fallback legacy `salt:sha256_hex("{salt}:{pin}")` (seed del demo). Solo si NO era un PHC.
    if let Some((salt, expected_hex)) = stored.split_once(':') {
        if !salt.is_empty() && !expected_hex.is_empty() {
            let digest = Sha256::digest(format!("{salt}:{pin}").as_bytes());
            let actual_hex = hex_lower(&digest);
            // Comparación tolerante a mayúsculas del hex almacenado.
            return actual_hex.eq_ignore_ascii_case(expected_hex);
        }
    }
    false
}

/// Hex en minúsculas de un buffer de bytes (sin dependencias extra).
fn hex_lower(bytes: &[u8]) -> String {
    let mut s = String::with_capacity(bytes.len() * 2);
    for b in bytes {
        s.push_str(&format!("{b:02x}"));
    }
    s
}

// ── Usuarios ────────────────────────────────────────────────────────────────────────────────

/// Crea un usuario local. `pin` vacío = usuario sin PIN (login por otro método). Devuelve su id.
pub async fn create_user(
    db: &dyn DatabaseAdapter,
    name: &str,
    pin: &str,
    role: &str,
    cloud_user_id: Option<&str>,
) -> Result<String> {
    let id = new_id();
    let pin_hash = if pin.is_empty() {
        String::new()
    } else {
        hash_pin_argon2(pin)?
    };
    let mut p = Params::new();
    p.insert("id".into(), json!(id));
    p.insert("name".into(), json!(name));
    p.insert("pin_hash".into(), json!(pin_hash));
    p.insert("role".into(), json!(role));
    p.insert("cloud_user_id".into(), json!(cloud_user_id));
    p.insert("now".into(), json!(now_rfc3339()));
    db.execute(
        "INSERT INTO hub_user (id, name, pin_hash, role, cloud_user_id, is_active, created_at) \
          VALUES (:id, :name, :pin_hash, :role, :cloud_user_id, 1, :now)",
        &p,
    )
    .await?;
    Ok(id)
}

/// Fija (o cambia) el PIN de un usuario **existente** por id. Lo usa el alta de PIN tras el primer
/// login cloud (§2.9): el usuario ya está provisionado (sin PIN) y elige su PIN en el dispositivo de
/// confianza. `pin` vacío borra el PIN (deja el usuario no autenticable por PIN). Idempotente.
pub async fn set_pin(db: &dyn DatabaseAdapter, user_id: &str, pin: &str) -> Result<()> {
    // Siempre escribe argon2id (string PHC); `pin` vacío deja el hash vacío (no autenticable).
    let pin_hash = if pin.is_empty() {
        String::new()
    } else {
        hash_pin_argon2(pin)?
    };
    let mut p = Params::new();
    p.insert("id".into(), json!(user_id));
    p.insert("pin_hash".into(), json!(pin_hash));
    db.execute(
        "UPDATE hub_user SET pin_hash = :pin_hash WHERE id = :id",
        &p,
    )
    .await?;
    Ok(())
}

fn row_to_user(row: &serde_json::Value) -> HubUser {
    HubUser {
        id: row["id"].as_str().unwrap_or_default().to_string(),
        name: row["name"].as_str().unwrap_or_default().to_string(),
        role: row["role"].as_str().unwrap_or_default().to_string(),
        cloud_user_id: row["cloud_user_id"].as_str().map(|s| s.to_string()),
        is_active: row["is_active"].as_i64().unwrap_or(0) != 0,
    }
}

/// Verifica el PIN de un usuario activo por **nombre**. `Some(user)` si el PIN encaja.
pub async fn verify_pin(
    db: &dyn DatabaseAdapter,
    name: &str,
    pin: &str,
) -> Result<Option<HubUser>> {
    let mut p = Params::new();
    p.insert("name".into(), json!(name));
    let res = db
        .query(
            "SELECT id, name, role, cloud_user_id, is_active, pin_hash FROM hub_user \
              WHERE name = :name AND is_active = 1",
            &p,
        )
        .await?;
    for row in &res.rows {
        if check_pin(row["pin_hash"].as_str().unwrap_or_default(), pin) {
            return Ok(Some(row_to_user(row)));
        }
    }
    Ok(None)
}

/// Lista los usuarios **activos con PIN** del hub `(id, name, role)`, ordenados por nombre. Lo usa
/// `GET /api/hub/context` para que el shell muestre el grid de PIN directamente (sin depender de un
/// flag en localStorage). Solo usuarios con `pin_hash` no vacío (los que pueden hacer login local).
pub async fn list_pin_users(db: &dyn DatabaseAdapter) -> Result<Vec<(String, String, String)>> {
    let res = db
        .query(
            "SELECT id, name, role FROM hub_user \
              WHERE is_active = 1 AND pin_hash IS NOT NULL AND pin_hash != '' \
              ORDER BY name",
            &Params::new(),
        )
        .await?;
    Ok(res
        .rows
        .iter()
        .map(|r| {
            (
                r["id"].as_str().unwrap_or_default().to_string(),
                r["name"].as_str().unwrap_or_default().to_string(),
                r["role"].as_str().unwrap_or_default().to_string(),
            )
        })
        .collect())
}

/// Resuelve (o crea) el `hub_user` vinculado a una identidad cloud. Es el adaptador del **JWT de
/// usuario**: tras verificar el token (server), se mapea su `user_id` a un usuario local. Si no
/// existe, se **provisiona** (primer login online, §2.9) con `default_role`.
pub async fn get_or_link_cloud_user(
    db: &dyn DatabaseAdapter,
    cloud_user_id: &str,
    default_name: &str,
    default_role: &str,
) -> Result<HubUser> {
    let mut p = Params::new();
    p.insert("cuid".into(), json!(cloud_user_id));
    let res = db
        .query(
            "SELECT id, name, role, cloud_user_id, is_active FROM hub_user \
              WHERE cloud_user_id = :cuid AND is_active = 1",
            &p,
        )
        .await?;
    if let Some(row) = res.rows.first() {
        return Ok(row_to_user(row));
    }
    let id = create_user(db, default_name, "", default_role, Some(cloud_user_id)).await?;
    Ok(HubUser {
        id,
        name: default_name.to_string(),
        role: default_role.to_string(),
        cloud_user_id: Some(cloud_user_id.to_string()),
        is_active: true,
    })
}

// ── Sesiones ────────────────────────────────────────────────────────────────────────────────

/// Abre una sesión para `user_id` y devuelve el token opaco (lo guarda el frontend y lo manda en
/// cada petición). TTL en segundos.
pub async fn create_session(
    db: &dyn DatabaseAdapter,
    user_id: &str,
    ttl_secs: i64,
) -> Result<String> {
    let token = format!("{}{}", new_id(), new_id()).replace('-', "");
    let expires = (chrono::Utc::now() + chrono::Duration::seconds(ttl_secs)).to_rfc3339();
    let mut p = Params::new();
    p.insert("token".into(), json!(token));
    p.insert("user_id".into(), json!(user_id));
    p.insert("now".into(), json!(now_rfc3339()));
    p.insert("expires".into(), json!(expires));
    db.execute(
        "INSERT INTO hub_session (token, user_id, created_at, expires_at) \
          VALUES (:token, :user_id, :now, :expires)",
        &p,
    )
    .await?;
    Ok(token)
}

/// Resuelve una sesión válida (no caducada) a su `hub_user` activo. `None` si no existe/caducó.
pub async fn resolve_session(db: &dyn DatabaseAdapter, token: &str) -> Result<Option<HubUser>> {
    let mut p = Params::new();
    p.insert("token".into(), json!(token));
    p.insert("now".into(), json!(now_rfc3339()));
    let res = db
        .query(
            "SELECT u.id, u.name, u.role, u.cloud_user_id, u.is_active \
              FROM hub_session s JOIN hub_user u ON u.id = s.user_id \
              WHERE s.token = :token AND s.expires_at > :now AND u.is_active = 1",
            &p,
        )
        .await?;
    Ok(res.rows.first().map(row_to_user))
}

/// Cierra una sesión (logout).
pub async fn delete_session(db: &dyn DatabaseAdapter, token: &str) -> Result<()> {
    let mut p = Params::new();
    p.insert("token".into(), json!(token));
    db.execute("DELETE FROM hub_session WHERE token = :token", &p)
        .await?;
    Ok(())
}

// ── Device-trust (§2.9) ───────────────────────────────────────────────────────────────────────
// Modelo MÍNIMO (hub#15): un dispositivo se marca **de confianza** tras el **primer login online**
// (login cloud OK). Mientras NO sea de confianza, el login local por PIN se rechaza — así un PIN de
// 4 dígitos solo es utilizable en un dispositivo que ya probó identidad contra el Cloud al menos una
// vez. La tabla `hub_trusted_device` la crea la migración de sistema v2 (no `CREATE IF NOT EXISTS`).
//
// El `device_id` lo aporta el host (Tauri = id estable de máquina; web-PWA = id persistido en el
// cliente). En el server cloud-only el gate puede deshabilitarse vía config (ver server). Esto NO
// es la credencial de máquina del hub (`cloud_api_token`/`X-Hub-Token`, enroll del dispositivo en el
// Cloud, `cloud-client`): aquel autentica el HUB ante el Cloud; este autoriza el LOGIN LOCAL por PIN.
//
// TODO(humano): §2.9/architecture no cierran el esquema exacto del device-trust local (¿expiración
// del trust?, ¿revocación por admin desde el dashboard?, ¿binding del device_id a un hub_user?).
// Esto implementa lo mínimo coherente con el flujo actual; cerrar el diseño antes de endurecerlo.

/// Marca un dispositivo como **de confianza** (idempotente). Lo llama el server tras un login online
/// (cloud) correcto. `label` es un nombre legible opcional (p. ej. "Caja 1").
pub async fn trust_device(db: &dyn DatabaseAdapter, device_id: &str, label: &str) -> Result<()> {
    // INSERT … ON CONFLICT: re-marcar un dispositivo ya de confianza no falla ni duplica.
    let mut p = Params::new();
    p.insert("device_id".into(), json!(device_id));
    p.insert("label".into(), json!(label));
    p.insert("now".into(), json!(now_rfc3339()));
    db.execute(
        "INSERT INTO hub_trusted_device (device_id, label, trusted_at) \
          VALUES (:device_id, :label, :now) \
          ON CONFLICT (device_id) DO UPDATE SET label = excluded.label",
        &p,
    )
    .await?;
    Ok(())
}

/// `true` si `device_id` está marcado como de confianza (gate del login por PIN, §2.9).
pub async fn is_device_trusted(db: &dyn DatabaseAdapter, device_id: &str) -> Result<bool> {
    let mut p = Params::new();
    p.insert("device_id".into(), json!(device_id));
    let res = db
        .query(
            "SELECT 1 AS ok FROM hub_trusted_device WHERE device_id = :device_id",
            &p,
        )
        .await?;
    Ok(!res.rows.is_empty())
}

/// Revoca la confianza de un dispositivo (dispositivo perdido/robado). Idempotente.
pub async fn untrust_device(db: &dyn DatabaseAdapter, device_id: &str) -> Result<()> {
    let mut p = Params::new();
    p.insert("device_id".into(), json!(device_id));
    db.execute(
        "DELETE FROM hub_trusted_device WHERE device_id = :device_id",
        &p,
    )
    .await?;
    Ok(())
}

// ── Permisos ────────────────────────────────────────────────────────────────────────────────

/// Permisos efectivos de un `role`: unión de `role_permissions[role]` de **todos los módulos
/// activos** (ARQUITECTURA.md §2.5/§9.2). Si algún módulo concede `*` al rol, el usuario tiene `*`.
pub fn permissions_for_role(registry: &Registry, role: &str) -> HashSet<String> {
    let mut perms = HashSet::new();
    for m in &registry.installed {
        if !registry.is_active(&m.id) {
            continue;
        }
        if let Some(list) = m.role_permissions.get(role) {
            for perm in list {
                perms.insert(perm.clone());
            }
        }
    }
    perms
}

#[cfg(test)]
mod tests {
    use super::*;
    use erplora_db::SqliteAdapter;

    #[tokio::test]
    async fn pin_login_and_session_roundtrip() {
        let db = SqliteAdapter::open_in_memory().await.unwrap();
        ensure_tables(&db).await.unwrap();

        let uid = create_user(&db, "María", "1234", "manager", None)
            .await
            .unwrap();

        // PIN correcto resuelve al usuario; PIN incorrecto no.
        let ok = verify_pin(&db, "María", "1234").await.unwrap();
        assert_eq!(ok.as_ref().map(|u| u.id.clone()), Some(uid.clone()));
        assert_eq!(ok.unwrap().role, "manager");
        assert!(verify_pin(&db, "María", "0000").await.unwrap().is_none());

        // Sesión: crear → resolver → logout.
        let token = create_session(&db, &uid, 3600).await.unwrap();
        assert_eq!(resolve_session(&db, &token).await.unwrap().unwrap().id, uid);
        delete_session(&db, &token).await.unwrap();
        assert!(resolve_session(&db, &token).await.unwrap().is_none());

        // Sesión caducada no resuelve.
        let expired = create_session(&db, &uid, -10).await.unwrap();
        assert!(resolve_session(&db, &expired).await.unwrap().is_none());
    }

    #[tokio::test]
    async fn set_pin_enables_pin_login_for_existing_user() {
        let db = SqliteAdapter::open_in_memory().await.unwrap();
        ensure_tables(&db).await.unwrap();
        // Cloud-linked user provisioned without a PIN (first online login).
        let user = get_or_link_cloud_user(&db, "7", "Ada", "admin")
            .await
            .unwrap();
        assert!(
            verify_pin(&db, "Ada", "4242").await.unwrap().is_none(),
            "no PIN yet"
        );

        set_pin(&db, &user.id, "4242").await.unwrap();
        let ok = verify_pin(&db, "Ada", "4242").await.unwrap();
        assert_eq!(ok.map(|u| u.id), Some(user.id.clone()));
        assert!(
            verify_pin(&db, "Ada", "0000").await.unwrap().is_none(),
            "wrong PIN rejected"
        );

        // Empty PIN clears it again.
        set_pin(&db, &user.id, "").await.unwrap();
        assert!(
            verify_pin(&db, "Ada", "4242").await.unwrap().is_none(),
            "PIN cleared"
        );
    }

    #[tokio::test]
    async fn cloud_user_link_is_idempotent() {
        let db = SqliteAdapter::open_in_memory().await.unwrap();
        ensure_tables(&db).await.unwrap();
        let a = get_or_link_cloud_user(&db, "42", "Demo", "cashier")
            .await
            .unwrap();
        let b = get_or_link_cloud_user(&db, "42", "OtroNombre", "admin")
            .await
            .unwrap();
        assert_eq!(a.id, b.id, "el mismo cloud_user_id reusa el hub_user");
        assert_eq!(
            b.role, "cashier",
            "no re-provisiona ni cambia el rol existente"
        );
    }

    #[tokio::test]
    async fn new_pins_are_argon2id() {
        // create_user/set_pin escriben siempre argon2id (string PHC `$argon2id$...`).
        let db = SqliteAdapter::open_in_memory().await.unwrap();
        ensure_tables(&db).await.unwrap();
        create_user(&db, "Eva", "1111", "cashier", None)
            .await
            .unwrap();
        let mut p = Params::new();
        p.insert("name".into(), json!("Eva"));
        let res = db
            .query("SELECT pin_hash FROM hub_user WHERE name = :name", &p)
            .await
            .unwrap();
        let stored = res.rows[0]["pin_hash"].as_str().unwrap();
        assert!(
            stored.starts_with("$argon2id$"),
            "hash debe ser argon2id PHC, fue: {stored}"
        );
        // Verifica argon2id directamente.
        let ok = verify_pin(&db, "Eva", "1111").await.unwrap();
        assert!(ok.is_some());
        assert!(verify_pin(&db, "Eva", "2222").await.unwrap().is_none());
    }

    #[tokio::test]
    async fn device_trust_gate() {
        let db = SqliteAdapter::open_in_memory().await.unwrap();
        ensure_tables(&db).await.unwrap();
        // La tabla la crea la migración de sistema v2; en el test la creamos a mano (sin hub_id).
        db.execute_batch(
            "CREATE TABLE hub_trusted_device (device_id TEXT PRIMARY KEY, \
              label TEXT NOT NULL DEFAULT '', trusted_at TEXT NOT NULL);",
        )
        .await
        .unwrap();

        assert!(
            !is_device_trusted(&db, "dev-1").await.unwrap(),
            "desconocido = no confianza"
        );
        trust_device(&db, "dev-1", "Caja 1").await.unwrap();
        assert!(
            is_device_trusted(&db, "dev-1").await.unwrap(),
            "marcado = de confianza"
        );
        // Idempotente (re-marcar no falla).
        trust_device(&db, "dev-1", "Caja 1 (renombrada)")
            .await
            .unwrap();
        assert!(is_device_trusted(&db, "dev-1").await.unwrap());
        // Revocar lo quita.
        untrust_device(&db, "dev-1").await.unwrap();
        assert!(!is_device_trusted(&db, "dev-1").await.unwrap());
    }
}
