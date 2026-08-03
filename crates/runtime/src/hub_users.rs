//! **Personal = core.** Gestión de los usuarios del hub (`hub_user`) para la pantalla de Personal.
//!
//! La identidad del hub ya es del core (`identity.rs`, §2.9): `hub_user` + `hub_session` + los
//! permisos del rol. Lo que faltaba era la cara de gestión — *listar todos* los usuarios, darlos de
//! alta, editarlos y darlos de baja — que hasta ahora se pedía al **módulo `staff`**. Eso era un
//! error de dependencia: `staff` es un módulo de negocio (profesional reservable, comisiones,
//! horarios) con su propia navegación, así que en un hub sin él la pantalla salía vacía con «No se
//! pudo cargar el personal», y el owner/administrador —que entra por Cloud y **no tiene PIN**— no
//! aparecía por ninguna parte (la única lista era `pin_users`, solo los que tienen PIN).
//!
//! Contrato de esta capa:
//!  - [`list`] devuelve **todos** los usuarios de la BD del hub, activos e inactivos, con PIN o sin
//!    él, con su email del perfil (`hub_user_profile`).
//!  - La baja es **desactivar** (`is_active = 0`), nunca borrar: las sesiones, la auditoría
//!    (`created_by`/`updated_by`) y el historial de ventas apuntan a ese id.
//!  - Los **roles** son del core: catálogo base ([`BASE_ROLES`]) ∪ los roles que declaran los
//!    módulos activos (`role_permissions`) ∪ los que ya usa algún usuario.
use std::collections::BTreeSet;

use erplora_db::{DatabaseAdapter, Params};
use serde::{Deserialize, Serialize};
use serde_json::json;

use crate::errors::{Result, RuntimeError};
use crate::identity;
use crate::registry::{now_rfc3339, Registry};
use crate::user_profile;

/// **Namespace reservado del core** en el dispatcher (ADR-0188). Ningún módulo puede registrar
/// queries bajo `hub.`: el instalador rechaza un módulo con ese id y el dispatcher resuelve el
/// prefijo antes de mirar el registry.
pub const CORE_NAMESPACE: &str = "hub.";

/// Permiso que abre las queries `hub.*`. Lo tiene **cualquier rol local** ([`permissions_for_role`]
/// lo añade siempre): el nombre y el rol de la plantilla ya son públicos en el grid de PIN del
/// login, así que no revela nada nuevo. Una **API key** no lo tiene — sus permisos salen del scope
/// de módulos que le dio el admin, y un tercero no lista el personal.
pub const VIEW_USERS_PERMISSION: &str = "hub.users.view";

/// Queries del core disponibles en el dispatcher (`hub.<algo>`).
const CORE_QUERIES: &[&str] = &["users.list", "roles.list"];

/// Roles que el core conoce siempre, aunque no haya ningún módulo instalado. `owner`/`admin` son
/// además los que abren el gate de administración del Hub (`is_admin_role`, server); `manager` y
/// `employee` son los que declaran los `role_permissions` de los módulos.
pub const BASE_ROLES: &[&str] = &["owner", "admin", "manager", "employee"];

/// Longitud válida de un PIN local (dígitos). El login es un pinpad numérico.
const PIN_LEN: std::ops::RangeInclusive<usize> = 4..=8;

/// Un usuario del hub tal y como lo pinta la pantalla de Personal.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct HubUserRow {
    pub id: String,
    pub name: String,
    /// Email del perfil (`hub_user_profile`); vacío si el usuario aún no tiene perfil.
    pub email: String,
    pub role: String,
    /// Id del usuario en el Cloud si la identidad está vinculada al portal (owner/admin), o `None`
    /// para el personal **solo-local** (§2.9).
    pub cloud_user_id: Option<String>,
    pub is_active: bool,
    /// `true` si puede entrar con PIN local. El owner suele entrar por Cloud, así que es `false`.
    pub has_pin: bool,
    pub created_at: String,
}

/// Un rol del hub con lo que concede y cuánta gente lo tiene.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct HubRole {
    pub name: String,
    /// Permisos efectivos = unión de `role_permissions[rol]` de los módulos **activos**.
    pub permissions: usize,
    /// Usuarios **activos** con este rol.
    pub members: usize,
}

/// Alta de un usuario del hub. `pin` vacío = sin PIN (entra por Cloud), `email` vacío = sin perfil.
#[derive(Debug, Clone, Default, Deserialize)]
pub struct NewHubUser {
    #[serde(default)]
    pub name: String,
    #[serde(default)]
    pub email: String,
    #[serde(default)]
    pub role: String,
    #[serde(default)]
    pub pin: String,
}

/// Edición parcial: solo se toca lo que viene. `pin: Some("")` **retira** el PIN;
/// `is_active: Some(false)` es la baja.
#[derive(Debug, Clone, Default, Deserialize)]
pub struct UpdateHubUser {
    pub name: Option<String>,
    pub email: Option<String>,
    pub role: Option<String>,
    pub is_active: Option<bool>,
    pub pin: Option<String>,
}

fn invalid(detail: impl Into<String>) -> RuntimeError {
    RuntimeError::InvalidPayload {
        name: "hub.users".into(),
        detail: detail.into(),
    }
}

/// Nombre visible: obligatorio y acotado (el mismo límite que el perfil).
fn clean_name(value: &str) -> Result<String> {
    let name = value.trim();
    if name.is_empty() {
        return Err(invalid("el nombre es obligatorio"));
    }
    if name.chars().count() > 150 {
        return Err(invalid("el nombre supera 150 caracteres"));
    }
    Ok(name.to_string())
}

/// Rol: obligatorio. NO se valida contra un catálogo cerrado — un módulo puede declarar roles
/// propios en `role_permissions` y el hub debe poder asignarlos.
fn clean_role(value: &str) -> Result<String> {
    let role = value.trim();
    if role.is_empty() {
        return Err(invalid("el rol es obligatorio"));
    }
    if role.chars().count() > 50 {
        return Err(invalid("el rol supera 50 caracteres"));
    }
    Ok(role.to_string())
}

/// PIN: vacío (sin PIN) o entre 4 y 8 **dígitos** — lo que acepta el pinpad del login.
fn clean_pin(value: &str) -> Result<String> {
    let pin = value.trim();
    if pin.is_empty() {
        return Ok(String::new());
    }
    if !pin.chars().all(|c| c.is_ascii_digit()) || !PIN_LEN.contains(&pin.chars().count()) {
        return Err(invalid("el PIN debe tener entre 4 y 8 dígitos"));
    }
    Ok(pin.to_string())
}

/// Email: vacío u opcional con forma mínima válida (misma regla que el perfil propio).
fn clean_email(value: &str) -> Result<String> {
    let email = value.trim();
    if email.is_empty() {
        return Ok(String::new());
    }
    if email.chars().count() > 254
        || !email.contains('@')
        || email.starts_with('@')
        || email.ends_with('@')
    {
        return Err(invalid("email no válido"));
    }
    Ok(email.to_string())
}

/// Parte el nombre visible en nombre/apellidos para el perfil (misma convención que `user_profile`).
fn split_name(name: &str) -> (String, String) {
    let mut parts = name.splitn(2, char::is_whitespace);
    (
        parts.next().unwrap_or_default().to_string(),
        parts.next().unwrap_or_default().trim().to_string(),
    )
}

/// Rechaza dos usuarios **activos** con el mismo nombre: el login por PIN resuelve por nombre
/// (`identity::verify_pin`), así que un duplicado haría ambiguo quién entra.
async fn ensure_name_is_free(
    db: &dyn DatabaseAdapter,
    name: &str,
    excluding_id: Option<&str>,
) -> Result<()> {
    let mut p = Params::new();
    p.insert("name".into(), json!(name));
    p.insert("id".into(), json!(excluding_id.unwrap_or_default()));
    let res = db
        .query(
            "SELECT id FROM hub_user WHERE name = :name AND is_active = 1 AND id != :id",
            &p,
        )
        .await?;
    if res.rows.is_empty() {
        Ok(())
    } else {
        Err(invalid(format!("ya hay un usuario activo llamado «{name}»")))
    }
}

/// Todos los usuarios del hub, activos primero y por nombre. Incluye al owner cloud (sin PIN) y a
/// los desactivados (marcados `is_active = false`) — la pantalla de Personal los muestra todos.
pub async fn list(db: &dyn DatabaseAdapter, hub_id: &str) -> Result<Vec<HubUserRow>> {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    let res = db
        .query(
            "SELECT u.id AS id, u.name AS name, u.role AS role, u.cloud_user_id AS cloud_user_id, \
                    u.is_active AS is_active, u.created_at AS created_at, \
                    CASE WHEN u.pin_hash IS NULL OR u.pin_hash = '' THEN 0 ELSE 1 END AS has_pin, \
                    p.email AS email \
               FROM hub_user u \
               LEFT JOIN hub_user_profile p ON p.user_id = u.id AND p.hub_id = :hub_id \
              ORDER BY u.is_active DESC, u.name",
            &p,
        )
        .await?;
    Ok(res
        .rows
        .iter()
        .map(|r| HubUserRow {
            id: r["id"].as_str().unwrap_or_default().to_string(),
            name: r["name"].as_str().unwrap_or_default().to_string(),
            email: r["email"].as_str().unwrap_or_default().to_string(),
            role: r["role"].as_str().unwrap_or_default().to_string(),
            cloud_user_id: r["cloud_user_id"].as_str().map(ToString::to_string),
            is_active: truthy(&r["is_active"]),
            has_pin: truthy(&r["has_pin"]),
            created_at: r["created_at"].as_str().unwrap_or_default().to_string(),
        })
        .collect())
}

/// SQLite devuelve enteros donde Postgres puede devolver booleanos: acepta ambos.
fn truthy(value: &serde_json::Value) -> bool {
    value.as_bool().unwrap_or_else(|| value.as_i64().unwrap_or(0) != 0)
}

/// Un usuario por id (cualquier estado). `None` si no existe en este hub.
pub async fn get(db: &dyn DatabaseAdapter, hub_id: &str, user_id: &str) -> Result<Option<HubUserRow>> {
    Ok(list(db, hub_id).await?.into_iter().find(|u| u.id == user_id))
}

/// Alta de usuario: valida, crea la identidad (con PIN si lo trae) y guarda su email en el perfil.
pub async fn create(db: &dyn DatabaseAdapter, hub_id: &str, input: &NewHubUser) -> Result<String> {
    let name = clean_name(&input.name)?;
    let role = clean_role(&input.role)?;
    let pin = clean_pin(&input.pin)?;
    let email = clean_email(&input.email)?;
    ensure_name_is_free(db, &name, None).await?;

    let id = identity::create_user(db, &name, &pin, &role, None).await?;
    if !email.is_empty() {
        let (first, last) = split_name(&name);
        user_profile::set_identity(db, hub_id, &id, &first, &last, &email).await?;
    }
    Ok(id)
}

/// Edición parcial de un usuario existente. Devuelve la fila resultante.
pub async fn update(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    user_id: &str,
    input: &UpdateHubUser,
) -> Result<HubUserRow> {
    let current = get(db, hub_id, user_id)
        .await?
        .ok_or_else(|| RuntimeError::Other("usuario no encontrado".into()))?;

    let name = match &input.name {
        Some(value) => clean_name(value)?,
        None => current.name.clone(),
    };
    let role = match &input.role {
        Some(value) => clean_role(value)?,
        None => current.role.clone(),
    };
    let email = match &input.email {
        Some(value) => Some(clean_email(value)?),
        None => None,
    };
    let pin = match &input.pin {
        Some(value) => Some(clean_pin(value)?),
        None => None,
    };
    let is_active = input.is_active.unwrap_or(current.is_active);
    if is_active && name != current.name {
        ensure_name_is_free(db, &name, Some(user_id)).await?;
    }

    let mut p = Params::new();
    p.insert("id".into(), json!(user_id));
    p.insert("name".into(), json!(name));
    p.insert("role".into(), json!(role));
    p.insert("is_active".into(), json!(i64::from(is_active)));
    db.execute(
        "UPDATE hub_user SET name = :name, role = :role, is_active = :is_active WHERE id = :id",
        &p,
    )
    .await?;

    if let Some(email) = email {
        let (first, last) = split_name(&name);
        user_profile::set_identity(db, hub_id, user_id, &first, &last, &email).await?;
    }
    if let Some(pin) = pin {
        identity::set_pin(db, user_id, &pin).await?;
    }
    // Desactivar cierra sus sesiones abiertas: la baja tiene que ser inmediata, no esperar al TTL.
    if !is_active {
        let mut p = Params::new();
        p.insert("id".into(), json!(user_id));
        db.execute("DELETE FROM hub_session WHERE user_id = :id", &p)
            .await?;
    }

    get(db, hub_id, user_id)
        .await?
        .ok_or_else(|| RuntimeError::Other("usuario no encontrado".into()))
}

/// Roles del hub: catálogo base ∪ roles de los módulos activos ∪ roles en uso, con sus permisos
/// efectivos y sus miembros activos.
pub async fn list_roles(db: &dyn DatabaseAdapter, registry: &Registry) -> Result<Vec<HubRole>> {
    let res = db
        .query(
            "SELECT role, COUNT(*) AS members FROM hub_user WHERE is_active = 1 GROUP BY role",
            &Params::new(),
        )
        .await?;
    let mut members: std::collections::HashMap<String, usize> = std::collections::HashMap::new();
    for row in &res.rows {
        let role = row["role"].as_str().unwrap_or_default().trim().to_string();
        if !role.is_empty() {
            members.insert(role, row["members"].as_i64().unwrap_or(0).max(0) as usize);
        }
    }

    // Los del catálogo base van primero y en su orden; el resto, alfabético y sin duplicar.
    let mut extra: BTreeSet<String> = members.keys().cloned().collect();
    for module in &registry.installed {
        if registry.is_active(&module.id) {
            extra.extend(module.role_permissions.keys().cloned());
        }
    }
    let mut names: Vec<String> = BASE_ROLES.iter().map(|r| (*r).to_string()).collect();
    let rest: Vec<String> = extra
        .into_iter()
        .filter(|role| !names.contains(role))
        .collect();
    names.extend(rest);

    Ok(names
        .into_iter()
        .map(|name| HubRole {
            permissions: identity::permissions_for_role(registry, &name).len(),
            members: members.get(&name).copied().unwrap_or(0),
            name,
        })
        .collect())
}

/// Despacha una query del namespace reservado `hub.` (ADR-0188). `rest` es el nombre sin prefijo.
///
/// Lo que ve un módulo es **menos** que lo que ve la pantalla de Personal: id, nombre, rol y estado
/// — lo justo para vincular su ficha a una persona (p. ej. `staff_member.user_id`). **Sin email ni
/// vía de acceso**: eso es dato del core y no hay motivo para dárselo a un módulo de terceros.
pub async fn core_query(
    db: &dyn DatabaseAdapter,
    registry: &Registry,
    hub_id: &str,
    name: &str,
    rest: &str,
    ctx: &crate::registry::RequestContext,
) -> Result<Vec<serde_json::Value>> {
    if !CORE_QUERIES.contains(&rest) {
        // NO es `ModuleNotInstalled`: `hub` no es un módulo ausente, es el core. Un nombre que no
        // existe aquí es un contrato roto y debe explotar (no lo perdona `queryOptional`).
        return Err(RuntimeError::QueryNotFound(name.to_string()));
    }
    crate::permissions::check(ctx, VIEW_USERS_PERMISSION)?;
    match rest {
        "users.list" => Ok(list(db, hub_id)
            .await?
            .into_iter()
            .map(|u| {
                json!({
                    "id": u.id,
                    "name": u.name,
                    "role": u.role,
                    "is_active": u.is_active,
                })
            })
            .collect()),
        // Los roles no son PII: se devuelven enteros (nombre, permisos, miembros).
        _ => Ok(list_roles(db, registry)
            .await?
            .into_iter()
            .map(|r| json!({ "name": r.name, "permissions": r.permissions, "members": r.members }))
            .collect()),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use erplora_db::SqliteAdapter;

    async fn db() -> SqliteAdapter {
        let db = SqliteAdapter::open_in_memory().await.unwrap();
        identity::ensure_tables(&db).await.unwrap();
        db
    }

    #[test]
    fn validates_name_role_pin_and_email() {
        assert!(clean_name("  ").is_err());
        assert_eq!(clean_name("  Ana  ").unwrap(), "Ana");
        assert!(clean_role("").is_err());
        assert_eq!(clean_pin("").unwrap(), "");
        assert_eq!(clean_pin("1234").unwrap(), "1234");
        assert!(clean_pin("12").is_err(), "menos de 4 dígitos");
        assert!(clean_pin("123456789").is_err(), "más de 8 dígitos");
        assert!(clean_pin("12ab").is_err(), "solo dígitos");
        assert_eq!(clean_email("").unwrap(), "");
        assert!(clean_email("ana@example.com").is_ok());
        assert!(clean_email("ana.example.com").is_err());
        assert!(clean_email("@example.com").is_err());
    }

    #[test]
    fn splits_the_visible_name_into_first_and_last() {
        assert_eq!(split_name("Ana"), ("Ana".into(), String::new()));
        assert_eq!(
            split_name("Marta Ruiz Gil"),
            ("Marta".into(), "Ruiz Gil".into())
        );
    }

    #[tokio::test]
    async fn rejects_two_active_users_with_the_same_name() {
        let db = db().await;
        identity::create_user(&db, "Marta", "1234", "cashier", None)
            .await
            .unwrap();
        let err = ensure_name_is_free(&db, "Marta", None).await.unwrap_err();
        assert!(err.to_string().contains("Marta"), "{err}");
        // Editarse a uno mismo con el mismo nombre no choca consigo mismo.
        let id = identity::create_user(&db, "Luis", "2222", "cashier", None)
            .await
            .unwrap();
        ensure_name_is_free(&db, "Luis", Some(&id)).await.unwrap();
    }

    #[test]
    fn truthy_accepts_sqlite_integers_and_postgres_booleans() {
        assert!(truthy(&json!(1)));
        assert!(!truthy(&json!(0)));
        assert!(truthy(&json!(true)));
        assert!(!truthy(&json!(null)));
    }
}
