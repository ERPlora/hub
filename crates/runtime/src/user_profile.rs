//! Perfil y preferencias personales del usuario del Hub.
//!
//! Las filas están aisladas por `(hub_id, user_id)`. Un string vacío en una preferencia significa
//! «sin override»: el shell debe heredar el valor global del Hub. La capa HTTP nunca acepta un
//! `user_id` del cliente; lo resuelve desde la sesión, por lo que un usuario solo edita sus datos.

use erplora_db::{DatabaseAdapter, Params};
use serde::{Deserialize, Serialize};
use serde_json::json;

use crate::errors::{Result, RuntimeError};
use crate::registry::now_rfc3339;

const LANGUAGES: &[&str] = &["es", "en"];
const MODES: &[&str] = &["system", "light", "dark"];
const PALETTES: &[&str] = &[
    "erplora",
    "terracotta",
    "corporate",
    "minimal",
    "forest",
    "ocean",
    "violet",
];

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, Default)]
pub struct UserPreferences {
    pub language: Option<String>,
    pub theme_mode: Option<String>,
    pub theme_palette: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct UserProfile {
    pub id: String,
    pub name: String,
    pub first_name: String,
    pub last_name: String,
    pub email: String,
    pub role: String,
    pub cloud_user_id: Option<String>,
    pub avatar_path: Option<String>,
    pub preferences: UserPreferences,
    /// `true` si hoy hay un PIN utilizable (hub#1430): «Mi perfil» lo usa para decidir entre
    /// «cambiar mi PIN» (pide el actual) y «establecer un PIN» (cuenta cloud-only, nada que
    /// confirmar todavía) — espejo del `has_pin` que ya pinta Personal.
    pub has_pin: bool,
}

#[derive(Debug, Clone, Deserialize)]
pub struct UpdateUserProfile {
    #[serde(default)]
    pub first_name: String,
    #[serde(default)]
    pub last_name: String,
    #[serde(default)]
    pub email: String,
    #[serde(default)]
    pub preferences: UserPreferences,
}

fn clean_text(value: &str, field: &str, max: usize) -> Result<String> {
    let cleaned = value.trim();
    if cleaned.chars().count() > max {
        return Err(RuntimeError::InvalidPayload {
            name: "user.profile.update".into(),
            detail: format!("{field} supera {max} caracteres"),
        });
    }
    Ok(cleaned.to_string())
}

fn validate_optional(value: &Option<String>, allowed: &[&str], field: &str) -> Result<String> {
    let Some(raw) = value else {
        return Ok(String::new());
    };
    let normalized = raw.trim().to_ascii_lowercase();
    if allowed.contains(&normalized.as_str()) {
        Ok(normalized)
    } else {
        Err(RuntimeError::InvalidField {
            name: "user.profile.update".into(),
            field: field.into(),
            reason: "unknown".into(),
            detail: format!("`{raw}` is not an accepted {field}: expected one of {allowed:?}"),
        })
    }
}

fn optional(value: &serde_json::Value) -> Option<String> {
    value
        .as_str()
        .filter(|s| !s.is_empty())
        .map(ToString::to_string)
}

/// Lee el perfil. Si aún no hay fila personal, devuelve la identidad base de `hub_user` y
/// preferencias vacías (herencia del Hub), sin fabricar un override.
pub async fn get(db: &dyn DatabaseAdapter, hub_id: &str, user_id: &str) -> Result<UserProfile> {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("user_id".into(), json!(user_id));
    let users = db
        .query(
            "SELECT id, name, role, cloud_user_id, pin_hash FROM hub_user \
              WHERE hub_id = :hub_id AND id = :user_id AND is_active = 1",
            &p,
        )
        .await?;
    let user = users
        .rows
        .first()
        .ok_or_else(|| RuntimeError::Other("usuario no encontrado".into()))?;

    let profile_rows = db
        .query(
            "SELECT first_name, last_name, email, avatar_path FROM hub_user_profile \
             WHERE hub_id = :hub_id AND user_id = :user_id",
            &p,
        )
        .await?;
    let pref_rows = db
        .query(
            "SELECT language, theme_mode, theme_palette FROM hub_user_pref \
             WHERE hub_id = :hub_id AND user_id = :user_id",
            &p,
        )
        .await?;

    let base_name = user["name"].as_str().unwrap_or_default();
    let mut inferred = base_name.splitn(2, char::is_whitespace);
    let inferred_first = inferred.next().unwrap_or_default();
    let inferred_last = inferred.next().unwrap_or_default();
    let profile = profile_rows.rows.first();
    let prefs = pref_rows.rows.first();

    let first_name = profile
        .and_then(|r| r["first_name"].as_str())
        .filter(|s| !s.is_empty())
        .unwrap_or(inferred_first)
        .to_string();
    let last_name = profile
        .and_then(|r| r["last_name"].as_str())
        .filter(|s| !s.is_empty())
        .unwrap_or(inferred_last)
        .to_string();

    Ok(UserProfile {
        id: user_id.to_string(),
        name: [first_name.as_str(), last_name.as_str()]
            .into_iter()
            .filter(|s| !s.is_empty())
            .collect::<Vec<_>>()
            .join(" "),
        first_name,
        last_name,
        email: profile
            .and_then(|r| r["email"].as_str())
            .unwrap_or_default()
            .to_string(),
        role: user["role"].as_str().unwrap_or_default().to_string(),
        cloud_user_id: user["cloud_user_id"].as_str().map(ToString::to_string),
        has_pin: user["pin_hash"].as_str().is_some_and(|h| !h.is_empty()),
        avatar_path: profile.and_then(|r| optional(&r["avatar_path"])),
        preferences: UserPreferences {
            language: prefs.and_then(|r| optional(&r["language"])),
            theme_mode: prefs.and_then(|r| optional(&r["theme_mode"])),
            theme_palette: prefs.and_then(|r| optional(&r["theme_palette"])),
        },
    })
}

/// Reemplaza los datos editables y las tres preferencias. `None` en una preferencia elimina el
/// override y reactiva la herencia del Hub.
pub async fn update(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    user_id: &str,
    input: &UpdateUserProfile,
) -> Result<UserProfile> {
    let first_name = clean_text(&input.first_name, "first_name", 150)?;
    let last_name = clean_text(&input.last_name, "last_name", 150)?;
    let email = clean_text(&input.email, "email", 254)?;
    if !email.is_empty() && (!email.contains('@') || email.starts_with('@') || email.ends_with('@'))
    {
        return Err(RuntimeError::InvalidPayload {
            name: "user.profile.update".into(),
            detail: "email no válido".into(),
        });
    }
    let language = validate_optional(&input.preferences.language, LANGUAGES, "language")?;
    let theme_mode = validate_optional(&input.preferences.theme_mode, MODES, "theme_mode")?;
    let theme_palette =
        validate_optional(&input.preferences.theme_palette, PALETTES, "theme_palette")?;
    let name = [first_name.as_str(), last_name.as_str()]
        .into_iter()
        .filter(|s| !s.is_empty())
        .collect::<Vec<_>>()
        .join(" ");
    let now = now_rfc3339();

    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("user_id".into(), json!(user_id));
    p.insert("first_name".into(), json!(first_name));
    p.insert("last_name".into(), json!(last_name));
    p.insert("email".into(), json!(email));
    p.insert("name".into(), json!(name.clone()));
    p.insert("language".into(), json!(language));
    p.insert("theme_mode".into(), json!(theme_mode));
    p.insert("theme_palette".into(), json!(theme_palette));
    p.insert("now".into(), json!(now));

    let mut ops = vec![
        (
            "INSERT INTO hub_user_profile \
             (hub_id, user_id, first_name, last_name, email, avatar_path, updated_at) \
             VALUES (:hub_id, :user_id, :first_name, :last_name, :email, '', :now) \
             ON CONFLICT (hub_id, user_id) DO UPDATE SET first_name = :first_name, \
             last_name = :last_name, email = :email, updated_at = :now"
                .to_string(),
            p.clone(),
        ),
        (
            "INSERT INTO hub_user_pref \
             (hub_id, user_id, language, theme_mode, theme_palette, updated_at) \
             VALUES (:hub_id, :user_id, :language, :theme_mode, :theme_palette, :now) \
             ON CONFLICT (hub_id, user_id) DO UPDATE SET language = :language, \
             theme_mode = :theme_mode, theme_palette = :theme_palette, updated_at = :now"
                .to_string(),
            p.clone(),
        ),
    ];
    if !name.is_empty() {
        ops.push((
            "UPDATE hub_user SET name = :name WHERE hub_id = :hub_id AND id = :user_id".to_string(),
            p,
        ));
    }
    db.execute_tx(&ops).await?;
    get(db, hub_id, user_id).await
}

/// Upsert de la **identidad** del perfil (nombre, apellidos, email) SIN tocar preferencias ni
/// avatar. Es la vía de la gestión de Personal (`hub_users`), donde un admin edita a **otra**
/// persona: [`update`] es self-service y reemplaza también las preferencias, que no son suyas.
/// No escribe `hub_user.name` — de eso se encarga quien gestiona la identidad.
pub async fn set_identity(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    user_id: &str,
    first_name: &str,
    last_name: &str,
    email: &str,
) -> Result<()> {
    let first_name = clean_text(first_name, "first_name", 150)?;
    let last_name = clean_text(last_name, "last_name", 150)?;
    let email = clean_text(email, "email", 254)?;
    if !email.is_empty() && (!email.contains('@') || email.starts_with('@') || email.ends_with('@'))
    {
        return Err(RuntimeError::InvalidPayload {
            name: "user.profile.update".into(),
            detail: "email no válido".into(),
        });
    }
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("user_id".into(), json!(user_id));
    p.insert("first_name".into(), json!(first_name));
    p.insert("last_name".into(), json!(last_name));
    p.insert("email".into(), json!(email));
    p.insert("now".into(), json!(now_rfc3339()));
    db.execute(
        "INSERT INTO hub_user_profile \
         (hub_id, user_id, first_name, last_name, email, avatar_path, updated_at) \
         VALUES (:hub_id, :user_id, :first_name, :last_name, :email, '', :now) \
         ON CONFLICT (hub_id, user_id) DO UPDATE SET first_name = :first_name, \
         last_name = :last_name, email = :email, updated_at = :now",
        &p,
    )
    .await?;
    Ok(())
}

pub async fn set_avatar(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    user_id: &str,
    avatar_path: &str,
) -> Result<UserProfile> {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("user_id".into(), json!(user_id));
    p.insert("avatar_path".into(), json!(avatar_path));
    p.insert("now".into(), json!(now_rfc3339()));
    db.execute(
        "INSERT INTO hub_user_profile \
         (hub_id, user_id, first_name, last_name, email, avatar_path, updated_at) \
         VALUES (:hub_id, :user_id, '', '', '', :avatar_path, :now) \
         ON CONFLICT (hub_id, user_id) DO UPDATE SET avatar_path = :avatar_path, updated_at = :now",
        &p,
    )
    .await?;
    get(db, hub_id, user_id).await
}
