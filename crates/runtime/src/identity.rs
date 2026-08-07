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

/// Fila del panel admin de **usuarios-login** del hub (ADR-0157 §7): los `hub_user` con una cuenta
/// cloud (email no vacío), que el owner/admin da de alta/baja. A diferencia de [`HubUser`] lleva el
/// `email` (la clave por la que el admin los administra y por la que el login los enlaza).
#[derive(Debug, Clone, PartialEq, Eq, serde::Serialize)]
pub struct LoginUser {
    pub id: String,
    pub email: String,
    pub name: String,
    pub role: String,
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
    hash_secret_argon2(pin)
}

/// Hash argon2id (string PHC `$argon2id$v=19$...`) de un secreto arbitrario con sal aleatoria.
/// **El mismo helper que usa el PIN** (decisión humano hub#15); lo reusan otras credenciales
/// locales hasheadas, p. ej. el `secret_hash` de las API keys (`api_keys.rs`, ADR-0057). A
/// diferencia del PIN, el secreto de una API key es largo/aleatorio (alta entropía), así que el
/// coste de argon2 cubre de sobra el ataque offline si se filtra la BD.
pub(crate) fn hash_secret_argon2(secret: &str) -> Result<String> {
    let salt = SaltString::generate(&mut argon2::password_hash::rand_core::OsRng);
    let hash = Argon2::default()
        .hash_password(secret.as_bytes(), &salt)
        .map_err(|e| crate::errors::RuntimeError::Other(format!("argon2 hash: {e}")))?;
    Ok(hash.to_string())
}

/// Verifica un secreto contra su hash argon2id PHC (`$argon2id$...`). `false` si el hash está
/// vacío/corrupto o no encaja. Espejo de `check_pin` pero **solo** para hashes PHC argon2id (sin
/// el fallback legacy `salt:sha256` del seed demo, que solo aplica al PIN). Lo usa `api_keys.rs`.
pub(crate) fn verify_secret_argon2(stored: &str, secret: &str) -> bool {
    if stored.is_empty() {
        return false;
    }
    match PasswordHash::new(stored) {
        Ok(parsed) => Argon2::default()
            .verify_password(secret.as_bytes(), &parsed)
            .is_ok(),
        Err(_) => false,
    }
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
        return Argon2::default()
            .verify_password(pin.as_bytes(), &parsed)
            .is_ok();
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

/// Asegura una identidad fija para `AuthMode::Dev`, donde el frontend es la autoridad de las
/// cabeceras y puede traer un id demo ya persistido. No cambia una identidad existente.
pub async fn ensure_dev_user(
    db: &dyn DatabaseAdapter,
    id: &str,
    name: &str,
    role: &str,
) -> Result<()> {
    let mut p = Params::new();
    p.insert("id".into(), json!(id));
    p.insert("name".into(), json!(name));
    p.insert("role".into(), json!(role));
    p.insert("now".into(), json!(now_rfc3339()));
    db.execute(
        "INSERT INTO hub_user (id, name, pin_hash, role, cloud_user_id, is_active, created_at) \
         VALUES (:id, :name, '', :role, NULL, 1, :now) \
         ON CONFLICT (id) DO NOTHING",
        &p,
    )
    .await?;
    Ok(())
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

/// Nombre legible por defecto derivado de un email (la parte local antes de `@`). Para dar un
/// `name` mostrable al `hub_user` sembrado/invitado por email antes de su primer login (el usuario
/// puede editarlo luego en su Perfil). `""` → `"owner"`/lo que pase el llamador.
fn name_from_email(email: &str) -> String {
    email
        .split('@')
        .next()
        .map(str::trim)
        .filter(|s| !s.is_empty())
        .unwrap_or(email)
        .to_string()
}

/// **Siembra el owner del hub** desde el env del provisioning del SaaS (ADR-0157, corrección de
/// Ioan 2026-07-26): el owner es el **CREADOR** del hub y el despliegue lo trae ya inyectado como
/// `HUB_OWNER_EMAIL`. Crea un `hub_user` con rol `owner`, ese `email` y `cloud_user_id = NULL`
/// (aún no ha hecho login: al primer login `get_or_link_cloud_user` lo enlaza por email). Sin PIN.
///
/// **Idempotente**: si ya existe un `hub_user` con ese email, **no hace nada** (no duplica ni pisa
/// un rol/estado existente). Devuelve `true` si sembró una fila nueva, `false` si ya existía.
/// Sustituye al bootstrap «primer login = owner» (retirado): el owner ya no depende de quién entre
/// primero, sino de quién creó el hub.
pub async fn seed_owner(db: &dyn DatabaseAdapter, email: &str) -> Result<bool> {
    let email = email.trim();
    if email.is_empty() {
        return Ok(false);
    }
    let mut p = Params::new();
    p.insert("email".into(), json!(email));
    let existing = db
        .query("SELECT id FROM hub_user WHERE email = :email", &p)
        .await?;
    if !existing.rows.is_empty() {
        return Ok(false); // ya sembrado: idempotente, no cambia nada.
    }
    let id = new_id();
    let mut ins = Params::new();
    ins.insert("id".into(), json!(id));
    ins.insert("name".into(), json!(name_from_email(email)));
    ins.insert("email".into(), json!(email));
    ins.insert("now".into(), json!(now_rfc3339()));
    db.execute(
        "INSERT INTO hub_user (id, name, pin_hash, role, cloud_user_id, is_active, created_at, email) \
          VALUES (:id, :name, '', 'owner', NULL, 1, :now, :email)",
        &ins,
    )
    .await?;
    Ok(true)
}

/// Sube el rol de un `hub_user` **al suelo** que impone el rol de su cuenta en el Cloud, si aún no
/// llega (paso 2b regla C, hub#347). Devuelve el usuario tal y como queda.
///
/// Es un **suelo**, no una sincronización, y por eso solo sube:
///  - Si el rol local ya **administra el hub** (`owner` o `admin`, [`hub_users::is_admin_role`]) no
///    toca nada. Ese es el caso que impide que reevaluar el suelo **degrade al owner** a `admin`.
///  - Cualquier otro rol —`manager`, `employee` o uno **custom** de un módulo— no acredita
///    administrar el hub, así que se sube a [`hub_users::CLOUD_ROLE_FLOOR`]. Es deliberado: los
///    permisos que declara el manifest de un módulo no son la propiedad "administra el hub", y sin
///    subirlo un owner de la cuenta puede quedarse fuera de su propio hub, que es justo lo que la
///    regla C existe para evitar.
///  - `floor` es siempre `admin` en el llamador real (`server::auth::role_floor_for_cloud_login`);
///    aquí se **acota igualmente** a `CLOUD_ROLE_FLOOR` como defensa en profundidad: un login
///    NUNCA puede escribir `owner`, venga como venga el parámetro (ADR-0157: la propiedad del hub
///    sale de `HUB_OWNER_EMAIL`, no de un token).
async fn raise_role_to_floor(
    db: &dyn DatabaseAdapter,
    user: HubUser,
    floor: Option<&str>,
) -> Result<HubUser> {
    let Some(floor) = floor.map(str::trim).filter(|s| !s.is_empty()) else {
        return Ok(user); // sin suelo: el rol local queda EXACTAMENTE como lo dejó el hub.
    };
    if crate::hub_users::is_admin_role(&user.role) {
        return Ok(user); // ya está en el suelo o por encima.
    }
    // Acota el suelo: `admin` y nada más, aunque el llamador pida otra cosa.
    let floor = if crate::hub_users::is_admin_role(floor) {
        crate::hub_users::CLOUD_ROLE_FLOOR
    } else {
        return Ok(user); // un "suelo" que no administra el hub no es un suelo: no asciende nada.
    };
    let mut p = Params::new();
    p.insert("id".into(), json!(user.id));
    p.insert("role".into(), json!(floor));
    db.execute("UPDATE hub_user SET role = :role WHERE id = :id", &p)
        .await?;
    Ok(HubUser {
        role: floor.to_string(),
        ..user
    })
}

/// Resuelve (o crea/enlaza) el `hub_user` vinculado a una identidad cloud. Adaptador del **JWT de
/// usuario**: tras verificar el token (server), se mapea a un usuario local. La resolución es en
/// dos pasos (ADR-0157):
///  1. Por **`cloud_user_id`** (usuario ya enlazado en un login previo).
///  2. Por **`email`** (si viene y no está vacío): una fila **pre-provisionada sin `cloud_user_id`**
///     — el **owner sembrado** (`seed_owner`) o un usuario **invitado** por el admin (`create_login_user`).
///     Se **enlaza** (fija `cloud_user_id`) conservando su rol (owner / rol de la invitación) y su
///     email. Así el owner mantiene `owner` (no cae a `employee`) en su primer login.
///  3. Si no hay coincidencia → se **provisiona** con `default_role` (red de seguridad para un
///     miembro que pasa el gate de presencia sin fila local; rol de mínimo privilegio).
///
/// En los dos primeros casos —fila que YA existe— se aplica además el **suelo de rol**
/// (`role_floor`, paso 2b regla C, hub#347): el rol de la cuenta en el Cloud se reevalúa en **cada**
/// login y sube el rol local si se ha quedado corto, sin bajarlo nunca. Antes el rol era una foto
/// del primer login y ascender a alguien en el SaaS no llegaba jamás al hub. Ver
/// [`raise_role_to_floor`]. `role_floor = None` → la fila se devuelve intacta.
pub async fn get_or_link_cloud_user(
    db: &dyn DatabaseAdapter,
    cloud_user_id: &str,
    default_name: &str,
    default_role: &str,
    email: Option<&str>,
    role_floor: Option<&str>,
) -> Result<HubUser> {
    // 1) Por cloud_user_id (ya enlazado).
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
        return raise_role_to_floor(db, row_to_user(row), role_floor).await;
    }
    // 2) Por email: fila pre-provisionada (owner sembrado / invitado) sin cloud_user_id → enlazar.
    if let Some(email) = email.map(str::trim).filter(|s| !s.is_empty()) {
        let mut pe = Params::new();
        pe.insert("email".into(), json!(email));
        let by_email = db
            .query(
                "SELECT id, name, role, cloud_user_id, is_active FROM hub_user \
                  WHERE email = :email AND cloud_user_id IS NULL AND is_active = 1",
                &pe,
            )
            .await?;
        if let Some(row) = by_email.rows.first() {
            let user = row_to_user(row);
            let mut up = Params::new();
            up.insert("id".into(), json!(user.id));
            up.insert("cuid".into(), json!(cloud_user_id));
            db.execute(
                "UPDATE hub_user SET cloud_user_id = :cuid WHERE id = :id",
                &up,
            )
            .await?;
            let linked = HubUser {
                cloud_user_id: Some(cloud_user_id.to_string()),
                ..user
            };
            return raise_role_to_floor(db, linked, role_floor).await;
        }
    }
    // 3) Provisiona una fila nueva (rol de mínimo privilegio) con su email si vino. El suelo se
    //    aplica también aquí para que la invariante sea la MISMA en los tres caminos: al salir, el
    //    rol nunca está por debajo del suelo. El llamador real ya calcula `default_role` con el
    //    mismo rol de cuenta, así que en la práctica es un no-op; lo que evita es que un llamador
    //    futuro pase un suelo y se olvide del rol por defecto y la fila nueva nazca por debajo.
    let email = email.map(str::trim).unwrap_or("");
    let id = create_login_user_row(db, &new_id(), default_name, "", default_role, Some(cloud_user_id), email).await?;
    let created = HubUser {
        id,
        name: default_name.to_string(),
        role: default_role.to_string(),
        cloud_user_id: Some(cloud_user_id.to_string()),
        is_active: true,
    };
    raise_role_to_floor(db, created, role_floor).await
}

/// INSERT de bajo nivel de un `hub_user` con `email` explícito (lo comparten el provisioning por
/// email y el enlace-o-crea del login). No comprueba duplicados (los llamadores lo hacen).
async fn create_login_user_row(
    db: &dyn DatabaseAdapter,
    id: &str,
    name: &str,
    pin: &str,
    role: &str,
    cloud_user_id: Option<&str>,
    email: &str,
) -> Result<String> {
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
    p.insert("email".into(), json!(email));
    p.insert("now".into(), json!(now_rfc3339()));
    db.execute(
        "INSERT INTO hub_user (id, name, pin_hash, role, cloud_user_id, is_active, created_at, email) \
          VALUES (:id, :name, :pin_hash, :role, :cloud_user_id, 1, :now, :email)",
        &p,
    )
    .await?;
    Ok(id.to_string())
}

/// **Alta de un usuario-login** por email + rol (flujo admin del Hub, ADR-0157 §7). Es identidad
/// (quién puede ENTRAR), **no** el módulo `staff.*` (negocio). **Upsert por email**: si ya existe
/// una fila con ese email la **reactiva** y le fija el rol nuevo (re-invitación); si no, crea una
/// fila nueva sin PIN y sin `cloud_user_id` (se enlaza en su primer login, `get_or_link_cloud_user`).
/// Devuelve el `hub_user` resultante. La notificación al SaaS (`members_add`) la hace el server.
pub async fn create_login_user(
    db: &dyn DatabaseAdapter,
    email: &str,
    role: &str,
) -> Result<HubUser> {
    let email = email.trim();
    let mut p = Params::new();
    p.insert("email".into(), json!(email));
    let existing = db
        .query(
            "SELECT id, name, role, cloud_user_id, is_active FROM hub_user WHERE email = :email",
            &p,
        )
        .await?;
    if let Some(row) = existing.rows.first() {
        let user = row_to_user(row);
        let mut up = Params::new();
        up.insert("id".into(), json!(user.id));
        up.insert("role".into(), json!(role));
        db.execute(
            "UPDATE hub_user SET role = :role, is_active = 1 WHERE id = :id",
            &up,
        )
        .await?;
        return Ok(HubUser {
            role: role.to_string(),
            is_active: true,
            ..user
        });
    }
    let id = new_id();
    create_login_user_row(db, &id, &name_from_email(email), "", role, None, email).await?;
    Ok(HubUser {
        id,
        name: name_from_email(email),
        role: role.to_string(),
        cloud_user_id: None,
        is_active: true,
    })
}

/// **Baja de un usuario-login** por email (flujo admin, ADR-0157 §7 — la simetría del alta). Marca
/// `is_active = 0` (no borra: audit + posible re-alta); una sesión abierta deja de resolver
/// (`resolve_session` filtra `is_active = 1`). Idempotente. Devuelve `true` si afectó a alguna fila
/// activa. La revocación de la membresía en el SaaS (`members_remove`) la hace el server.
pub async fn deactivate_login_user(db: &dyn DatabaseAdapter, email: &str) -> Result<bool> {
    let email = email.trim();
    let mut p = Params::new();
    p.insert("email".into(), json!(email));
    let res = db
        .execute(
            "UPDATE hub_user SET is_active = 0 WHERE email = :email AND is_active = 1",
            &p,
        )
        .await?;
    Ok(res.affected > 0)
}

/// Lista los **usuarios-login** del hub (los `hub_user` con email = cuenta cloud) para el panel
/// admin. Incluye los desactivados (`is_active = 0`) para que el admin los vea y pueda re-activar.
/// Ordenados por email.
pub async fn list_login_users(db: &dyn DatabaseAdapter) -> Result<Vec<LoginUser>> {
    let res = db
        .query(
            "SELECT id, email, name, role, is_active FROM hub_user \
              WHERE email IS NOT NULL AND email != '' ORDER BY email",
            &Params::new(),
        )
        .await?;
    Ok(res
        .rows
        .iter()
        .map(|r| LoginUser {
            id: r["id"].as_str().unwrap_or_default().to_string(),
            email: r["email"].as_str().unwrap_or_default().to_string(),
            name: r["name"].as_str().unwrap_or_default().to_string(),
            role: r["role"].as_str().unwrap_or_default().to_string(),
            is_active: r["is_active"].as_i64().unwrap_or(0) != 0,
        })
        .collect())
}

// ── Sesiones ────────────────────────────────────────────────────────────────────────────────

/// Abre una sesión para `user_id` y devuelve el token opaco (lo guarda el frontend y lo manda en
/// cada petición). TTL en segundos. `device_id` = identidad estable del dispositivo que aporta el
/// host (Tauri = id de máquina; web-PWA = id persistido), o `None` si el login no la aporta; se
/// persiste en la columna `hub_session.device_id` (migración de sistema v8, ADR-0154) y la usa el
/// límite de dispositivos [`enforce_device_limit`]. NO desaloja por sí sola: el takeover es un
/// paso aparte que el server ejecuta ANTES según el plan.
pub async fn create_session(
    db: &dyn DatabaseAdapter,
    user_id: &str,
    ttl_secs: i64,
    device_id: Option<&str>,
) -> Result<String> {
    let token = format!("{}{}", new_id(), new_id()).replace('-', "");
    let expires = (chrono::Utc::now() + chrono::Duration::seconds(ttl_secs)).to_rfc3339();
    let mut p = Params::new();
    p.insert("token".into(), json!(token));
    p.insert("user_id".into(), json!(user_id));
    p.insert("now".into(), json!(now_rfc3339()));
    p.insert("expires".into(), json!(expires));
    p.insert("device_id".into(), json!(device_id));
    db.execute(
        "INSERT INTO hub_session (token, user_id, created_at, expires_at, device_id) \
          VALUES (:token, :user_id, :now, :expires, :device_id)",
        &p,
    )
    .await?;
    Ok(token)
}

/// Aplica el **límite de dispositivos** del plan (ADR-0154) ANTES de abrir una sesión nueva.
///
/// *Single active device session*: con `max_devices == 1` y un `device_id` presente, el hub solo
/// admite **un dispositivo activo** a la vez. Al abrir sesión en un dispositivo nuevo se
/// **desalojan** (borran) todas las sesiones cuyo `device_id` **difiera** del nuevo —incluidas las
/// `NULL` de logins que no aportaron device_id—; las del mismo dispositivo se conservan. El
/// dispositivo desalojado deja de resolver su token → 401 en su siguiente petición (takeover).
///
/// Con `max_devices == 0` (**ilimitado**: Hub Cloud multi-dispositivo, o token de entitlement
/// antiguo sin el claim) o sin `device_id` (login que no identifica el dispositivo) es un **no-op**
/// (comportamiento actual: no se desaloja a nadie).
///
/// El borrado es *hub-wide* sobre `hub_session` a propósito: `max_devices` es un límite del plan,
/// no del usuario, así que el segundo dispositivo desaloja al primero sea quien sea el operario.
pub async fn enforce_device_limit(
    db: &dyn DatabaseAdapter,
    max_devices: u32,
    device_id: Option<&str>,
) -> Result<()> {
    // Solo el plan de 1 dispositivo con un device_id conocido desaloja. 0 = ilimitado.
    let (1, Some(device_id)) = (max_devices, device_id) else {
        return Ok(());
    };
    let mut p = Params::new();
    p.insert("device_id".into(), json!(device_id));
    // `!=` no casa NULL en SQL (NULL != 'x' es NULL, no TRUE): expandimos a «NULL o distinto» para
    // desalojar también las sesiones sin device_id. Portable SQLite/Postgres (sin `IS DISTINCT FROM`).
    db.execute(
        "DELETE FROM hub_session WHERE device_id IS NULL OR device_id != :device_id",
        &p,
    )
    .await?;
    Ok(())
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
///
/// `owner` se resuelve como `admin`: el provisioning siembra al creador del hub con ese rol
/// ([`seed_owner`], ADR-0157) y `auth.rs` ya lo trata como admin para el gate FUERTE (ajustes,
/// certificado, import/export), pero **ningún** módulo del catálogo declara
/// `role_permissions.owner` —los 24 solo conocen `admin`/`manager`/`employee`—, así que el
/// PROPIETARIO del hub se quedaba con el conjunto VACÍO y toda query de módulo le respondía
/// `permission_denied`. Verificado por pantalla el 2026-07-31: tras importar el blueprint de
/// restaurante (280 productos, 26 mesas), el dueño veía el hub vacío, los KPIs en «No
/// disponible» y ni una sección de módulo en el menú. No amplía privilegios: es estrictamente
/// menos de lo que ya le concede el gate admin.
pub fn permissions_for_role(registry: &Registry, role: &str) -> HashSet<String> {
    let role = if role.eq_ignore_ascii_case("owner") { "admin" } else { role };
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

/// Permisos de una **sesión de usuario local**: lo que conceden los módulos a su rol MÁS el permiso
/// del core (ADR-0192, `hub.users.view`) — leer el personal del hub, que ya es público en el grid de
/// PIN del login.
///
/// Separado de [`permissions_for_role`] a propósito: aquello responde «qué conceden los MÓDULOS a
/// este rol» y lo consumen la herencia `owner`→`admin` y el contador de la pestaña Roles. Si el
/// permiso del core viviera ahí, hasta un rol que ningún manifest declara recibiría permisos y cada
/// rol pintaría un permiso fantasma. Lo que decide quién puede leer el personal no es el rol: es
/// **tener sesión local**. Una API key nunca pasa por aquí (su contexto sale de su scope).
pub fn session_permissions(registry: &Registry, role: &str) -> HashSet<String> {
    let mut perms = permissions_for_role(registry, role);
    perms.insert(crate::hub_users::VIEW_USERS_PERMISSION.to_string());
    perms
}

#[cfg(test)]
mod tests {
    use super::*;
    use erplora_db::{testutil::fresh_db, PgAdapter};

    /// Prepara la identidad para los unit tests. La columna `hub_session.device_id` la añade la
    /// **migración de sistema v8** (ADR-0154); en los unit tests de identidad la creamos a mano
    /// tras el baseline, igual que `device_trust_gate` monta `hub_trusted_device` (v2) a mano.
    async fn setup_identity(db: &PgAdapter) {
        ensure_tables(db).await.unwrap();
        db.execute_batch("ALTER TABLE hub_session ADD COLUMN device_id TEXT;")
            .await
            .unwrap();
    }

    /// `ensure_tables` + la columna `hub_user.email` (**migración de sistema v9**, ADR-0157),
    /// montada a mano — igual que `setup_identity` monta el `device_id` (v8). Para los tests del
    /// owner sembrado / enlace por email / alta-baja de usuarios-login, sin pasar por el boot real.
    async fn ensure_identity_email(db: &PgAdapter) {
        ensure_tables(db).await.unwrap();
        db.execute_batch("ALTER TABLE hub_user ADD COLUMN email TEXT NOT NULL DEFAULT '';")
            .await
            .unwrap();
    }

    /// `device_id` persistido en la sesión `token` (o `None` si la fila no existe / es NULL).
    async fn session_device_id(db: &PgAdapter, token: &str) -> Option<String> {
        let mut p = Params::new();
        p.insert("token".into(), json!(token));
        let res = db
            .query(
                "SELECT device_id FROM hub_session WHERE token = :token",
                &p,
            )
            .await
            .unwrap();
        res.rows
            .first()
            .and_then(|r| r["device_id"].as_str().map(|s| s.to_string()))
    }

    /// Manifiesto como los 24 reales: conceden permisos a `admin`/`manager`/`employee`,
    /// NINGUNO declara `owner`.
    fn modulo_con_roles_habituales() -> Registry {
        let manifest: crate::manifest::Manifest = serde_json::from_value(serde_json::json!({
            "id": "inventory",
            "name": "Inventory",
            "version": "1.0.0",
            "role_permissions": {
                "admin": ["inventory.view_product", "inventory.add_product"],
                "manager": ["inventory.view_product"],
                "employee": ["inventory.view_product"],
            },
        }))
        .expect("manifiesto de prueba");
        let mut reg = Registry::new();
        reg.status.insert("inventory".into(), crate::registry::ModuleStatus::Active);
        reg.installed.push(manifest);
        reg
    }

    /// 🔴 El PROPIETARIO del hub se quedaba sin un solo permiso de módulo.
    ///
    /// El provisioning siembra al creador con rol `owner` (ADR-0157) y `auth.rs` ya lo trata
    /// como admin para el gate fuerte (ajustes, certificado, import/export). Pero ningún módulo
    /// declara `role_permissions.owner`, así que `permissions_for_role("owner")` devolvía vacío
    /// y TODA query de módulo respondía `permission_denied`: tras importar un blueprint con 280
    /// productos, el dueño veía el hub vacío y los KPIs en «No disponible» (verificado por
    /// pantalla el 2026-07-31 en un hub recién creado).
    #[test]
    fn el_owner_hereda_los_permisos_de_admin() {
        let reg = modulo_con_roles_habituales();

        let de_admin = permissions_for_role(&reg, "admin");
        let de_owner = permissions_for_role(&reg, "owner");

        assert!(!de_admin.is_empty(), "el fixture debe conceder permisos a admin");
        assert_eq!(de_owner, de_admin, "el owner debe ver al menos lo que ve un admin");
    }

    /// El resto de roles no cambia: `owner` es el único alias, no una barra libre.
    #[test]
    fn los_demas_roles_siguen_igual() {
        let reg = modulo_con_roles_habituales();

        assert_eq!(permissions_for_role(&reg, "manager").len(), 1);
        assert!(permissions_for_role(&reg, "employee").contains("inventory.view_product"));
        assert!(
            permissions_for_role(&reg, "cajero").is_empty(),
            "un rol que ningún módulo declara no recibe permisos"
        );
    }

    #[tokio::test]
    async fn pin_login_and_session_roundtrip() {
        let db = fresh_db().await;
        setup_identity(&db).await;

        let uid = create_user(&db, "María", "1234", "manager", None)
            .await
            .unwrap();

        // PIN correcto resuelve al usuario; PIN incorrecto no.
        let ok = verify_pin(&db, "María", "1234").await.unwrap();
        assert_eq!(ok.as_ref().map(|u| u.id.clone()), Some(uid.clone()));
        assert_eq!(ok.unwrap().role, "manager");
        assert!(verify_pin(&db, "María", "0000").await.unwrap().is_none());

        // Sesión: crear → resolver → logout.
        let token = create_session(&db, &uid, 3600, None).await.unwrap();
        assert_eq!(resolve_session(&db, &token).await.unwrap().unwrap().id, uid);
        delete_session(&db, &token).await.unwrap();
        assert!(resolve_session(&db, &token).await.unwrap().is_none());

        // Sesión caducada no resuelve.
        let expired = create_session(&db, &uid, -10, None).await.unwrap();
        assert!(resolve_session(&db, &expired).await.unwrap().is_none());
    }

    #[tokio::test]
    async fn create_session_persists_device_id() {
        // ADR-0154: `create_session` guarda el `device_id` aportado por el host (Some) y lo deja
        // NULL cuando el login no lo aporta (None).
        let db = fresh_db().await;
        setup_identity(&db).await;
        let uid = create_user(&db, "Ada", "1234", "admin", None).await.unwrap();

        let with_dev = create_session(&db, &uid, 3600, Some("dev-A")).await.unwrap();
        assert_eq!(session_device_id(&db, &with_dev).await.as_deref(), Some("dev-A"));

        let without = create_session(&db, &uid, 3600, None).await.unwrap();
        assert_eq!(session_device_id(&db, &without).await, None);

        // Ambas resuelven al usuario (el device_id no cambia la resolución de la sesión).
        assert_eq!(resolve_session(&db, &with_dev).await.unwrap().unwrap().id, uid);
        assert_eq!(resolve_session(&db, &without).await.unwrap().unwrap().id, uid);
    }

    #[tokio::test]
    async fn enforce_device_limit_one_evicts_other_devices_and_nulls() {
        // ADR-0154 *single active device session*: con max_devices == 1 y un device_id nuevo,
        // se desalojan (borran) TODAS las sesiones cuyo device_id difiera —incluidas las NULL de
        // logins que no aportaron device_id—; las del MISMO dispositivo sobreviven.
        let db = fresh_db().await;
        setup_identity(&db).await;
        let uid = create_user(&db, "Ada", "1234", "admin", None).await.unwrap();

        let tok_a = create_session(&db, &uid, 3600, Some("dev-A")).await.unwrap();
        let tok_null = create_session(&db, &uid, 3600, None).await.unwrap();
        let tok_a2 = create_session(&db, &uid, 3600, Some("dev-A")).await.unwrap();

        // Llega un login del dispositivo B: desaloja A y la sesión sin device_id, no la de B aún.
        enforce_device_limit(&db, 1, Some("dev-B")).await.unwrap();
        assert!(resolve_session(&db, &tok_a).await.unwrap().is_none(), "A desalojado");
        assert!(resolve_session(&db, &tok_null).await.unwrap().is_none(), "NULL desalojado");
        assert!(resolve_session(&db, &tok_a2).await.unwrap().is_none(), "otra de A desalojada");

        // Ahora abre B; una segunda sesión del MISMO dispositivo B no se auto-desaloja.
        let tok_b = create_session(&db, &uid, 3600, Some("dev-B")).await.unwrap();
        enforce_device_limit(&db, 1, Some("dev-B")).await.unwrap();
        assert!(resolve_session(&db, &tok_b).await.unwrap().is_some(), "B (mismo device) sobrevive");
    }

    #[tokio::test]
    async fn enforce_device_limit_unlimited_or_no_device_is_noop() {
        // max_devices == 0 (ilimitado, p. ej. Hub Cloud) o sin device_id → no se desaloja a nadie.
        let db = fresh_db().await;
        setup_identity(&db).await;
        let uid = create_user(&db, "Ada", "1234", "admin", None).await.unwrap();

        let tok_a = create_session(&db, &uid, 3600, Some("dev-A")).await.unwrap();
        let tok_b = create_session(&db, &uid, 3600, Some("dev-B")).await.unwrap();

        // Ilimitado: aunque llegue un device nuevo, nadie cae.
        enforce_device_limit(&db, 0, Some("dev-C")).await.unwrap();
        assert!(resolve_session(&db, &tok_a).await.unwrap().is_some());
        assert!(resolve_session(&db, &tok_b).await.unwrap().is_some());

        // max_devices == 1 pero SIN device_id (login que no identifica dispositivo): tampoco desaloja.
        enforce_device_limit(&db, 1, None).await.unwrap();
        assert!(resolve_session(&db, &tok_a).await.unwrap().is_some());
        assert!(resolve_session(&db, &tok_b).await.unwrap().is_some());
    }

    #[tokio::test]
    async fn set_pin_enables_pin_login_for_existing_user() {
        let db = fresh_db().await;
        ensure_identity_email(&db).await;
        // Cloud-linked user provisioned without a PIN (first online login).
        let user = get_or_link_cloud_user(&db, "7", "Ada", "admin", None, None)
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
    async fn seed_owner_is_idempotent_and_creates_owner() {
        // ADR-0157 (corrección Ioan): el owner es el CREADOR, sembrado del env `HUB_OWNER_EMAIL`.
        // `seed_owner` crea un `hub_user` role=owner con ese email y cloud_user_id NULL; re-sembrar
        // (mismo email) es no-op (no duplica ni cambia).
        let db = fresh_db().await;
        ensure_identity_email(&db).await;

        assert!(
            seed_owner(&db, "boss@bar.com").await.unwrap(),
            "primera siembra → true (fila nueva)"
        );
        let users = list_login_users(&db).await.unwrap();
        assert_eq!(users.len(), 1, "un único owner sembrado");
        assert_eq!(users[0].email, "boss@bar.com");
        assert_eq!(users[0].role, "owner", "sembrado como owner");

        // Idempotente: re-sembrar el MISMO email no duplica ni cambia.
        assert!(
            !seed_owner(&db, "boss@bar.com").await.unwrap(),
            "segunda siembra → false (ya existía)"
        );
        assert_eq!(
            list_login_users(&db).await.unwrap().len(),
            1,
            "sigue habiendo un solo owner (no duplica)"
        );

        // Email vacío = no-op (no siembra nada).
        assert!(!seed_owner(&db, "  ").await.unwrap());
        assert_eq!(list_login_users(&db).await.unwrap().len(), 1);
    }

    #[tokio::test]
    async fn login_links_seeded_owner_by_email_keeping_owner_role() {
        // El owner sembrado (cloud_user_id NULL) se ENLAZA en su primer login por email,
        // conservando role=owner (NO cae a `employee`). Un segundo login usa el cloud_user_id.
        let db = fresh_db().await;
        ensure_identity_email(&db).await;
        seed_owner(&db, "boss@bar.com").await.unwrap();

        // Primer login: enlaza por email → owner.
        let user = get_or_link_cloud_user(&db, "99", "Boss", "employee", Some("boss@bar.com"), None)
            .await
            .unwrap();
        assert_eq!(user.role, "owner", "el owner sembrado conserva su rol");
        assert_eq!(user.cloud_user_id.as_deref(), Some("99"), "queda enlazado");
        assert_eq!(
            list_login_users(&db).await.unwrap().len(),
            1,
            "NO crea una segunda fila: reusa el owner sembrado"
        );

        // Segundo login (ya enlazado): resuelve por cloud_user_id, mismo usuario/rol.
        let again = get_or_link_cloud_user(&db, "99", "Boss", "employee", Some("boss@bar.com"), None)
            .await
            .unwrap();
        assert_eq!(again.id, user.id);
        assert_eq!(again.role, "owner");
    }

    #[tokio::test]
    async fn login_without_matching_seed_provisions_default_role() {
        // Un miembro que pasa el gate de presencia SIN fila pre-sembrada → rol de mínimo privilegio
        // (red de seguridad), con su email persistido.
        let db = fresh_db().await;
        ensure_identity_email(&db).await;

        let user = get_or_link_cloud_user(&db, "5", "Nuevo", "employee", Some("nuevo@bar.com"), None)
            .await
            .unwrap();
        assert_eq!(user.role, "employee");
        let listed = list_login_users(&db).await.unwrap();
        assert_eq!(listed.len(), 1);
        assert_eq!(listed[0].email, "nuevo@bar.com", "email persistido");
    }

    #[tokio::test]
    async fn cloud_user_link_is_idempotent() {
        let db = fresh_db().await;
        ensure_identity_email(&db).await;
        let a = get_or_link_cloud_user(&db, "42", "Demo", "cashier", None, None)
            .await
            .unwrap();
        let b = get_or_link_cloud_user(&db, "42", "OtroNombre", "admin", None, None)
            .await
            .unwrap();
        assert_eq!(a.id, b.id, "el mismo cloud_user_id reusa el hub_user");
        assert_eq!(
            b.role, "cashier",
            "no re-provisiona ni cambia el rol existente"
        );
    }

    // ── Role floor re-evaluated on every login (hub#347, plan step 2b rule C) ────────────────
    //
    // `default_role` decides how a BRAND NEW row is provisioned; `role_floor` is the minimum the
    // cloud account imposes on a row that ALREADY exists. They are separate parameters on purpose:
    // conflating them would turn `HUB_DEFAULT_ROLE` into a floor and re-promote, on every login,
    // anybody the hub had deliberately demoted.

    /// Rol actual de un `hub_user` leído de la BD (no del valor devuelto): así los tests comprueban
    /// que el suelo se **persiste**, no solo que se reporta bien en la respuesta del login.
    async fn stored_role(db: &dyn DatabaseAdapter, id: &str) -> String {
        let mut p = Params::new();
        p.insert("id".into(), json!(id));
        let res = db
            .query("SELECT role FROM hub_user WHERE id = :id", &p)
            .await
            .unwrap();
        res.rows[0]["role"].as_str().unwrap().to_string()
    }

    #[tokio::test]
    async fn the_floor_raises_an_existing_employee_on_a_later_login() {
        // The bug: the role was a snapshot of the first login, so a promotion in the SaaS never
        // reached the hub. Same row, raised — not a second user.
        let db = fresh_db().await;
        ensure_identity_email(&db).await;
        let first = get_or_link_cloud_user(&db, "42", "Ada", "employee", None, None)
            .await
            .unwrap();
        assert_eq!(first.role, "employee");

        let second = get_or_link_cloud_user(&db, "42", "Ada", "employee", None, Some("admin"))
            .await
            .unwrap();
        assert_eq!(second.id, first.id, "misma fila, no una nueva");
        assert_eq!(second.role, "admin", "el suelo sube el rol local");
        assert_eq!(
            stored_role(&db, &first.id).await,
            "admin",
            "y queda persistido, no solo devuelto"
        );
    }

    #[tokio::test]
    async fn the_floor_never_lowers_an_owner() {
        // Re-evaluating an `admin` floor must not demote the hub owner: `owner` is already above
        // it. Otherwise every login of the owner would quietly strip their ownership.
        let db = fresh_db().await;
        ensure_identity_email(&db).await;
        seed_owner(&db, "boss@bar.com").await.unwrap();
        let linked = get_or_link_cloud_user(&db, "1", "Boss", "employee", Some("boss@bar.com"), Some("admin"))
            .await
            .unwrap();
        assert_eq!(linked.role, "owner", "el owner sembrado sigue siendo owner");
        assert_eq!(stored_role(&db, &linked.id).await, "owner");
    }

    #[tokio::test]
    async fn without_a_floor_the_local_role_is_left_exactly_as_it_was() {
        // Losing the administrative role in the cloud does NOT lower the local role: the bridge is
        // a floor, not a synchronisation. Taking access away is deactivating the `hub_user`
        // (rule D, hub#348), never a silent demotion.
        let db = fresh_db().await;
        ensure_identity_email(&db).await;
        // As the real caller does it: an account admin gets both the default role AND the floor.
        let raised = get_or_link_cloud_user(&db, "42", "Ada", "admin", None, Some("admin"))
            .await
            .unwrap();
        assert_eq!(raised.role, "admin");

        // Demoted in the cloud: no floor any more, and the local role stays untouched.
        let demoted_in_cloud = get_or_link_cloud_user(&db, "42", "Ada", "employee", None, None)
            .await
            .unwrap();
        assert_eq!(demoted_in_cloud.role, "admin", "el suelo sube, nunca baja");
        assert_eq!(stored_role(&db, &raised.id).await, "admin");
    }

    #[tokio::test]
    async fn a_brand_new_row_is_never_created_below_the_floor() {
        // Same invariant on the three paths: on the way out the role is never under the floor.
        // The real caller derives `default_role` from the same cloud role, so this is a no-op for
        // it; it guards a future caller that passes a floor and forgets the default.
        let db = fresh_db().await;
        ensure_identity_email(&db).await;
        let user = get_or_link_cloud_user(&db, "42", "Ada", "employee", None, Some("admin"))
            .await
            .unwrap();
        assert_eq!(user.role, "admin");
        assert_eq!(stored_role(&db, &user.id).await, "admin");
    }

    #[tokio::test]
    async fn the_floor_applies_when_linking_an_invited_row_by_email() {
        // An invited user whose row was created as `employee` and who is an admin of the account:
        // the floor applies on the very login that links the row, not only from the second one on.
        let db = fresh_db().await;
        ensure_identity_email(&db).await;
        create_login_user(&db, "socia@bar.com", "employee").await.unwrap();

        let linked = get_or_link_cloud_user(&db, "77", "Socia", "employee", Some("socia@bar.com"), Some("admin"))
            .await
            .unwrap();
        assert_eq!(linked.role, "admin");
        assert_eq!(linked.cloud_user_id.as_deref(), Some("77"), "queda enlazada");
        assert_eq!(
            list_login_users(&db).await.unwrap().len(),
            1,
            "reusa la fila invitada, no crea otra"
        );
    }

    #[tokio::test]
    async fn a_custom_module_role_does_not_satisfy_the_admin_floor() {
        // A custom role declared by a module (`bartender`, `kitchen`…) may carry a generous
        // `role_permissions`, but that is not the "administers the hub" property. Assuming it did
        // would leave an account owner locked out of their own hub — the very thing rule C exists
        // to prevent — so an unranked role is raised.
        let db = fresh_db().await;
        ensure_identity_email(&db).await;
        let user = get_or_link_cloud_user(&db, "42", "Ada", "bartender", None, None)
            .await
            .unwrap();
        assert_eq!(user.role, "bartender");

        let raised = get_or_link_cloud_user(&db, "42", "Ada", "bartender", None, Some("admin"))
            .await
            .unwrap();
        assert_eq!(raised.role, "admin");
    }

    #[tokio::test]
    async fn a_login_can_never_write_owner_however_the_floor_arrives() {
        // Defence in depth: the only caller passes `admin`, but the runtime clamps the floor too.
        // Hub ownership comes from `HUB_OWNER_EMAIL` (ADR-0157) and no token may grant it.
        let db = fresh_db().await;
        ensure_identity_email(&db).await;
        get_or_link_cloud_user(&db, "42", "Ada", "employee", None, None)
            .await
            .unwrap();

        let user = get_or_link_cloud_user(&db, "42", "Ada", "employee", None, Some("owner"))
            .await
            .unwrap();
        assert_eq!(user.role, "admin", "un suelo `owner` se acota a `admin`");
        assert_eq!(stored_role(&db, &user.id).await, "admin");
    }

    #[tokio::test]
    async fn a_floor_that_does_not_administer_the_hub_raises_nothing() {
        // A non-administrative "floor" is not a floor: it must not overwrite the local role, in
        // either direction. Guards against a future caller passing the raw cloud role through.
        let db = fresh_db().await;
        ensure_identity_email(&db).await;
        let first = get_or_link_cloud_user(&db, "42", "Ada", "cashier", None, None)
            .await
            .unwrap();

        for bogus in ["manager", "employee", "member", ""] {
            let user = get_or_link_cloud_user(&db, "42", "Ada", "cashier", None, Some(bogus))
                .await
                .unwrap();
            assert_eq!(user.role, "cashier", "`{bogus}` no es un suelo");
        }
        assert_eq!(stored_role(&db, &first.id).await, "cashier");
    }

    #[tokio::test]
    async fn create_login_user_upserts_by_email_and_deactivate_is_symmetric() {
        // ADR-0157 §7: alta/baja de usuarios-login por email (flujo admin). Alta = upsert por email
        // (crea o reactiva+re-rol); baja = desactiva (simétrica, idempotente).
        let db = fresh_db().await;
        ensure_identity_email(&db).await;

        // Alta nueva.
        let u = create_login_user(&db, "ana@bar.com", "manager").await.unwrap();
        assert_eq!(u.role, "manager");
        assert!(u.cloud_user_id.is_none(), "aún sin login → sin cloud_user_id");
        assert!(u.is_active);

        // Re-alta (mismo email, rol nuevo) = upsert: misma fila, rol actualizado.
        let u2 = create_login_user(&db, "ana@bar.com", "admin").await.unwrap();
        assert_eq!(u2.id, u.id, "reusa la fila del email (no duplica)");
        assert_eq!(u2.role, "admin", "actualiza el rol");
        assert_eq!(list_login_users(&db).await.unwrap().len(), 1);

        // Baja: desactiva (true la primera vez, false si ya estaba inactiva = idempotente).
        assert!(deactivate_login_user(&db, "ana@bar.com").await.unwrap());
        assert!(!deactivate_login_user(&db, "ana@bar.com").await.unwrap());
        let listed = list_login_users(&db).await.unwrap();
        assert_eq!(listed.len(), 1, "sigue listada (audit), pero inactiva");
        assert!(!listed[0].is_active);

        // Re-alta reactiva la misma fila.
        let u3 = create_login_user(&db, "ana@bar.com", "employee").await.unwrap();
        assert_eq!(u3.id, u.id);
        assert!(u3.is_active, "el alta reactiva");
        assert_eq!(u3.role, "employee");
    }

    #[tokio::test]
    async fn new_pins_are_argon2id() {
        // create_user/set_pin escriben siempre argon2id (string PHC `$argon2id$...`).
        let db = fresh_db().await;
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
        let db = fresh_db().await;
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
