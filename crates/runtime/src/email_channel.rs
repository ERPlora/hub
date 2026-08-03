//! Configuración del canal de correo del Hub.
//!
//! Los metadatos viven en `_hub_email_channel`; contraseñas SMTP e identificadores del broker
//! OAuth se guardan cifrados con `HUB_SECRETS_KEY`. Las lecturas públicas devuelven únicamente
//! [`EmailChannelStatus`], nunca el secreto ni su ciphertext.

use erplora_db::{DatabaseAdapter, Params};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value as Json};

use crate::errors::{Result, RuntimeError};
use crate::registry::now_rfc3339;
use crate::secret_box::{self, SecretsKey};

pub const MANAGED_FROM_NAME: &str = "ERPlora";
pub const MANAGED_FROM_EMAIL: &str = "noreply@erplora.com";

#[derive(Debug, Clone, Copy, PartialEq, Eq, Deserialize, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum EmailMode {
    Managed,
    GoogleOauth,
    MicrosoftOauth,
    Smtp,
}

impl EmailMode {
    fn as_str(self) -> &'static str {
        match self {
            Self::Managed => "managed",
            Self::GoogleOauth => "google_oauth",
            Self::MicrosoftOauth => "microsoft_oauth",
            Self::Smtp => "smtp",
        }
    }

    fn parse(value: &str) -> Option<Self> {
        match value {
            "managed" => Some(Self::Managed),
            "google_oauth" => Some(Self::GoogleOauth),
            "microsoft_oauth" => Some(Self::MicrosoftOauth),
            "smtp" => Some(Self::Smtp),
            _ => None,
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Deserialize, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum SmtpSecurity {
    Tls,
    Starttls,
    None,
}

impl SmtpSecurity {
    fn as_str(self) -> &'static str {
        match self {
            Self::Tls => "tls",
            Self::Starttls => "starttls",
            Self::None => "none",
        }
    }

    fn parse(value: &str) -> Self {
        match value {
            "tls" => Self::Tls,
            "none" => Self::None,
            _ => Self::Starttls,
        }
    }
}

#[derive(Debug, Clone, Deserialize)]
pub struct EmailChannelInput {
    pub mode: EmailMode,
    #[serde(default)]
    pub host: String,
    #[serde(default)]
    pub port: u16,
    #[serde(default)]
    pub security: Option<SmtpSecurity>,
    #[serde(default)]
    pub username: String,
    /// Solo escritura. Vacío conserva la contraseña SMTP existente si la hay.
    #[serde(default)]
    pub password: String,
    #[serde(default)]
    pub from_name: String,
    #[serde(default)]
    pub from_email: String,
    #[serde(default)]
    pub reply_to: String,
    /// Cuenta visible devuelta por Google/Microsoft.
    #[serde(default)]
    pub account_email: String,
    /// Identificador opaco devuelto por el broker OAuth central. Solo escritura y cifrado.
    #[serde(default)]
    pub oauth_connection_id: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct EmailChannelStatus {
    pub mode: EmailMode,
    pub connected: bool,
    pub status: String,
    pub host: String,
    pub port: u16,
    pub security: SmtpSecurity,
    pub username: String,
    pub from_name: String,
    pub from_email: String,
    pub reply_to: String,
    pub account_email: String,
    pub has_secret: bool,
    pub last_test_at: Option<String>,
    pub last_error: String,
    pub updated_at: Option<String>,
    pub updated_by: String,
}

impl Default for EmailChannelStatus {
    fn default() -> Self {
        Self {
            mode: EmailMode::Managed,
            connected: true,
            status: "ready".into(),
            host: String::new(),
            port: 0,
            security: SmtpSecurity::Starttls,
            username: String::new(),
            from_name: MANAGED_FROM_NAME.into(),
            from_email: MANAGED_FROM_EMAIL.into(),
            reply_to: String::new(),
            account_email: String::new(),
            has_secret: false,
            last_test_at: None,
            last_error: String::new(),
            updated_at: None,
            updated_by: String::new(),
        }
    }
}

/// Configuración interna que consume el transporte. Su `Debug` no incluye secretos.
#[derive(Clone)]
pub struct EmailConnection {
    pub mode: EmailMode,
    pub host: String,
    pub port: u16,
    pub security: SmtpSecurity,
    pub username: String,
    pub password: String,
    pub from_name: String,
    pub from_email: String,
    pub reply_to: String,
    pub account_email: String,
    pub oauth_connection_id: String,
}

impl std::fmt::Debug for EmailConnection {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("EmailConnection")
            .field("mode", &self.mode)
            .field("host", &self.host)
            .field("port", &self.port)
            .field("security", &self.security)
            .field("username", &self.username)
            .field("password", &"<redacted>")
            .field("from_name", &self.from_name)
            .field("from_email", &self.from_email)
            .field("reply_to", &self.reply_to)
            .field("account_email", &self.account_email)
            .field("oauth_connection_id", &"<redacted>")
            .finish()
    }
}

fn config_error(detail: impl Into<String>) -> RuntimeError {
    RuntimeError::Notify(format!("configuración de correo: {}", detail.into()))
}

fn load_master_key() -> Result<Option<SecretsKey>> {
    secret_box::master_key_from_env()
        .map_err(|e| config_error(format!("{} inválida: {e}", secret_box::MASTER_KEY_ENV)))
}

fn require_master_key() -> Result<SecretsKey> {
    load_master_key()?.ok_or_else(|| {
        config_error(format!(
            "define {} antes de guardar credenciales; nunca se almacenan en claro",
            secret_box::MASTER_KEY_ENV
        ))
    })
}

fn valid_email(value: &str) -> bool {
    if value.is_empty() || value.len() > 254 || value.chars().any(|c| c.is_control()) {
        return value.is_empty();
    }
    let mut parts = value.split('@');
    let (Some(local), Some(domain), None) = (parts.next(), parts.next(), parts.next()) else {
        return false;
    };
    !local.is_empty()
        && domain.contains('.')
        && !domain.starts_with('.')
        && !domain.ends_with('.')
        && !value.chars().any(char::is_whitespace)
}

fn validate(input: &EmailChannelInput) -> Result<()> {
    if !valid_email(input.reply_to.trim())
        || !valid_email(input.from_email.trim())
        || !valid_email(input.account_email.trim())
    {
        return Err(config_error("dirección de email inválida"));
    }
    if input
        .from_name
        .chars()
        .chain(input.username.chars())
        .any(char::is_control)
    {
        return Err(config_error(
            "los campos de cabecera contienen caracteres de control",
        ));
    }
    match input.mode {
        EmailMode::Managed => Ok(()),
        EmailMode::Smtp => {
            if input.host.trim().is_empty()
                || input.host.chars().any(char::is_control)
                || input.port == 0
                || input.username.trim().is_empty()
                || input.from_email.trim().is_empty()
            {
                return Err(config_error(
                    "SMTP requiere host, puerto, usuario y dirección remitente",
                ));
            }
            Ok(())
        }
        EmailMode::GoogleOauth | EmailMode::MicrosoftOauth => {
            if input.account_email.trim().is_empty() {
                return Err(config_error("OAuth requiere la cuenta conectada"));
            }
            Ok(())
        }
    }
}

fn row_string(row: &Json, key: &str) -> String {
    row.get(key)
        .and_then(Json::as_str)
        .unwrap_or_default()
        .to_string()
}

async fn raw_row(db: &dyn DatabaseAdapter, hub_id: &str) -> Result<Option<Json>> {
    let mut params = Params::new();
    params.insert("hub_id".into(), json!(hub_id));
    Ok(db
        .query(
            "SELECT mode, host, port, security, username, secret_enc, from_name, from_email, \
             reply_to, account_email, status, last_test_at, last_error, updated_at, updated_by \
             FROM _hub_email_channel WHERE hub_id = :hub_id LIMIT 1",
            &params,
        )
        .await?
        .rows
        .into_iter()
        .next())
}

pub async fn status(db: &dyn DatabaseAdapter, hub_id: &str) -> Result<EmailChannelStatus> {
    let Some(row) = raw_row(db, hub_id).await? else {
        return Ok(EmailChannelStatus::default());
    };
    let mode = EmailMode::parse(&row_string(&row, "mode"))
        .ok_or_else(|| config_error("modo persistido desconocido"))?;
    let state = row_string(&row, "status");
    Ok(EmailChannelStatus {
        mode,
        connected: state == "ready",
        status: state,
        host: row_string(&row, "host"),
        port: row.get("port").and_then(Json::as_u64).unwrap_or_default() as u16,
        security: SmtpSecurity::parse(&row_string(&row, "security")),
        username: row_string(&row, "username"),
        from_name: row_string(&row, "from_name"),
        from_email: row_string(&row, "from_email"),
        reply_to: row_string(&row, "reply_to"),
        account_email: row_string(&row, "account_email"),
        has_secret: !row_string(&row, "secret_enc").is_empty(),
        last_test_at: row
            .get("last_test_at")
            .and_then(Json::as_str)
            .map(str::to_string),
        last_error: row_string(&row, "last_error"),
        updated_at: row
            .get("updated_at")
            .and_then(Json::as_str)
            .map(str::to_string),
        updated_by: row_string(&row, "updated_by"),
    })
}

pub async fn set(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    input: &EmailChannelInput,
    by: &str,
) -> Result<EmailChannelStatus> {
    validate(input)?;
    let previous = raw_row(db, hub_id).await?;
    let previous_mode = previous
        .as_ref()
        .and_then(|row| EmailMode::parse(&row_string(row, "mode")));
    let previous_secret = previous
        .as_ref()
        .map(|row| row_string(row, "secret_enc"))
        .unwrap_or_default();

    let secret_enc = match input.mode {
        EmailMode::Managed => String::new(),
        EmailMode::Smtp if input.password.is_empty() && previous_mode == Some(EmailMode::Smtp) => {
            if previous_secret.is_empty() {
                return Err(config_error("SMTP requiere contraseña"));
            }
            previous_secret
        }
        EmailMode::Smtp => {
            if input.password.is_empty() {
                return Err(config_error("SMTP requiere contraseña"));
            }
            secret_box::encrypt(
                &require_master_key()?,
                &json!({"password": input.password}).to_string(),
            )
            .map_err(|e| config_error(format!("cifrando contraseña SMTP: {e}")))?
        }
        EmailMode::GoogleOauth | EmailMode::MicrosoftOauth
            if input.oauth_connection_id.is_empty()
                && previous_mode == Some(input.mode)
                && !previous_secret.is_empty() =>
        {
            previous_secret
        }
        EmailMode::GoogleOauth | EmailMode::MicrosoftOauth => {
            if input.oauth_connection_id.is_empty() {
                return Err(config_error("OAuth requiere completar la conexión"));
            }
            secret_box::encrypt(
                &require_master_key()?,
                &json!({"connection_id": input.oauth_connection_id}).to_string(),
            )
            .map_err(|e| config_error(format!("cifrando conexión OAuth: {e}")))?
        }
    };

    let (from_name, from_email, connection_status) = match input.mode {
        EmailMode::Managed => (
            MANAGED_FROM_NAME.to_string(),
            MANAGED_FROM_EMAIL.to_string(),
            "ready",
        ),
        _ => (
            input.from_name.trim().to_string(),
            input.from_email.trim().to_string(),
            "ready",
        ),
    };
    let mut params = Params::new();
    params.insert("hub_id".into(), json!(hub_id));
    params.insert("mode".into(), json!(input.mode.as_str()));
    params.insert("host".into(), json!(input.host.trim()));
    params.insert("port".into(), json!(input.port));
    params.insert(
        "security".into(),
        json!(input.security.unwrap_or(SmtpSecurity::Starttls).as_str()),
    );
    params.insert("username".into(), json!(input.username.trim()));
    params.insert("secret_enc".into(), json!(secret_enc));
    params.insert("from_name".into(), json!(from_name));
    params.insert("from_email".into(), json!(from_email));
    params.insert("reply_to".into(), json!(input.reply_to.trim()));
    params.insert("account_email".into(), json!(input.account_email.trim()));
    params.insert("status".into(), json!(connection_status));
    params.insert("updated_at".into(), json!(now_rfc3339()));
    params.insert("updated_by".into(), json!(by));
    db.execute(
        "INSERT INTO _hub_email_channel \
         (hub_id, mode, host, port, security, username, secret_enc, from_name, from_email, \
          reply_to, account_email, status, last_test_at, last_error, updated_at, updated_by) \
         VALUES (:hub_id, :mode, :host, :port, :security, :username, :secret_enc, :from_name, \
          :from_email, :reply_to, :account_email, :status, NULL, '', :updated_at, :updated_by) \
         ON CONFLICT (hub_id) DO UPDATE SET mode = excluded.mode, host = excluded.host, \
          port = excluded.port, security = excluded.security, username = excluded.username, \
          secret_enc = excluded.secret_enc, from_name = excluded.from_name, \
          from_email = excluded.from_email, reply_to = excluded.reply_to, \
          account_email = excluded.account_email, status = excluded.status, last_error = '', \
          updated_at = excluded.updated_at, updated_by = excluded.updated_by",
        &params,
    )
    .await?;
    status(db, hub_id).await
}

/// Desconectar restaura el relay gestionado por defecto.
pub async fn disconnect(db: &dyn DatabaseAdapter, hub_id: &str) -> Result<EmailChannelStatus> {
    let mut params = Params::new();
    params.insert("hub_id".into(), json!(hub_id));
    db.execute(
        "DELETE FROM _hub_email_channel WHERE hub_id = :hub_id",
        &params,
    )
    .await?;
    Ok(EmailChannelStatus::default())
}

pub async fn load(db: &dyn DatabaseAdapter, hub_id: &str) -> Result<EmailConnection> {
    let Some(row) = raw_row(db, hub_id).await? else {
        return Ok(EmailConnection {
            mode: EmailMode::Managed,
            host: String::new(),
            port: 0,
            security: SmtpSecurity::Starttls,
            username: String::new(),
            password: String::new(),
            from_name: MANAGED_FROM_NAME.into(),
            from_email: MANAGED_FROM_EMAIL.into(),
            reply_to: String::new(),
            account_email: String::new(),
            oauth_connection_id: String::new(),
        });
    };
    let mode = EmailMode::parse(&row_string(&row, "mode"))
        .ok_or_else(|| config_error("modo persistido desconocido"))?;
    let secret_enc = row_string(&row, "secret_enc");
    let secret: Json = if secret_enc.is_empty() {
        json!({})
    } else {
        let plain = secret_box::decrypt_or_legacy(load_master_key()?.as_ref(), &secret_enc)
            .map_err(|e| config_error(format!("descifrando credenciales: {e}")))?;
        serde_json::from_str(&plain).map_err(|_| config_error("credenciales cifradas corruptas"))?
    };
    Ok(EmailConnection {
        mode,
        host: row_string(&row, "host"),
        port: row.get("port").and_then(Json::as_u64).unwrap_or_default() as u16,
        security: SmtpSecurity::parse(&row_string(&row, "security")),
        username: row_string(&row, "username"),
        password: secret
            .get("password")
            .and_then(Json::as_str)
            .unwrap_or_default()
            .to_string(),
        from_name: row_string(&row, "from_name"),
        from_email: row_string(&row, "from_email"),
        reply_to: row_string(&row, "reply_to"),
        account_email: row_string(&row, "account_email"),
        oauth_connection_id: secret
            .get("connection_id")
            .and_then(Json::as_str)
            .unwrap_or_default()
            .to_string(),
    })
}

pub async fn record_test_result(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    error: Option<&str>,
) -> Result<()> {
    // El relay gestionado puede no tener fila todavía; materializamos solo al registrar la prueba.
    let mut params = Params::new();
    params.insert("hub_id".into(), json!(hub_id));
    params.insert("at".into(), json!(now_rfc3339()));
    params.insert("error".into(), json!(error.unwrap_or_default()));
    params.insert(
        "status".into(),
        json!(if error.is_some() { "error" } else { "ready" }),
    );
    db.execute(
        "UPDATE _hub_email_channel SET last_test_at = :at, last_error = :error, status = :status \
         WHERE hub_id = :hub_id",
        &params,
    )
    .await?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::secret_box::test_support::{env_lock, test_key_b64, EnvVarGuard};
    use erplora_db::testutil::fresh_db;

    async fn ready_db() -> impl DatabaseAdapter {
        let db = fresh_db().await;
        crate::installer::ensure_hub_module_table(&db)
            .await
            .unwrap();
        crate::identity::ensure_tables(&db).await.unwrap();
        crate::system_migrations::apply(&db, "h1").await.unwrap();
        db
    }

    fn smtp(password: &str) -> EmailChannelInput {
        EmailChannelInput {
            mode: EmailMode::Smtp,
            host: "smtp.example.com".into(),
            port: 587,
            security: Some(SmtpSecurity::Starttls),
            username: "billing@example.com".into(),
            password: password.into(),
            from_name: "Mi negocio".into(),
            from_email: "billing@example.com".into(),
            reply_to: "info@example.com".into(),
            account_email: String::new(),
            oauth_connection_id: String::new(),
        }
    }

    #[tokio::test]
    async fn managed_is_the_default_without_a_database_row() {
        let db = ready_db().await;
        let value = status(&db, "h1").await.unwrap();
        assert_eq!(value.mode, EmailMode::Managed);
        assert!(value.connected);
        assert_eq!(value.from_email, MANAGED_FROM_EMAIL);
    }

    #[tokio::test]
    async fn smtp_secret_is_encrypted_and_never_returned_by_status() {
        let _lock = env_lock();
        let _env = EnvVarGuard::set(&test_key_b64(31));
        let db = ready_db().await;
        let value = set(&db, "h1", &smtp("SUPER-SECRET"), "hub_user:admin")
            .await
            .unwrap();
        assert!(value.has_secret);
        let serialized = serde_json::to_string(&value).unwrap();
        assert!(!serialized.contains("SUPER-SECRET"));

        let mut p = Params::new();
        p.insert("hub_id".into(), json!("h1"));
        let raw = db
            .query(
                "SELECT secret_enc FROM _hub_email_channel WHERE hub_id = :hub_id",
                &p,
            )
            .await
            .unwrap();
        let encrypted = raw.rows[0]["secret_enc"].as_str().unwrap();
        assert!(secret_box::is_encrypted(encrypted));
        assert!(!encrypted.contains("SUPER-SECRET"));
        assert_eq!(load(&db, "h1").await.unwrap().password, "SUPER-SECRET");
    }

    #[tokio::test]
    async fn smtp_write_fails_closed_without_the_master_key() {
        let _lock = env_lock();
        let _env = EnvVarGuard::unset();
        let db = ready_db().await;
        let err = set(&db, "h1", &smtp("secret"), "hub_user:admin")
            .await
            .unwrap_err();
        assert!(err.to_string().contains(secret_box::MASTER_KEY_ENV));
    }

    #[tokio::test]
    async fn empty_password_keeps_the_existing_encrypted_secret() {
        let _lock = env_lock();
        let _env = EnvVarGuard::set(&test_key_b64(32));
        let db = ready_db().await;
        set(&db, "h1", &smtp("first"), "hub_user:admin")
            .await
            .unwrap();
        let mut update = smtp("");
        update.from_name = "Nuevo nombre".into();
        set(&db, "h1", &update, "hub_user:admin").await.unwrap();
        let loaded = load(&db, "h1").await.unwrap();
        assert_eq!(loaded.password, "first");
        assert_eq!(loaded.from_name, "Nuevo nombre");
    }
}
