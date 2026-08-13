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

/// Código de error **estable** (hub#139) con el que el login rechaza a un `hub_user` desactivado
/// por el propio hub (paso 2b regla D, hub#348). La UI programa y traduce contra este código, no
/// contra el mensaje. Es distinto de `not_a_member`: aquel dice «el SaaS no te reconoce en este
/// hub»; este dice «el hub te cerró la puerta», y solo el hub la reabre.
pub const DEACTIVATED_ERROR_CODE: &str = "user_deactivated";

/// The baseline (v0) schema of the identity tables.
///
/// **`hub_id` is `NOT NULL` with no default** (hub#497). Both tables were the last system tables
/// without a tenant while every other one — `hub_settings`, `hub_api_key`, `hub_module`,
/// `hub_user_profile`, and since hub#489 `hub_trusted_device` — is keyed on `(hub_id, …)`. The
/// *profile* of a person was per hub; the person was not, and a session was not either, so in a
/// shared database a token of one hub authenticated against another.
///
/// No default on purpose: a default would let an `INSERT` that forgot the column succeed and write
/// an unattributable row, and on an authentication table that row is somebody who can sign in
/// nowhere or — worse, if the empty string ever became a hub id — everywhere. Without it the
/// statement fails, loudly, at the first test that runs it.
///
/// The primary keys are **not** recomposed to `(hub_id, …)`, and that is a decision rather than an
/// omission: `hub_user.id` is a UUID and `hub_session.token` is 32 random bytes, so neither can
/// collide across hubs — a composite key would buy no uniqueness and would break every reference
/// that already travels by id alone (`hub_user_profile(hub_id, user_id)`, the `hub_user:<id>` of
/// every audit column, exported bundles, sessions already issued). What was missing was never a
/// key; it was a `WHERE`.
///
/// ⚠️ **`hub_id` only ever reaches a table through this batch on a database that is BORN here**
/// (hub#885). A `CREATE TABLE IF NOT EXISTS` is a **no-op** on a table that already exists — it
/// does not add the columns the new definition lists — and this batch runs on every boot, before
/// the migration engine, so it meets databases it did not create. On a hub deployed before hub#497
/// `hub_user` still has no `hub_id` here, and the column only arrives with the system migration
/// v42 (`hub_identity_hub_scoped`), which runs **afterwards**. That is why the two indexes over
/// `hub_id` are **not** in this batch: they lived here for one release and the boot died 42703
/// (`indexcmds.c` / `ComputeIndexAttrs`) on every existing hub in the fleet — a `CREATE INDEX` on a
/// column the no-op above did not create — while Swarm rolled the update back and the deploy CLI
/// printed `Service converged`. They belong to v42, which creates them right after the `ALTER` that
/// guarantees the column and the `UPDATE` that fills the rows already there. Same rule as
/// `installer::ENSURE_HUB_MODULE`, and for the same reason: a change in the SHAPE of a system table
/// goes through a numbered migration, always, because that is the only step that reaches a database
/// that already exists.
///
/// `ix_hub_user_cloud` stays because `cloud_user_id` is part of the v0 baseline itself: every
/// `hub_user` that has ever existed has that column.
const ENSURE_TABLES: &str = "\
CREATE TABLE IF NOT EXISTS hub_user (\
  id TEXT PRIMARY KEY, hub_id TEXT NOT NULL, name TEXT NOT NULL, pin_hash TEXT NOT NULL DEFAULT '', \
  role TEXT NOT NULL DEFAULT '', cloud_user_id TEXT, is_active INTEGER NOT NULL DEFAULT 1, \
  created_at TEXT NOT NULL);\
CREATE TABLE IF NOT EXISTS hub_session (\
  token TEXT PRIMARY KEY, hub_id TEXT NOT NULL, user_id TEXT NOT NULL, created_at TEXT NOT NULL, \
  expires_at TEXT NOT NULL);\
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
    hub_id: &str,
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
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("name".into(), json!(name));
    p.insert("pin_hash".into(), json!(pin_hash));
    p.insert("role".into(), json!(role));
    p.insert("cloud_user_id".into(), json!(cloud_user_id));
    p.insert("now".into(), json!(now_rfc3339()));
    db.execute(
        "INSERT INTO hub_user (id, hub_id, name, pin_hash, role, cloud_user_id, is_active, created_at) \
          VALUES (:id, :hub_id, :name, :pin_hash, :role, :cloud_user_id, 1, :now)",
        &p,
    )
    .await?;
    Ok(id)
}

/// Asegura una identidad fija para `AuthMode::Dev`, donde el frontend es la autoridad de las
/// cabeceras y puede traer un id demo ya persistido. No cambia una identidad existente.
pub async fn ensure_dev_user(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    id: &str,
    name: &str,
    role: &str,
) -> Result<()> {
    let mut p = Params::new();
    p.insert("id".into(), json!(id));
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("name".into(), json!(name));
    p.insert("role".into(), json!(role));
    p.insert("now".into(), json!(now_rfc3339()));
    db.execute(
        "INSERT INTO hub_user (id, hub_id, name, pin_hash, role, cloud_user_id, is_active, created_at) \
         VALUES (:id, :hub_id, :name, '', :role, NULL, 1, :now) \
         ON CONFLICT (id) DO NOTHING",
        &p,
    )
    .await?;
    Ok(())
}

/// Fija (o cambia) el PIN de un usuario **existente** por id. Lo usa el alta de PIN tras el primer
/// login cloud (§2.9): el usuario ya está provisionado (sin PIN) y elige su PIN en el dispositivo de
/// confianza. `pin` vacío borra el PIN (deja el usuario no autenticable por PIN). Idempotente.
pub async fn set_pin(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    user_id: &str,
    pin: &str,
) -> Result<()> {
    // Siempre escribe argon2id (string PHC); `pin` vacío deja el hash vacío (no autenticable).
    let pin_hash = if pin.is_empty() {
        String::new()
    } else {
        hash_pin_argon2(pin)?
    };
    let mut p = Params::new();
    p.insert("id".into(), json!(user_id));
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("pin_hash".into(), json!(pin_hash));
    db.execute(
        "UPDATE hub_user SET pin_hash = :pin_hash WHERE id = :id AND hub_id = :hub_id",
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
    hub_id: &str,
    name: &str,
    pin: &str,
) -> Result<Option<HubUser>> {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("name".into(), json!(name));
    let res = db
        .query(
            "SELECT id, name, role, cloud_user_id, is_active, pin_hash FROM hub_user \
              WHERE hub_id = :hub_id AND name = :name AND is_active = 1",
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
pub async fn list_pin_users(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
) -> Result<Vec<(String, String, String)>> {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    let res = db
        .query(
            "SELECT id, name, role FROM hub_user \
              WHERE hub_id = :hub_id AND is_active = 1 AND pin_hash IS NOT NULL AND pin_hash != '' \
              ORDER BY name",
            &p,
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

/// `true` if `pin` already opens the session of **another active** user of this hub (plan step 2b,
/// hub#355). `excluding_id` is the user being edited, so re-typing your own PIN is not a clash.
///
/// A PIN is an **attribution** mechanism, not authentication: the pinpad resolves NAME + PIN
/// ([`verify_pin`]), so two people behind the same four digits means the sale is attributed to
/// whoever was tapped on the grid, and whoever actually typed is invisible. This is the only guard
/// that can catch it, and only at the moment the hub sees the digits in clear: the hashes are
/// argon2id with a random salt each, so two equal PINs do NOT produce equal hashes and there is
/// nothing to compare in SQL. Hence the linear scan verifying the candidate against each stored
/// hash — an alta is rare and the staff of a hub is tens of rows.
///
/// **Active users only.** A deactivated row cannot sign in, so it holds no digits hostage; the
/// alternative would burn PINs forever and leak that a given PIN once belonged to somebody.
pub async fn pin_is_taken(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    pin: &str,
    excluding_id: Option<&str>,
) -> Result<bool> {
    if pin.is_empty() {
        return Ok(false); // no PIN, no collision.
    }
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    let res = db
        .query(
            "SELECT id, pin_hash FROM hub_user \
              WHERE hub_id = :hub_id AND is_active = 1 AND pin_hash IS NOT NULL AND pin_hash != ''",
            &p,
        )
        .await?;
    for row in &res.rows {
        let id = row["id"].as_str().unwrap_or_default();
        if excluding_id.is_some_and(|excluded| excluded == id) {
            continue;
        }
        if check_pin(row["pin_hash"].as_str().unwrap_or_default(), pin) {
            return Ok(true);
        }
    }
    Ok(false)
}

/// `true` if this hub already knows somebody by this name — **active or not**, ignoring case (plan
/// step 2b, hub#355). Used by the local-user alta; the generic alta and the edit keep asking only
/// about active rows ([`crate::hub_users`]), because that is what makes the pinpad ambiguous.
///
/// The extra reach is the point: a deactivated row is a door the hub (or the SaaS, hub#348) closed,
/// and creating a namesake next to it hands a working PIN to somebody who was locked out, leaving
/// two identities for one person. Reopening it is [`crate::hub_users::update`] — an explicit,
/// audited decision — not a second alta.
///
/// Case-insensitive because the pinpad is: `marta ruiz` and `Marta Ruiz` are two rows the cashier
/// cannot tell apart on the login grid, and "which of the two Martas is this?" is exactly the
/// question a PIN exists to answer.
pub async fn name_is_known(db: &dyn DatabaseAdapter, hub_id: &str, name: &str) -> Result<bool> {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("name".into(), json!(name.trim().to_lowercase()));
    let res = db
        .query(
            "SELECT id FROM hub_user WHERE hub_id = :hub_id AND LOWER(name) = :name",
            &p,
        )
        .await?;
    Ok(!res.rows.is_empty())
}

/// `true` if this hub already knows this **email** — active or not, ignoring case (plan step 2b,
/// hub#356). `excluding_id` is the user being edited, so re-typing your own email is not a clash.
/// The email twin of [`name_is_known`], and it reads the column the ACCESS plane reads
/// (`hub_user.email`), not the one Personal displays.
///
/// The reach over **deactivated** rows is the point, and it is the same argument as `name_is_known`
/// seen from the other identity: a deactivated row is a door somebody closed — the hub in Personal,
/// or the SaaS by revoking the membership (hub#348) — and inviting the same email again would hand
/// that person a second, active row while the first one keeps their history. Worse, the SaaS cannot
/// stop it: a revocation there is a **row delete**, so a second `POST /device/members/` is just a
/// fresh membership. Reopening the door is [`crate::hub_users::update`] — explicit and audited.
pub async fn email_is_known(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    email: &str,
    excluding_id: Option<&str>,
) -> Result<bool> {
    let email = email.trim().to_lowercase();
    if email.is_empty() {
        return Ok(false);
    }
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("email".into(), json!(email));
    p.insert("id".into(), json!(excluding_id.unwrap_or_default()));
    let res = db
        .query(
            "SELECT id FROM hub_user \
              WHERE hub_id = :hub_id AND LOWER(email) = :email AND id != :id",
            &p,
        )
        .await?;
    Ok(!res.rows.is_empty())
}

/// Writes the email of an existing `hub_user` **where access looks for it** (`hub_user.email`).
///
/// That column is the one the whole access plane resolves against: [`get_or_link_cloud_user`] links
/// a pre-provisioned row by it on the first login, [`revoke_cloud_access`] closes the door by it
/// when the SaaS revokes a membership, and [`create_login_user`]/[`deactivate_login_user`] are the
/// `/api/members` alta and baja. `hub_user_profile.email` is a **different** field — what the
/// person's profile shows — so writing only that one (what the Personal alta used to do) produced a
/// row the login could not find: it fell through to provisioning a SECOND identity with the
/// least-privilege role, losing the role the administrator had granted.
pub async fn set_email(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    user_id: &str,
    email: &str,
) -> Result<()> {
    let mut p = Params::new();
    p.insert("id".into(), json!(user_id));
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("email".into(), json!(email.trim()));
    db.execute(
        "UPDATE hub_user SET email = :email WHERE id = :id AND hub_id = :hub_id",
        &p,
    )
        .await?;
    Ok(())
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

/// **Siembra al creador del hub** desde el env del provisioning del SaaS (ADR-0157, corrección de
/// Ioan 2026-07-26): el owner es el **CREADOR** del hub y el despliegue lo trae ya inyectado como
/// `HUB_OWNER_EMAIL`. Crea un `hub_user` con rol [`crate::hub_users::ADMIN_ROLE`], ese
/// `email` y `cloud_user_id = NULL` (aún no ha hecho login: al primer login
/// `get_or_link_cloud_user` lo enlaza por email). Sin PIN.
///
/// **Se siembra `admin`, no `owner`** (paso 2b, hub#349): `owner` salió del catálogo de roles del
/// hub porque era la misma palabra en los dos planos y ningún módulo le concedía nada, y `admin`
/// es lo más alto del plano de NEGOCIO. **Quién** es el propietario no cambia —sigue saliendo del
/// env, nunca de un token (ADR-0157)— y **qué puede** tampoco: `admin` concede exactamente lo que
/// concedía `owner` (el gate ya trataba igual a los dos y `permissions_for_role` ya resolvía
/// `owner` como `admin`).
///
/// **Idempotente**: si ya existe un `hub_user` con ese email, **no hace nada** (no duplica ni pisa
/// un rol/estado existente). Devuelve `true` si sembró una fila nueva, `false` si ya existía.
/// Sustituye al bootstrap «primer login = owner» (retirado): el owner ya no depende de quién entre
/// primero, sino de quién creó el hub.
pub async fn seed_owner(db: &dyn DatabaseAdapter, hub_id: &str, email: &str) -> Result<bool> {
    let email = email.trim();
    if email.is_empty() {
        return Ok(false);
    }
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("email".into(), json!(email));
    let existing = db
        .query(
            "SELECT id FROM hub_user WHERE hub_id = :hub_id AND email = :email",
            &p,
        )
        .await?;
    if !existing.rows.is_empty() {
        return Ok(false); // ya sembrado: idempotente, no cambia nada.
    }
    let id = new_id();
    let mut ins = Params::new();
    ins.insert("id".into(), json!(id));
    ins.insert("hub_id".into(), json!(hub_id));
    ins.insert("name".into(), json!(name_from_email(email)));
    ins.insert("email".into(), json!(email));
    ins.insert("role".into(), json!(crate::hub_users::ADMIN_ROLE));
    ins.insert("now".into(), json!(now_rfc3339()));
    db.execute(
        "INSERT INTO hub_user (id, hub_id, name, pin_hash, role, cloud_user_id, is_active, created_at, email) \
          VALUES (:id, :hub_id, :name, '', :role, NULL, 1, :now, :email)",
        &ins,
    )
    .await?;
    Ok(true)
}

/// Sube el rol de un `hub_user` **al suelo** que impone el rol de su cuenta en el Cloud, si aún no
/// llega (paso 2b regla C, hub#347). Devuelve el usuario tal y como queda.
///
/// Es un **suelo**, no una sincronización, y por eso solo sube:
///  - Si el rol local ya **administra el hub** ([`crate::hub_users::is_admin_role`]: `admin` o su
///    alias legacy `owner`) no toca nada. Ese es el caso que impide que reevaluar el suelo
///    **degrade** a quien ya está arriba — incluida una fila `owner` de un hub que aún no pasó por
///    la migración v12 (hub#349).
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
    hub_id: &str,
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
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("role".into(), json!(floor));
    db.execute(
        "UPDATE hub_user SET role = :role WHERE id = :id AND hub_id = :hub_id",
        &p,
    )
        .await?;
    Ok(HubUser {
        role: floor.to_string(),
        ..user
    })
}

/// **Cierra el acceso local de una identidad cloud** cuando el SaaS revoca su membresía en este hub
/// (paso 2b regla D, hub#348). Quitar el acceso NO es bajar el rol (eso es la regla C, que solo
/// sube): es desactivar el `hub_user`, que es lo único que cierra **todas** las puertas a la vez —
/// `resolve_session` hace `JOIN … AND u.is_active = 1` (una sesión abierta deja de resolver en la
/// siguiente petición), `verify_pin` y `list_pin_users` filtran igual (ni login por PIN ni presencia
/// en el pinpad) y el dispositivo de confianza no es por sí solo una vía de entrada.
///
/// Además **borra sus sesiones**, como la baja del admin en Personal (`hub_users::update`): que el
/// `JOIN` ya las invalide no basta, porque una reincorporación futura devolvería a la vida tokens
/// emitidos antes de la revocación (TTL de 30 días).
///
/// Alcanza tanto la fila ya enlazada (`cloud_user_id`) como la **pre-provisionada por email** que
/// aún no ha hecho login (invitación/owner sembrado): el email del JWT está autenticado (firma del
/// SaaS) y es la misma clave con la que `get_or_link_cloud_user` enlaza, así que no amplía la
/// confianza. Idempotente: solo toca filas activas. Devuelve cuántas cerró.
pub async fn revoke_cloud_access(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    cloud_user_id: &str,
    email: Option<&str>,
) -> Result<usize> {
    let mut ids: Vec<String> = Vec::new();
    let mut by_cloud_id = Params::new();
    by_cloud_id.insert("hub_id".into(), json!(hub_id));
    by_cloud_id.insert("cuid".into(), json!(cloud_user_id));
    let linked = db
        .query(
            "SELECT id FROM hub_user \
              WHERE hub_id = :hub_id AND cloud_user_id = :cuid AND is_active = 1",
            &by_cloud_id,
        )
        .await?;
    push_ids(&linked, &mut ids);
    if let Some(email) = email.map(str::trim).filter(|s| !s.is_empty()) {
        let mut by_email = Params::new();
        by_email.insert("hub_id".into(), json!(hub_id));
        by_email.insert("email".into(), json!(email));
        let invited = db
            .query(
                "SELECT id FROM hub_user \
                  WHERE hub_id = :hub_id AND email = :email AND is_active = 1",
                &by_email,
            )
            .await?;
        push_ids(&invited, &mut ids);
    }
    let now = now_rfc3339();
    for id in &ids {
        let mut p = Params::new();
        p.insert("id".into(), json!(id));
        p.insert("hub_id".into(), json!(hub_id));
        p.insert("now".into(), json!(now));
        db.execute(
            "UPDATE hub_user SET is_active = 0, cloud_revoked_at = :now \
              WHERE id = :id AND hub_id = :hub_id",
            &p,
        )
        .await?;
        db.execute(
            "DELETE FROM hub_session WHERE user_id = :id AND hub_id = :hub_id",
            &p,
        )
        .await?;
    }
    Ok(ids.len())
}

/// Acumula los `id` de un resultado en `out` sin repetir (las dos búsquedas de
/// [`revoke_cloud_access`] —por `cloud_user_id` y por email— pueden devolver la misma fila).
fn push_ids(res: &erplora_db::QueryResult, out: &mut Vec<String>) {
    for row in &res.rows {
        let id = row["id"].as_str().unwrap_or_default().to_string();
        if !id.is_empty() && !out.contains(&id) {
            out.push(id);
        }
    }
}

/// Qué hacer con una fila **desactivada** que vuelve a presentarse con una membresía válida
/// (paso 2b regla D, hub#348). Hay dos autoridades que cierran una puerta y solo una la reabre:
///
///  - **La cerró el SaaS** (`cloud_revoked_at` no vacío, la escribió [`revoke_cloud_access`]): la
///    causa era la membresía y la membresía ha vuelto, así que la fila se **reincorpora**. Se
///    reutiliza la MISMA fila —el historial, la auditoría y las ventas apuntan a ese id— y se
///    vuelve al rol que concede la membresía de HOY (`default_role`, luego el suelo de la regla C):
///    reincorporar es admitir de nuevo, no deshacer, y no resucita permisos que ya no le tocan.
///  - **La cerró el hub** (`cloud_revoked_at` vacío: baja del admin en Personal o en `/api/members`,
///    ADR-0157 §7): un token **no** la reabre. Esa decisión es del hub y el espejo del SaaS puede ir
///    retrasado —`remove_member` conserva la baja local aunque falle la llamada al SaaS—, así que
///    dejar que una membresía rancia reactivase sería devolver dentro a quien el hub echó. Se
///    rechaza con [`DEACTIVATED_ERROR_CODE`] **sin** provisionar nada.
async fn reinstate_or_reject(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    user: HubUser,
    revoked_by_cloud: bool,
    default_role: &str,
) -> Result<HubUser> {
    if !revoked_by_cloud {
        return Err(crate::errors::RuntimeError::Domain {
            code: DEACTIVATED_ERROR_CODE.to_string(),
            message: "this account is deactivated in this hub: ask an administrator to reinstate it"
                .to_string(),
        });
    }
    let mut p = Params::new();
    p.insert("id".into(), json!(user.id));
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("role".into(), json!(default_role));
    db.execute(
        "UPDATE hub_user SET is_active = 1, cloud_revoked_at = '', role = :role \
          WHERE id = :id AND hub_id = :hub_id",
        &p,
    )
    .await?;
    Ok(HubUser {
        role: default_role.to_string(),
        is_active: true,
        ..user
    })
}

/// `true` si la fila la cerró el SaaS (regla D) y no el hub. Lee la columna de la v11; una fila de
/// una BD sin migrar devuelve `false` = «la cerró el hub», que es el lado conservador.
fn was_revoked_by_cloud(row: &serde_json::Value) -> bool {
    !row["cloud_revoked_at"]
        .as_str()
        .unwrap_or_default()
        .trim()
        .is_empty()
}

/// Resuelve (o crea/enlaza) el `hub_user` vinculado a una identidad cloud. Adaptador del **JWT de
/// usuario**: tras verificar el token (server), se mapea a un usuario local. La resolución es en
/// dos pasos (ADR-0157):
///  1. Por **`cloud_user_id`** (usuario ya enlazado en un login previo).
///  2. Por **`email`** (si viene y no está vacío): una fila **pre-provisionada sin `cloud_user_id`**
///     — el **creador sembrado** (`seed_owner`) o un usuario **invitado** por el admin (`create_login_user`).
///     Se **enlaza** (fija `cloud_user_id`) conservando su rol (el sembrado / el de la invitación) y
///     su email. Así el creador del hub mantiene su `admin` (no cae a `employee`) en su primer login.
///  3. Si no hay coincidencia → se **provisiona** con `default_role` (red de seguridad para un
///     miembro que pasa el gate de presencia sin fila local; rol de mínimo privilegio).
///
/// En los dos primeros casos —fila que YA existe— se aplica además el **suelo de rol**
/// (`role_floor`, paso 2b regla C, hub#347): el rol de la cuenta en el Cloud se reevalúa en **cada**
/// login y sube el rol local si se ha quedado corto, sin bajarlo nunca. Antes el rol era una foto
/// del primer login y ascender a alguien en el SaaS no llegaba jamás al hub. Ver
/// [`raise_role_to_floor`]. `role_floor = None` → la fila se devuelve intacta.
///
/// **Las dos búsquedas miran también las filas DESACTIVADAS** (paso 2b regla D, hub#348). Antes
/// filtraban `is_active = 1`, así que una fila cerrada sencillamente no casaba y el paso 3
/// provisionaba una **segunda fila** al lado, activa y con el rol por defecto: desactivar a alguien
/// no servía de nada porque su siguiente login le fabricaba una identidad nueva. Ahora la fila se
/// reutiliza siempre y [`reinstate_or_reject`] decide si se reincorpora (la cerró el SaaS y la
/// membresía ha vuelto) o se rechaza (la cerró el hub).
pub async fn get_or_link_cloud_user(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    cloud_user_id: &str,
    default_name: &str,
    default_role: &str,
    email: Option<&str>,
    role_floor: Option<&str>,
) -> Result<HubUser> {
    // 1) Por cloud_user_id (ya enlazado), activa o no.
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("cuid".into(), json!(cloud_user_id));
    let res = db
        .query(
            "SELECT id, name, role, cloud_user_id, is_active, cloud_revoked_at FROM hub_user \
              WHERE hub_id = :hub_id AND cloud_user_id = :cuid",
            &p,
        )
        .await?;
    if let Some(row) = res.rows.first() {
        let user = row_to_user(row);
        let user = if user.is_active {
            user
        } else {
            reinstate_or_reject(db, hub_id, user, was_revoked_by_cloud(row), default_role).await?
        };
        return raise_role_to_floor(db, hub_id, user, role_floor).await;
    }
    // 2) Por email: fila pre-provisionada (owner sembrado / invitado) sin cloud_user_id → enlazar.
    if let Some(email) = email.map(str::trim).filter(|s| !s.is_empty()) {
        let mut pe = Params::new();
        pe.insert("hub_id".into(), json!(hub_id));
        pe.insert("email".into(), json!(email));
        let by_email = db
            .query(
                "SELECT id, name, role, cloud_user_id, is_active, cloud_revoked_at FROM hub_user \
                  WHERE hub_id = :hub_id AND email = :email AND cloud_user_id IS NULL",
                &pe,
            )
            .await?;
        if let Some(row) = by_email.rows.first() {
            let user = row_to_user(row);
            // La reincorporación va ANTES del enlace: si la puerta la cerró el hub, el rechazo no
            // debe dejar la fila enlazada a la cuenta cloud que acaba de ser rechazada.
            let user = if user.is_active {
                user
            } else {
                reinstate_or_reject(db, hub_id, user, was_revoked_by_cloud(row), default_role)
                    .await?
            };
            let mut up = Params::new();
            up.insert("id".into(), json!(user.id));
            up.insert("hub_id".into(), json!(hub_id));
            up.insert("cuid".into(), json!(cloud_user_id));
            db.execute(
                "UPDATE hub_user SET cloud_user_id = :cuid WHERE id = :id AND hub_id = :hub_id",
                &up,
            )
            .await?;
            let linked = HubUser {
                cloud_user_id: Some(cloud_user_id.to_string()),
                ..user
            };
            return raise_role_to_floor(db, hub_id, linked, role_floor).await;
        }
    }
    // 3) Provisiona una fila nueva (rol de mínimo privilegio) con su email si vino. El suelo se
    //    aplica también aquí para que la invariante sea la MISMA en los tres caminos: al salir, el
    //    rol nunca está por debajo del suelo. El llamador real ya calcula `default_role` con el
    //    mismo rol de cuenta, así que en la práctica es un no-op; lo que evita es que un llamador
    //    futuro pase un suelo y se olvide del rol por defecto y la fila nueva nazca por debajo.
    let email = email.map(str::trim).unwrap_or("");
    let id = create_login_user_row(db, hub_id, &new_id(), default_name, "", default_role, Some(cloud_user_id), email).await?;
    let created = HubUser {
        id,
        name: default_name.to_string(),
        role: default_role.to_string(),
        cloud_user_id: Some(cloud_user_id.to_string()),
        is_active: true,
    };
    raise_role_to_floor(db, hub_id, created, role_floor).await
}

/// INSERT de bajo nivel de un `hub_user` con `email` explícito (lo comparten el provisioning por
/// email y el enlace-o-crea del login). No comprueba duplicados (los llamadores lo hacen).
async fn create_login_user_row(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
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
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("name".into(), json!(name));
    p.insert("pin_hash".into(), json!(pin_hash));
    p.insert("role".into(), json!(role));
    p.insert("cloud_user_id".into(), json!(cloud_user_id));
    p.insert("email".into(), json!(email));
    p.insert("now".into(), json!(now_rfc3339()));
    db.execute(
        "INSERT INTO hub_user (id, hub_id, name, pin_hash, role, cloud_user_id, is_active, created_at, email) \
          VALUES (:id, :hub_id, :name, :pin_hash, :role, :cloud_user_id, 1, :now, :email)",
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
    hub_id: &str,
    email: &str,
    role: &str,
) -> Result<HubUser> {
    let email = email.trim();
    // El rol tiene que ser uno que el SaaS pueda poner en la membresía (hub#356). Es la MISMA
    // guarda que la del alta de Personal, aquí porque esta es la otra puerta del mismo alta: dejar
    // una sin ella sería guardar el candado y dejar la ventana abierta.
    crate::hub_users::ensure_account_role_is_grantable(role)?;
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("email".into(), json!(email));
    let existing = db
        .query(
            "SELECT id, name, role, cloud_user_id, is_active FROM hub_user \
              WHERE hub_id = :hub_id AND email = :email",
            &p,
        )
        .await?;
    if let Some(row) = existing.rows.first() {
        let user = row_to_user(row);
        let mut up = Params::new();
        up.insert("id".into(), json!(user.id));
        up.insert("hub_id".into(), json!(hub_id));
        up.insert("role".into(), json!(role));
        // `cloud_revoked_at = ''`: reactivar cierra el episodio de la regla D (hub#348). Si no se
        // limpiase, una baja POSTERIOR del admin heredaría la marca del cloud y un login podría
        // reabrirla — el hub dejaría de ser dueño de su propia baja.
        db.execute(
            "UPDATE hub_user SET role = :role, is_active = 1, cloud_revoked_at = '' \
              WHERE id = :id AND hub_id = :hub_id",
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
    create_login_user_row(db, hub_id, &id, &name_from_email(email), "", role, None, email).await?;
    Ok(HubUser {
        id,
        name: name_from_email(email),
        role: role.to_string(),
        cloud_user_id: None,
        is_active: true,
    })
}

/// **Baja de un usuario-login** por email (flujo admin, ADR-0157 §7 — la simetría del alta). Marca
/// `is_active = 0` (no borra: audit + posible re-alta) y **borra sus sesiones abiertas**, igual que
/// la baja desde Personal (`hub_users::update`): que `resolve_session` filtre `is_active = 1` ya la
/// invalida, pero borrarlas evita que una re-alta futura devuelva a la vida tokens emitidos antes
/// de la baja (TTL de 30 días). Idempotente. Devuelve `true` si afectó a alguna fila activa. La
/// revocación de la membresía en el SaaS (`members_remove`) la hace el server.
///
/// Escribe `cloud_revoked_at = ''` a propósito: **esta baja es del hub**, no del SaaS, así que
/// ningún login la reabre (paso 2b regla D, hub#348 — ver [`reinstate_or_reject`]). Solo el hub la
/// levanta, con el alta/re-invitación ([`create_login_user`]).
pub async fn deactivate_login_user(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    email: &str,
) -> Result<bool> {
    let email = email.trim();
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("email".into(), json!(email));
    let res = db
        .execute(
            "UPDATE hub_user SET is_active = 0, cloud_revoked_at = '' \
              WHERE hub_id = :hub_id AND email = :email AND is_active = 1",
            &p,
        )
        .await?;
    if res.affected == 0 {
        return Ok(false);
    }
    db.execute(
        "DELETE FROM hub_session WHERE hub_id = :hub_id AND user_id IN \
          (SELECT id FROM hub_user WHERE hub_id = :hub_id AND email = :email)",
        &p,
    )
    .await?;
    Ok(true)
}

/// Lista los **usuarios-login** del hub (los `hub_user` con email = cuenta cloud) para el panel
/// admin. Incluye los desactivados (`is_active = 0`) para que el admin los vea y pueda re-activar.
/// Ordenados por email.
pub async fn list_login_users(db: &dyn DatabaseAdapter, hub_id: &str) -> Result<Vec<LoginUser>> {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    let res = db
        .query(
            "SELECT id, email, name, role, is_active FROM hub_user \
              WHERE hub_id = :hub_id AND email IS NOT NULL AND email != '' ORDER BY email",
            &p,
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
    hub_id: &str,
    user_id: &str,
    ttl_secs: i64,
    device_id: Option<&str>,
) -> Result<String> {
    let token = format!("{}{}", new_id(), new_id()).replace('-', "");
    let expires = (chrono::Utc::now() + chrono::Duration::seconds(ttl_secs)).to_rfc3339();
    let mut p = Params::new();
    p.insert("token".into(), json!(token));
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("user_id".into(), json!(user_id));
    p.insert("now".into(), json!(now_rfc3339()));
    p.insert("expires".into(), json!(expires));
    p.insert("device_id".into(), json!(device_id));
    db.execute(
        "INSERT INTO hub_session (token, hub_id, user_id, created_at, expires_at, device_id) \
          VALUES (:token, :hub_id, :user_id, :now, :expires, :device_id)",
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
/// **Hub-wide, no database-wide** (hub#497): sin el `hub_id` este `DELETE` barría también las
/// sesiones de los demás hubs de la base — abrir la caja aquí firmaba la salida del negocio de al
/// lado, y ni su personal ni el nuestro tenían forma de saber por qué.
pub async fn enforce_device_limit(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    max_devices: u32,
    device_id: Option<&str>,
) -> Result<()> {
    // Solo el plan de 1 dispositivo con un device_id conocido desaloja. 0 = ilimitado.
    let (1, Some(device_id)) = (max_devices, device_id) else {
        return Ok(());
    };
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("device_id".into(), json!(device_id));
    // `!=` no casa NULL en SQL (NULL != 'x' es NULL, no TRUE): expandimos a «NULL o distinto» para
    // desalojar también las sesiones sin device_id. Portable SQLite/Postgres (sin `IS DISTINCT FROM`).
    db.execute(
        "DELETE FROM hub_session \
          WHERE hub_id = :hub_id AND (device_id IS NULL OR device_id != :device_id)",
        &p,
    )
    .await?;
    Ok(())
}

/// Resuelve una sesión válida (no caducada) a su `hub_user` activo. `None` si no existe/caducó.
///
/// **The door** (hub#497). A session token is a bearer credential: whoever holds it is signed in as
/// whoever it names. Matched by `token` alone — as this did until now — a token minted by another
/// hub of the same database resolved here, with the role its holder has *there*. That is not
/// "seeing too much", it is getting in, and it is why both sides of the join are scoped: the
/// session row must be this hub's **and** so must the person it names.
pub async fn resolve_session(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    token: &str,
) -> Result<Option<HubUser>> {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("token".into(), json!(token));
    p.insert("now".into(), json!(now_rfc3339()));
    let res = db
        .query(
            "SELECT u.id, u.name, u.role, u.cloud_user_id, u.is_active \
              FROM hub_session s JOIN hub_user u ON u.id = s.user_id AND u.hub_id = s.hub_id \
              WHERE s.hub_id = :hub_id AND s.token = :token \
                AND s.expires_at > :now AND u.is_active = 1",
            &p,
        )
        .await?;
    Ok(res.rows.first().map(row_to_user))
}

/// Cierra una sesión (logout).
pub async fn delete_session(db: &dyn DatabaseAdapter, hub_id: &str, token: &str) -> Result<()> {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("token".into(), json!(token));
    db.execute(
        "DELETE FROM hub_session WHERE hub_id = :hub_id AND token = :token",
        &p,
    )
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
// ABIERTO: §2.9/architecture no cierran el esquema exacto del device-trust local (¿expiración del
// trust?, ¿revocación por admin desde el dashboard?, ¿binding del device_id a un hub_user?). Esto
// implementa lo mínimo coherente con el flujo actual; cerrar el diseño antes de endurecerlo.

/// Marca un dispositivo como **de confianza** (idempotente). Lo llama el server tras un login online
/// (cloud) correcto. `label` es un nombre legible opcional (p. ej. "Caja 1").
///
/// Scoped por `hub_id` (hub#489, migración de sistema v23): la confianza es de **un hub**, no de la
/// base de datos. La clave `(hub_id, device_id)` deja además que la MISMA tablet sea de confianza en
/// dos negocios a la vez —el caso real de quien trabaja en dos sitios—, cada uno con su etiqueta y
/// su modo, sin que el login de uno pise el del otro.
pub async fn trust_device(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    device_id: &str,
    label: &str,
    default_name: &str,
) -> Result<()> {
    // INSERT … ON CONFLICT: re-marcar un dispositivo ya de confianza no falla ni duplica.
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("device_id".into(), json!(device_id));
    p.insert("label".into(), json!(label));
    p.insert("default_name".into(), json!(default_name));
    p.insert("now".into(), json!(now_rfc3339()));
    // `name` va SOLO en el INSERT (hub#494, migración de sistema v44). El `DO UPDATE` sigue
    // tocando **solo `label`** —«quién entró la última vez», que sí cambia en cada entrada— y por
    // eso el nombre que puso el dueño («Barra», «Cocina») sobrevive al siguiente login. Meterlo en
    // el `SET` sería reintroducir el bug entero: una etiqueta que nadie eligió a propósito,
    // reescrita por el cliente en cada turno, delante del botón que corta la tablet equivocada.
    db.execute(
        "INSERT INTO hub_trusted_device (hub_id, device_id, label, name, trusted_at) \
          VALUES (:hub_id, :device_id, :label, :default_name, :now) \
          ON CONFLICT (hub_id, device_id) DO UPDATE SET label = excluded.label",
        &p,
    )
    .await?;
    Ok(())
}

/// `true` si `device_id` está marcado como de confianza **de este hub** (gate del login por PIN,
/// §2.9). La confianza ganada en el hub de al lado no abre esta puerta (hub#489).
pub async fn is_device_trusted(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    device_id: &str,
) -> Result<bool> {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("device_id".into(), json!(device_id));
    let res = db
        .query(
            "SELECT 1 AS ok FROM hub_trusted_device \
              WHERE hub_id = :hub_id AND device_id = :device_id",
            &p,
        )
        .await?;
    Ok(!res.rows.is_empty())
}

/// Removes the trust row an id that names the **hub itself** left behind (hub#454).
///
/// Deployed hubs carry one: until this, a browser presented the `hub_id` as its `X-Device-Id`, so
/// every browser shared a single row — and that id is published unauthenticated by
/// `GET /api/hub/context`. A trusted row keyed on a value anyone can fetch, possibly carrying the
/// lax `personal` mode, is the escalation; the client-side fix does not reach it.
///
/// Runs on **every boot**, not once as a versioned migration: it must also clean a database
/// restored from a backup taken before this change (pgBackRest is the only real copy of a hub,
/// ADR-0213), and re-running a `DELETE` of an id that is not a device is a no-op by construction.
///
/// Scoped **twice** to `hub_id`, since hub#489 gave the table its own tenant column: a hub sweeps
/// the row whose *device* is its own id, and only among its **own** rows. Before that column the
/// scope was the device side alone, because the table was common ground in a database shared by
/// several hubs (the pre-ADR-0201 shape) — now a neighbour that happens to know a device by this
/// hub's id keeps it, which is its business and not this hub's to decide.
pub async fn forget_hub_id_as_device(db: &dyn DatabaseAdapter, hub_id: &str) -> Result<()> {
    if hub_id.is_empty() {
        return Ok(());
    }
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    db.execute(
        "DELETE FROM hub_trusted_device WHERE hub_id = :hub_id AND device_id = :hub_id",
        &p,
    )
    .await?;
    Ok(())
}

/// Revoca la confianza de un dispositivo **de este hub** (perdido/robado). Idempotente (hub#489: no
/// alcanza la fila del hub de al lado que conozca un dispositivo con ese mismo id).
pub async fn untrust_device(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    device_id: &str,
) -> Result<()> {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("device_id".into(), json!(device_id));
    db.execute(
        "DELETE FROM hub_trusted_device WHERE hub_id = :hub_id AND device_id = :device_id",
        &p,
    )
    .await?;
    Ok(())
}

// ── Permisos ────────────────────────────────────────────────────────────────────────────────

/// Permisos efectivos de un `role`: unión de `role_permissions[role]` de **todos los módulos
/// activos** (ARQUITECTURA.md §2.5/§9.2). Si algún módulo concede `*` al rol, el usuario tiene `*`.
///
/// `owner` se resuelve como `admin`. El provisioning **sembraba** al creador del hub con ese rol
/// ([`seed_owner`], ADR-0157) y `auth.rs` ya lo trataba como admin para el gate FUERTE (ajustes,
/// certificado, import/export), pero **ningún** módulo del catálogo declara
/// `role_permissions.owner` —los 24 solo conocen `admin`/`manager`/`employee`—, así que el
/// PROPIETARIO del hub se quedaba con el conjunto VACÍO y toda query de módulo le respondía
/// `permission_denied`. Verificado por pantalla el 2026-07-31: tras importar el blueprint de
/// restaurante (280 productos, 26 mesas), el dueño veía el hub vacío, los KPIs en «No
/// disponible» y ni una sección de módulo en el menú. No amplía privilegios: es estrictamente
/// menos de lo que ya le concede el gate admin.
///
/// Desde hub#349 el alias es **legacy**: `owner` salió del catálogo ([`crate::hub_users::
/// BASE_ROLES`]), la siembra escribe `admin` y la migración de sistema v12 renombra las filas que
/// lo llevaban. Se conserva por lo mismo que [`crate::hub_users::is_admin_role`]: una fila puede
/// llegar sin pasar por la migración, y quitarlo la dejaría sin ver un solo dato de módulo.
pub fn permissions_for_role(registry: &Registry, role: &str) -> HashSet<String> {
    let role = if role.eq_ignore_ascii_case("owner") { "admin" } else { role };
    let mut perms = HashSet::new();
    for m in &registry.installed {
        if !registry.is_active(&m.id) {
            continue;
        }
        if let Some(list) = m.role_permissions.get(role) {
            for perm in list {
                // **El namespace del core no se concede desde un manifest** (misma regla de
                // propiedad que `permissions::is_elevable`, hub#351: un módulo solo habla de lo
                // suyo). Si contase, un `module.zip` de terceros podría escribir
                // `role_permissions.employee = ["hub.administer"]` y volver a poner la checklist
                // de administración delante del camarero — el agujero que hub#435 cierra —, o
                // acuñar cualquier otro permiso del core con tres líneas de JSON.
                if perm.starts_with(crate::hub_users::CORE_NAMESPACE) {
                    continue;
                }
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
    // Y el permiso de ADMINISTRAR el hub (hub#435), para los mismos roles que reconoce el gate HTTP
    // (`server::auth::require_admin_session` → [`crate::hub_users::is_admin_role`]). Se concede
    // aquí y no en el catálogo de roles por lo mismo que el de arriba: lo decide el ROL de la
    // sesión, no lo que conceda un manifest — y en un hub VACÍO, que es cuando la checklist más
    // vale, ningún módulo concede nada y el administrador se quedaría sin sus propios ítems.
    if crate::hub_users::is_admin_role(role) {
        perms.insert(crate::hub_users::ADMINISTER_PERMISSION.to_string());
    }
    perms
}

#[cfg(test)]
mod tests {
    use super::*;
    use erplora_db::{testutil::fresh_db, PgAdapter};

    /// The hub these unit tests are the identity of (hub#497). Every scoped call passes it, so a
    /// statement that lost its `hub_id` fails here rather than silently reading the whole table.
    const HUB: &str = "hub-identity";

    /// Prepara la identidad para los unit tests. La columna `hub_session.device_id` la añade la
    /// **migración de sistema v8** (ADR-0154); en los unit tests de identidad la creamos a mano
    /// tras el baseline, igual que `device_trust_gate` monta `hub_trusted_device` (v2) a mano.
    async fn setup_identity(db: &PgAdapter) {
        ensure_tables(db).await.unwrap();
        db.execute_batch("ALTER TABLE hub_session ADD COLUMN device_id TEXT;")
            .await
            .unwrap();
    }

    /// `ensure_tables` + las columnas que el login cloud necesita y el baseline v0 no trae:
    /// `hub_user.email` (**migración de sistema v9**, ADR-0157) y `hub_user.cloud_revoked_at`
    /// (**v11**, regla D de hub#348), montadas a mano — igual que `setup_identity` monta el
    /// `device_id` (v8). Para los tests del owner sembrado / enlace por email / alta-baja de
    /// usuarios-login / revocación, sin pasar por el boot real.
    async fn ensure_identity_email(db: &PgAdapter) {
        ensure_tables(db).await.unwrap();
        db.execute_batch(
            "ALTER TABLE hub_user ADD COLUMN email TEXT NOT NULL DEFAULT '';\
             ALTER TABLE hub_user ADD COLUMN cloud_revoked_at TEXT NOT NULL DEFAULT '';",
        )
        .await
        .unwrap();
    }

    /// Como [`ensure_identity_email`] pero además con `hub_session.device_id` (v8), para los tests
    /// de revocación que abren una sesión de verdad y comprueban que muere con la membresía.
    async fn ensure_identity_with_sessions(db: &PgAdapter) {
        ensure_identity_email(db).await;
        db.execute_batch("ALTER TABLE hub_session ADD COLUMN device_id TEXT;")
            .await
            .unwrap();
    }

    /// `true` si el `hub_user` sigue activo.
    async fn stored_is_active(db: &PgAdapter, id: &str) -> bool {
        let mut p = Params::new();
        p.insert("id".into(), json!(id));
        let res = db
            .query("SELECT is_active FROM hub_user WHERE id = :id", &p)
            .await
            .unwrap();
        res.rows
            .first()
            .map(|r| r["is_active"].as_i64().unwrap_or(0) != 0)
            .unwrap_or(false)
    }

    /// Cuántas filas de `hub_user` llevan este email (una revocación no debe dejar gemelas).
    async fn rows_with_email(db: &PgAdapter, email: &str) -> usize {
        let mut p = Params::new();
        p.insert("email".into(), json!(email));
        db.query("SELECT id FROM hub_user WHERE email = :email", &p)
            .await
            .unwrap()
            .rows
            .len()
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

    /// Who administers the hub is decided by the ROLE, and only the roles the gate itself accepts
    /// get the permission that says so (hub#435).
    ///
    /// It has to work on an EMPTY hub — the moment the onboarding checklist is worth the most — so
    /// it cannot come from `permissions_for_role`, which with no modules installed grants nothing
    /// to anybody, administrator included.
    #[test]
    fn only_an_administrator_session_carries_the_core_administration_permission() {
        let empty = Registry::new();
        for role in ["admin", "ADMIN", "owner", "Owner"] {
            let perms = session_permissions(&empty, role);
            assert!(
                perms.contains(crate::hub_users::ADMINISTER_PERMISSION),
                "{role} administra el hub y el gate HTTP le deja pasar"
            );
            assert!(perms.contains(crate::hub_users::VIEW_USERS_PERMISSION));
        }
        for role in ["manager", "employee", "bartender", ""] {
            assert!(
                !session_permissions(&empty, role).contains(crate::hub_users::ADMINISTER_PERMISSION),
                "{role} NO administra el hub"
            );
        }
        // Y sigue sin ensuciar el catálogo de roles: lo concede la SESIÓN, no los módulos.
        assert!(permissions_for_role(&empty, "admin").is_empty());
    }

    /// Un `module.zip` no puede acuñar permisos del core.
    ///
    /// Misma regla de propiedad que `permissions::is_elevable` (hub#351): un módulo solo habla de
    /// su namespace. Sin esta guarda, tres líneas de JSON en un manifest de terceros
    /// (`role_permissions.employee = ["hub.administer"]`) volverían a poner la checklist de
    /// administración —y su botón a `/settings`— delante del camarero, que es el agujero de
    /// hub#435 reabierto por la puerta de al lado.
    #[test]
    fn un_manifest_no_puede_conceder_permisos_del_core() {
        let manifest: crate::manifest::Manifest = serde_json::from_value(serde_json::json!({
            "id": "greedy",
            "name": "Greedy",
            "version": "1.0.0",
            "role_permissions": {
                "employee": [
                    crate::hub_users::ADMINISTER_PERMISSION,
                    crate::hub_users::VIEW_USERS_PERMISSION,
                    "greedy.ok"
                ]
            }
        }))
        .expect("manifiesto de prueba");
        let mut reg = Registry::new();
        reg.status.insert("greedy".into(), crate::registry::ModuleStatus::Active);
        reg.installed.push(manifest);

        let perms = permissions_for_role(&reg, "employee");
        assert!(!perms.contains(crate::hub_users::ADMINISTER_PERMISSION));
        assert!(!perms.contains(crate::hub_users::VIEW_USERS_PERMISSION));
        assert!(perms.contains("greedy.ok"), "lo suyo sí lo concede");

        // Y la sesión tampoco lo hereda por la puerta de atrás: un empleado sigue sin administrar,
        // aunque conserva el permiso de namespace que toda sesión local tiene de todas formas.
        let session = session_permissions(&reg, "employee");
        assert!(!session.contains(crate::hub_users::ADMINISTER_PERMISSION));
        assert!(session.contains(crate::hub_users::VIEW_USERS_PERMISSION));
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

        let uid = create_user(&db, HUB, "María", "1234", "manager", None)
            .await
            .unwrap();

        // PIN correcto resuelve al usuario; PIN incorrecto no.
        let ok = verify_pin(&db, HUB, "María", "1234").await.unwrap();
        assert_eq!(ok.as_ref().map(|u| u.id.clone()), Some(uid.clone()));
        assert_eq!(ok.unwrap().role, "manager");
        assert!(verify_pin(&db, HUB, "María", "0000").await.unwrap().is_none());

        // Sesión: crear → resolver → logout.
        let token = create_session(&db, HUB, &uid, 3600, None).await.unwrap();
        assert_eq!(resolve_session(&db, HUB, &token).await.unwrap().unwrap().id, uid);
        delete_session(&db, HUB, &token).await.unwrap();
        assert!(resolve_session(&db, HUB, &token).await.unwrap().is_none());

        // Sesión caducada no resuelve.
        let expired = create_session(&db, HUB, &uid, -10, None).await.unwrap();
        assert!(resolve_session(&db, HUB, &expired).await.unwrap().is_none());
    }

    #[tokio::test]
    async fn create_session_persists_device_id() {
        // ADR-0154: `create_session` guarda el `device_id` aportado por el host (Some) y lo deja
        // NULL cuando el login no lo aporta (None).
        let db = fresh_db().await;
        setup_identity(&db).await;
        let uid = create_user(&db, HUB, "Ada", "1234", "admin", None).await.unwrap();

        let with_dev = create_session(&db, HUB, &uid, 3600, Some("dev-A")).await.unwrap();
        assert_eq!(session_device_id(&db, &with_dev).await.as_deref(), Some("dev-A"));

        let without = create_session(&db, HUB, &uid, 3600, None).await.unwrap();
        assert_eq!(session_device_id(&db, &without).await, None);

        // Ambas resuelven al usuario (el device_id no cambia la resolución de la sesión).
        assert_eq!(resolve_session(&db, HUB, &with_dev).await.unwrap().unwrap().id, uid);
        assert_eq!(resolve_session(&db, HUB, &without).await.unwrap().unwrap().id, uid);
    }

    #[tokio::test]
    async fn enforce_device_limit_one_evicts_other_devices_and_nulls() {
        // ADR-0154 *single active device session*: con max_devices == 1 y un device_id nuevo,
        // se desalojan (borran) TODAS las sesiones cuyo device_id difiera —incluidas las NULL de
        // logins que no aportaron device_id—; las del MISMO dispositivo sobreviven.
        let db = fresh_db().await;
        setup_identity(&db).await;
        let uid = create_user(&db, HUB, "Ada", "1234", "admin", None).await.unwrap();

        let tok_a = create_session(&db, HUB, &uid, 3600, Some("dev-A")).await.unwrap();
        let tok_null = create_session(&db, HUB, &uid, 3600, None).await.unwrap();
        let tok_a2 = create_session(&db, HUB, &uid, 3600, Some("dev-A")).await.unwrap();

        // Llega un login del dispositivo B: desaloja A y la sesión sin device_id, no la de B aún.
        enforce_device_limit(&db, HUB, 1, Some("dev-B")).await.unwrap();
        assert!(resolve_session(&db, HUB, &tok_a).await.unwrap().is_none(), "A desalojado");
        assert!(resolve_session(&db, HUB, &tok_null).await.unwrap().is_none(), "NULL desalojado");
        assert!(resolve_session(&db, HUB, &tok_a2).await.unwrap().is_none(), "otra de A desalojada");

        // Ahora abre B; una segunda sesión del MISMO dispositivo B no se auto-desaloja.
        let tok_b = create_session(&db, HUB, &uid, 3600, Some("dev-B")).await.unwrap();
        enforce_device_limit(&db, HUB, 1, Some("dev-B")).await.unwrap();
        assert!(resolve_session(&db, HUB, &tok_b).await.unwrap().is_some(), "B (mismo device) sobrevive");
    }

    #[tokio::test]
    async fn enforce_device_limit_unlimited_or_no_device_is_noop() {
        // max_devices == 0 (ilimitado, p. ej. Hub Cloud) o sin device_id → no se desaloja a nadie.
        let db = fresh_db().await;
        setup_identity(&db).await;
        let uid = create_user(&db, HUB, "Ada", "1234", "admin", None).await.unwrap();

        let tok_a = create_session(&db, HUB, &uid, 3600, Some("dev-A")).await.unwrap();
        let tok_b = create_session(&db, HUB, &uid, 3600, Some("dev-B")).await.unwrap();

        // Ilimitado: aunque llegue un device nuevo, nadie cae.
        enforce_device_limit(&db, HUB, 0, Some("dev-C")).await.unwrap();
        assert!(resolve_session(&db, HUB, &tok_a).await.unwrap().is_some());
        assert!(resolve_session(&db, HUB, &tok_b).await.unwrap().is_some());

        // max_devices == 1 pero SIN device_id (login que no identifica dispositivo): tampoco desaloja.
        enforce_device_limit(&db, HUB, 1, None).await.unwrap();
        assert!(resolve_session(&db, HUB, &tok_a).await.unwrap().is_some());
        assert!(resolve_session(&db, HUB, &tok_b).await.unwrap().is_some());
    }

    #[tokio::test]
    async fn set_pin_enables_pin_login_for_existing_user() {
        let db = fresh_db().await;
        ensure_identity_email(&db).await;
        // Cloud-linked user provisioned without a PIN (first online login).
        let user = get_or_link_cloud_user(&db, HUB, "7", "Ada", "admin", None, None)
            .await
            .unwrap();
        assert!(
            verify_pin(&db, HUB, "Ada", "4242").await.unwrap().is_none(),
            "no PIN yet"
        );

        set_pin(&db, HUB, &user.id, "4242").await.unwrap();
        let ok = verify_pin(&db, HUB, "Ada", "4242").await.unwrap();
        assert_eq!(ok.map(|u| u.id), Some(user.id.clone()));
        assert!(
            verify_pin(&db, HUB, "Ada", "0000").await.unwrap().is_none(),
            "wrong PIN rejected"
        );

        // Empty PIN clears it again.
        set_pin(&db, HUB, &user.id, "").await.unwrap();
        assert!(
            verify_pin(&db, HUB, "Ada", "4242").await.unwrap().is_none(),
            "PIN cleared"
        );
    }

    #[tokio::test]
    async fn seed_owner_is_idempotent_and_seeds_the_hub_administrator() {
        // ADR-0157 (corrección Ioan): el owner es el CREADOR, sembrado del env `HUB_OWNER_EMAIL`.
        // `seed_owner` crea un `hub_user` con ese email y cloud_user_id NULL; re-sembrar (mismo
        // email) es no-op (no duplica ni cambia). Desde hub#349 se siembra con el rol **`admin`**:
        // `owner` salió del catálogo base y `admin` es lo más alto del plano de NEGOCIO. Quién es
        // el propietario no cambia (sigue siendo el email del env, ADR-0157); cambia cómo se
        // deletrea su rol local, y `admin` ya concede exactamente lo mismo que concedía `owner`.
        let db = fresh_db().await;
        ensure_identity_email(&db).await;

        assert!(
            seed_owner(&db, HUB, "boss@bar.com").await.unwrap(),
            "primera siembra → true (fila nueva)"
        );
        let users = list_login_users(&db, HUB).await.unwrap();
        assert_eq!(users.len(), 1, "un único creador sembrado");
        assert_eq!(users[0].email, "boss@bar.com");
        assert_eq!(users[0].role, "admin", "sembrado como admin, nunca `owner`");

        // Idempotente: re-sembrar el MISMO email no duplica ni cambia.
        assert!(
            !seed_owner(&db, HUB, "boss@bar.com").await.unwrap(),
            "segunda siembra → false (ya existía)"
        );
        assert_eq!(
            list_login_users(&db, HUB).await.unwrap().len(),
            1,
            "sigue habiendo un solo creador (no duplica)"
        );

        // Email vacío = no-op (no siembra nada).
        assert!(!seed_owner(&db, HUB, "  ").await.unwrap());
        assert_eq!(list_login_users(&db, HUB).await.unwrap().len(), 1);
    }

    #[tokio::test]
    async fn login_links_the_seeded_creator_by_email_keeping_its_admin_role() {
        // La fila sembrada (cloud_user_id NULL) se ENLAZA en su primer login por email,
        // conservando su rol (NO cae a `employee`). Un segundo login usa el cloud_user_id.
        let db = fresh_db().await;
        ensure_identity_email(&db).await;
        seed_owner(&db, HUB, "boss@bar.com").await.unwrap();

        // Primer login: enlaza por email → conserva el rol sembrado.
        let user = get_or_link_cloud_user(&db, HUB, "99", "Boss", "employee", Some("boss@bar.com"), None)
            .await
            .unwrap();
        assert_eq!(user.role, "admin", "el creador sembrado conserva su rol");
        assert_eq!(user.cloud_user_id.as_deref(), Some("99"), "queda enlazado");
        assert_eq!(
            list_login_users(&db, HUB).await.unwrap().len(),
            1,
            "NO crea una segunda fila: reusa la fila sembrada"
        );

        // Segundo login (ya enlazado): resuelve por cloud_user_id, mismo usuario/rol.
        let again = get_or_link_cloud_user(&db, HUB, "99", "Boss", "employee", Some("boss@bar.com"), None)
            .await
            .unwrap();
        assert_eq!(again.id, user.id);
        assert_eq!(again.role, "admin");
    }

    #[tokio::test]
    async fn login_without_matching_seed_provisions_default_role() {
        // Un miembro que pasa el gate de presencia SIN fila pre-sembrada → rol de mínimo privilegio
        // (red de seguridad), con su email persistido.
        let db = fresh_db().await;
        ensure_identity_email(&db).await;

        let user = get_or_link_cloud_user(&db, HUB, "5", "Nuevo", "employee", Some("nuevo@bar.com"), None)
            .await
            .unwrap();
        assert_eq!(user.role, "employee");
        let listed = list_login_users(&db, HUB).await.unwrap();
        assert_eq!(listed.len(), 1);
        assert_eq!(listed[0].email, "nuevo@bar.com", "email persistido");
    }

    #[tokio::test]
    async fn cloud_user_link_is_idempotent() {
        let db = fresh_db().await;
        ensure_identity_email(&db).await;
        let a = get_or_link_cloud_user(&db, HUB, "42", "Demo", "cashier", None, None)
            .await
            .unwrap();
        let b = get_or_link_cloud_user(&db, HUB, "42", "OtroNombre", "admin", None, None)
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
        let first = get_or_link_cloud_user(&db, HUB, "42", "Ada", "employee", None, None)
            .await
            .unwrap();
        assert_eq!(first.role, "employee");

        let second = get_or_link_cloud_user(&db, HUB, "42", "Ada", "employee", None, Some("admin"))
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
    async fn the_floor_never_lowers_the_seeded_creator() {
        // Re-evaluating the floor on every login must not touch the hub creator seeded from
        // `HUB_OWNER_EMAIL`: they are already at the top of the business plane. Otherwise every
        // login of the owner would quietly rewrite their role.
        let db = fresh_db().await;
        ensure_identity_email(&db).await;
        seed_owner(&db, HUB, "boss@bar.com").await.unwrap();
        let linked = get_or_link_cloud_user(&db, HUB, "1", "Boss", "employee", Some("boss@bar.com"), Some("admin"))
            .await
            .unwrap();
        assert_eq!(linked.role, "admin", "el creador sembrado sigue siendo admin");
        assert_eq!(stored_role(&db, &linked.id).await, "admin");
    }

    #[tokio::test]
    async fn the_floor_never_lowers_a_legacy_owner() {
        // `owner` left the base catalogue in hub#349 and the v12 migration renames the rows that
        // carry it, but the gate still recognises the old spelling. A row that reaches the hub
        // without going through the migration — a restored backup, an import, a runtime still
        // pinned to an older image — must NOT be demoted to `admin` by the floor: re-evaluating it
        // on every login would otherwise strip the owner of a hub that was never migrated.
        let db = fresh_db().await;
        ensure_identity_email(&db).await;
        // La fila se fabrica a mano, sin pasar por el alta: desde hub#356 **ninguna** puerta del
        // alta escribe `owner` —el SaaS no lo concede—, así que usarla aquí probaría lo contrario
        // de lo que este test dice. Una fila así llega restaurando un backup o importando.
        create_login_user_row(&db, HUB, &new_id(), "Boss", "", "owner", None, "legacy@bar.com")
            .await
            .unwrap();

        let linked =
            get_or_link_cloud_user(&db, HUB, "1", "Boss", "employee", Some("legacy@bar.com"), Some("admin"))
                .await
                .unwrap();
        assert_eq!(linked.role, "owner", "un `owner` legacy no se degrada");
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
        let raised = get_or_link_cloud_user(&db, HUB, "42", "Ada", "admin", None, Some("admin"))
            .await
            .unwrap();
        assert_eq!(raised.role, "admin");

        // Demoted in the cloud: no floor any more, and the local role stays untouched.
        let demoted_in_cloud = get_or_link_cloud_user(&db, HUB, "42", "Ada", "employee", None, None)
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
        let user = get_or_link_cloud_user(&db, HUB, "42", "Ada", "employee", None, Some("admin"))
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
        create_login_user(&db, HUB, "socia@bar.com", "employee").await.unwrap();

        let linked = get_or_link_cloud_user(&db, HUB, "77", "Socia", "employee", Some("socia@bar.com"), Some("admin"))
            .await
            .unwrap();
        assert_eq!(linked.role, "admin");
        assert_eq!(linked.cloud_user_id.as_deref(), Some("77"), "queda enlazada");
        assert_eq!(
            list_login_users(&db, HUB).await.unwrap().len(),
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
        let user = get_or_link_cloud_user(&db, HUB, "42", "Ada", "bartender", None, None)
            .await
            .unwrap();
        assert_eq!(user.role, "bartender");

        let raised = get_or_link_cloud_user(&db, HUB, "42", "Ada", "bartender", None, Some("admin"))
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
        get_or_link_cloud_user(&db, HUB, "42", "Ada", "employee", None, None)
            .await
            .unwrap();

        let user = get_or_link_cloud_user(&db, HUB, "42", "Ada", "employee", None, Some("owner"))
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
        let first = get_or_link_cloud_user(&db, HUB, "42", "Ada", "cashier", None, None)
            .await
            .unwrap();

        for bogus in ["manager", "employee", "member", ""] {
            let user = get_or_link_cloud_user(&db, HUB, "42", "Ada", "cashier", None, Some(bogus))
                .await
                .unwrap();
            assert_eq!(user.role, "cashier", "`{bogus}` no es un suelo");
        }
        assert_eq!(stored_role(&db, &first.id).await, "cashier");
    }

    // ── Rule D (hub#348): revoking the membership SHUTS THE DOOR, and it stays shut ─────────────

    #[tokio::test]
    async fn revoking_the_membership_closes_every_local_door_at_once() {
        // Deactivating is not bookkeeping: it is what makes the revocation real. The open session,
        // the PIN and the pinpad entry all hang off `is_active`, and the sessions are deleted so a
        // future readmission cannot revive a token minted before the revocation (TTL 30 days).
        let db = fresh_db().await;
        ensure_identity_with_sessions(&db).await;
        let user = get_or_link_cloud_user(&db, HUB, "42", "Ada", "employee", Some("ada@bar.com"), None)
            .await
            .unwrap();
        set_pin(&db, HUB, &user.id, "1234").await.unwrap();
        let token = create_session(&db, HUB, &user.id, 3600, None).await.unwrap();
        assert!(resolve_session(&db, HUB, &token).await.unwrap().is_some());

        assert_eq!(
            revoke_cloud_access(&db, HUB, "42", Some("ada@bar.com")).await.unwrap(),
            1,
            "closes the one row of that cloud identity",
        );

        assert!(!stored_is_active(&db, &user.id).await, "the row is deactivated");
        assert!(
            resolve_session(&db, HUB, &token).await.unwrap().is_none(),
            "the session opened before the revocation is gone",
        );
        assert!(
            verify_pin(&db, HUB, "Ada", "1234").await.unwrap().is_none(),
            "the PIN is not a side door around the revocation",
        );
        assert!(
            list_pin_users(&db, HUB).await.unwrap().is_empty(),
            "and they disappear from the pinpad grid",
        );
        assert_eq!(
            session_rows(&db, &user.id).await,
            0,
            "the session rows are deleted, not merely invalidated by the JOIN",
        );
        assert_eq!(
            revoke_cloud_access(&db, HUB, "42", Some("ada@bar.com")).await.unwrap(),
            0,
            "idempotent: a second revocation touches nothing",
        );
    }

    #[tokio::test]
    async fn revoking_reaches_a_row_that_has_never_logged_in() {
        // The invited row (or the seeded owner) has no `cloud_user_id` yet: the SaaS can revoke an
        // invitation before it is ever used, and the email in the JWT is authenticated by the same
        // signature the presence gate trusts, so it is the key that finds them.
        let db = fresh_db().await;
        ensure_identity_email(&db).await;
        create_login_user(&db, HUB, "socia@bar.com", "admin").await.unwrap();

        assert_eq!(
            revoke_cloud_access(&db, HUB, "99", Some("socia@bar.com")).await.unwrap(),
            1,
        );
        assert!(!list_login_users(&db, HUB).await.unwrap()[0].is_active);
    }

    #[tokio::test]
    async fn a_revoked_row_is_reused_and_never_duplicated() {
        // The hole that made deactivating pointless: both lookups filtered `is_active = 1`, so the
        // closed row did not match and a SECOND one was provisioned beside it — active, with the
        // default role. Shutting the door has to survive the next login.
        let db = fresh_db().await;
        ensure_identity_email(&db).await;
        let user = get_or_link_cloud_user(&db, HUB, "42", "Ada", "manager", Some("ada@bar.com"), None)
            .await
            .unwrap();
        revoke_cloud_access(&db, HUB, "42", Some("ada@bar.com")).await.unwrap();

        let back = get_or_link_cloud_user(&db, HUB, "42", "Ada", "employee", Some("ada@bar.com"), None)
            .await
            .unwrap();
        assert_eq!(back.id, user.id, "the SAME row comes back, not a twin");
        assert_eq!(rows_with_email(&db, "ada@bar.com").await, 1);
    }

    #[tokio::test]
    async fn a_readmission_comes_back_at_the_role_the_membership_grants_today() {
        // Readmission is an admission, not an undo. Coming back must not resurrect a role the
        // current membership no longer justifies — and, with the floor of rule C, an account admin
        // still comes back as `admin` on the very same login.
        let db = fresh_db().await;
        ensure_identity_email(&db).await;
        get_or_link_cloud_user(&db, HUB, "42", "Ada", "manager", Some("ada@bar.com"), None)
            .await
            .unwrap();
        revoke_cloud_access(&db, HUB, "42", Some("ada@bar.com")).await.unwrap();

        let back = get_or_link_cloud_user(&db, HUB, "42", "Ada", "employee", Some("ada@bar.com"), None)
            .await
            .unwrap();
        assert!(back.is_active, "the membership reopens the door it closed");
        assert_eq!(back.role, "employee", "`manager` is NOT resurrected");
        assert_eq!(stored_role(&db, &back.id).await, "employee");

        revoke_cloud_access(&db, HUB, "42", Some("ada@bar.com")).await.unwrap();
        let as_admin =
            get_or_link_cloud_user(&db, HUB, "42", "Ada", "admin", Some("ada@bar.com"), Some("admin"))
                .await
                .unwrap();
        assert_eq!(as_admin.role, "admin", "the floor of rule C applies on readmission too");
    }

    #[tokio::test]
    async fn a_baja_decided_by_the_hub_is_never_undone_by_a_token() {
        // The other authority that shuts a door: the hub's own admin (ADR-0157 §7 / Personal). A
        // membership must not reopen it — `remove_member` keeps the local baja even when the call
        // to the SaaS fails, so the mirror can lag, and "still a member in the SaaS" would then
        // walk somebody the hub threw out straight back in.
        let db = fresh_db().await;
        ensure_identity_email(&db).await;
        let user = create_login_user(&db, HUB, "ana@bar.com", "manager").await.unwrap();
        assert!(deactivate_login_user(&db, HUB, "ana@bar.com").await.unwrap());

        let err = get_or_link_cloud_user(&db, HUB, "42", "Ana", "employee", Some("ana@bar.com"), None)
            .await
            .unwrap_err();
        match err {
            crate::errors::RuntimeError::Domain { code, .. } => {
                assert_eq!(code, DEACTIVATED_ERROR_CODE, "a stable code, never a silent pass");
            }
            other => panic!("expected a domain rejection, got {other:?}"),
        }
        assert_eq!(rows_with_email(&db, "ana@bar.com").await, 1, "and nothing is provisioned");
        assert!(!stored_is_active(&db, &user.id).await, "the row stays closed");
        assert_eq!(
            linked_cloud_user_id(&db, &user.id).await,
            None,
            "a rejected login does not leave the row linked to the account it just refused",
        );
    }

    #[tokio::test]
    async fn reactivating_clears_the_cloud_revocation_mark() {
        // Otherwise the mark outlives its episode: the admin readmits somebody the SaaS had
        // revoked, later shows them the door themselves, and a stale `cloud_revoked_at` would let
        // the next login walk back in. Both alta paths (re-invitation and Personal) clear it.
        let db = fresh_db().await;
        ensure_identity_email(&db).await;
        get_or_link_cloud_user(&db, HUB, "42", "Ada", "employee", Some("ada@bar.com"), None)
            .await
            .unwrap();
        revoke_cloud_access(&db, HUB, "42", Some("ada@bar.com")).await.unwrap();

        create_login_user(&db, HUB, "ada@bar.com", "employee").await.unwrap();
        assert!(deactivate_login_user(&db, HUB, "ada@bar.com").await.unwrap());

        let err = get_or_link_cloud_user(&db, HUB, "42", "Ada", "employee", Some("ada@bar.com"), None)
            .await
            .unwrap_err();
        assert!(
            matches!(err, crate::errors::RuntimeError::Domain { ref code, .. } if code == DEACTIVATED_ERROR_CODE),
            "the hub's baja wins: the old cloud mark must not reopen the door",
        );
    }

    /// Cuántas sesiones tiene abiertas un usuario.
    async fn session_rows(db: &PgAdapter, user_id: &str) -> usize {
        let mut p = Params::new();
        p.insert("id".into(), json!(user_id));
        db.query("SELECT token FROM hub_session WHERE user_id = :id", &p)
            .await
            .unwrap()
            .rows
            .len()
    }

    /// `cloud_user_id` de una fila (o `None` si sigue sin enlazar).
    async fn linked_cloud_user_id(db: &PgAdapter, id: &str) -> Option<String> {
        let mut p = Params::new();
        p.insert("id".into(), json!(id));
        let res = db
            .query("SELECT cloud_user_id FROM hub_user WHERE id = :id", &p)
            .await
            .unwrap();
        res.rows
            .first()
            .and_then(|r| r["cloud_user_id"].as_str().map(|s| s.to_string()))
    }

    #[tokio::test]
    async fn create_login_user_upserts_by_email_and_deactivate_is_symmetric() {
        // ADR-0157 §7: alta/baja de usuarios-login por email (flujo admin). Alta = upsert por email
        // (crea o reactiva+re-rol); baja = desactiva (simétrica, idempotente).
        let db = fresh_db().await;
        ensure_identity_email(&db).await;

        // Alta nueva.
        let u = create_login_user(&db, HUB, "ana@bar.com", "manager").await.unwrap();
        assert_eq!(u.role, "manager");
        assert!(u.cloud_user_id.is_none(), "aún sin login → sin cloud_user_id");
        assert!(u.is_active);

        // Re-alta (mismo email, rol nuevo) = upsert: misma fila, rol actualizado.
        let u2 = create_login_user(&db, HUB, "ana@bar.com", "admin").await.unwrap();
        assert_eq!(u2.id, u.id, "reusa la fila del email (no duplica)");
        assert_eq!(u2.role, "admin", "actualiza el rol");
        assert_eq!(list_login_users(&db, HUB).await.unwrap().len(), 1);

        // Baja: desactiva (true la primera vez, false si ya estaba inactiva = idempotente).
        assert!(deactivate_login_user(&db, HUB, "ana@bar.com").await.unwrap());
        assert!(!deactivate_login_user(&db, HUB, "ana@bar.com").await.unwrap());
        let listed = list_login_users(&db, HUB).await.unwrap();
        assert_eq!(listed.len(), 1, "sigue listada (audit), pero inactiva");
        assert!(!listed[0].is_active);

        // Re-alta reactiva la misma fila.
        let u3 = create_login_user(&db, HUB, "ana@bar.com", "employee").await.unwrap();
        assert_eq!(u3.id, u.id);
        assert!(u3.is_active, "el alta reactiva");
        assert_eq!(u3.role, "employee");
    }

    /// **The baseline never indexes a column its `CREATE TABLE` may not have created** (hub#885).
    ///
    /// [`ensure_tables`] runs on every boot, *before* the migration engine, so it meets databases it
    /// did not create. A `CREATE TABLE IF NOT EXISTS` is a **no-op** on a table that is already
    /// there — it does not add the columns the new definition lists — so on a hub deployed before
    /// hub#497 `hub_user` still has no `hub_id`, and an index over it dies 42703 (`indexcmds.c` /
    /// `ComputeIndexAttrs`). The migration that adds the column (v42) runs afterwards and never gets
    /// its turn: the process exits 1 and Swarm rolls the whole update back.
    ///
    /// The column and the two indexes that need it belong to v42, which creates them right after the
    /// `ALTER`. Here we only assert the baseline **survives** the old shape, which is the invariant
    /// the boot path depends on. The end-to-end proof that the upgrade lands is
    /// `tests/boot_over_pre_hub_scoped_identity.rs`.
    #[tokio::test]
    async fn the_baseline_survives_a_table_that_predates_hub_id() {
        let db = fresh_db().await;
        // A `hub_user`/`hub_session` exactly as a hub deployed before hub#497 carries them.
        db.execute_batch(
            "CREATE TABLE hub_user (\
               id TEXT PRIMARY KEY, name TEXT NOT NULL, pin_hash TEXT NOT NULL DEFAULT '', \
               role TEXT NOT NULL DEFAULT '', cloud_user_id TEXT, \
               is_active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL);\
             CREATE TABLE hub_session (\
               token TEXT PRIMARY KEY, user_id TEXT NOT NULL, created_at TEXT NOT NULL, \
               expires_at TEXT NOT NULL);",
        )
        .await
        .unwrap();

        ensure_tables(&db).await.expect(
            "el baseline no puede indexar `hub_id` en una tabla que ya existía sin esa columna: \
             su `CREATE TABLE IF NOT EXISTS` no la añade (hub#885)",
        );
    }

    #[tokio::test]
    async fn new_pins_are_argon2id() {
        // create_user/set_pin escriben siempre argon2id (string PHC `$argon2id$...`).
        let db = fresh_db().await;
        ensure_tables(&db).await.unwrap();
        create_user(&db, HUB, "Eva", "1111", "cashier", None)
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
        let ok = verify_pin(&db, HUB, "Eva", "1111").await.unwrap();
        assert!(ok.is_some());
        assert!(verify_pin(&db, HUB, "Eva", "2222").await.unwrap().is_none());
    }

    #[tokio::test]
    async fn device_trust_gate() {
        let db = fresh_db().await;
        ensure_tables(&db).await.unwrap();
        // La tabla la crean las migraciones de sistema v2 + v23 (que le añade el `hub_id` y
        // recompone la PK, hub#489) + v44 (`name`, hub#494); en el test la creamos a mano ya en su
        // forma final.
        db.execute_batch(
            "CREATE TABLE hub_trusted_device (hub_id TEXT NOT NULL, device_id TEXT NOT NULL, \
              label TEXT NOT NULL DEFAULT '', name TEXT NOT NULL DEFAULT '', \
              trusted_at TEXT NOT NULL, PRIMARY KEY (hub_id, device_id));",
        )
        .await
        .unwrap();

        assert!(
            !is_device_trusted(&db, "hub-1", "dev-1").await.unwrap(),
            "desconocido = no confianza"
        );
        trust_device(&db, "hub-1", "dev-1", "Caja 1", "Chrome · Android")
            .await
            .unwrap();
        assert!(
            is_device_trusted(&db, "hub-1", "dev-1").await.unwrap(),
            "marcado = de confianza"
        );
        // Idempotente (re-marcar no falla).
        trust_device(&db, "hub-1", "dev-1", "Caja 1 (renombrada)", "Safari · iPad")
            .await
            .unwrap();
        assert!(is_device_trusted(&db, "hub-1", "dev-1").await.unwrap());
        // Y el nombre con el que NACIÓ sigue ahí: el `DO UPDATE` toca `label` y nada más (hub#494).
        // Un segundo login que lo reescribiera devolvería la fila a una etiqueta que nadie eligió.
        let row = db
            .query(
                "SELECT name, label FROM hub_trusted_device WHERE hub_id = 'hub-1' AND device_id = 'dev-1'",
                &Params::new(),
            )
            .await
            .unwrap();
        assert_eq!(row.rows[0]["name"], json!("Chrome · Android"));
        assert_eq!(row.rows[0]["label"], json!("Caja 1 (renombrada)"));
        // Y es confianza de ESTE hub: el de al lado, sobre la misma BD, no la hereda (hub#489).
        assert!(
            !is_device_trusted(&db, "hub-2", "dev-1").await.unwrap(),
            "la confianza es de un hub, no de la base de datos"
        );
        // Revocar lo quita.
        untrust_device(&db, "hub-1", "dev-1").await.unwrap();
        assert!(!is_device_trusted(&db, "hub-1", "dev-1").await.unwrap());
    }
}
