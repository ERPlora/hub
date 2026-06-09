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
// Hash salteado SHA-256, formato `"{salt_hex}:{hash_hex}"`. NOTA: el PIN es corto; la seguridad
// real depende de que el dispositivo sea de confianza + rate-limiting en el login. **Pendiente**:
// migrar a argon2id (decisión de dependencia del humano). Cadena vacía = sin PIN (no autenticable).
fn hash_pin(pin: &str, salt: &str) -> String {
    let mut h = Sha256::new();
    h.update(salt.as_bytes());
    h.update(b":");
    h.update(pin.as_bytes());
    format!("{salt}:{:x}", h.finalize())
}

fn pin_matches(stored: &str, pin: &str) -> bool {
    match stored.split_once(':') {
        Some((salt, _)) if !stored.is_empty() => hash_pin(pin, salt) == stored,
        _ => false,
    }
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
    let pin_hash = if pin.is_empty() { String::new() } else { hash_pin(pin, &new_id()) };
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
pub async fn verify_pin(db: &dyn DatabaseAdapter, name: &str, pin: &str) -> Result<Option<HubUser>> {
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
        if pin_matches(row["pin_hash"].as_str().unwrap_or_default(), pin) {
            return Ok(Some(row_to_user(row)));
        }
    }
    Ok(None)
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
pub async fn create_session(db: &dyn DatabaseAdapter, user_id: &str, ttl_secs: i64) -> Result<String> {
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
    db.execute("DELETE FROM hub_session WHERE token = :token", &p).await?;
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

        let uid = create_user(&db, "María", "1234", "manager", None).await.unwrap();

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
    async fn cloud_user_link_is_idempotent() {
        let db = SqliteAdapter::open_in_memory().await.unwrap();
        ensure_tables(&db).await.unwrap();
        let a = get_or_link_cloud_user(&db, "42", "Demo", "cashier").await.unwrap();
        let b = get_or_link_cloud_user(&db, "42", "OtroNombre", "admin").await.unwrap();
        assert_eq!(a.id, b.id, "el mismo cloud_user_id reusa el hub_user");
        assert_eq!(b.role, "cashier", "no re-provisiona ni cambia el rol existente");
    }
}
