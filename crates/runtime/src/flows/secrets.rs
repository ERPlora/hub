//! **`_flow_secrets`** — the credentials an `http` step needs, and the only thing in this kernel
//! that is deliberately impossible to read back (ADR-0283 §4, hub#662).
//!
//! Three properties, and each one closes a different way a credential leaks:
//!
//! 1. **Write-only.** There is no function here that returns a value to a human, and no endpoint
//!    that could. `list` returns NAMES. The only reader is [`resolve`], which is `pub(crate)` and
//!    called by the executor while it builds the request that is about to leave. A "reveal" button
//!    would turn every admin session into a copy of every API key the hub holds.
//! 2. **Encrypted at rest** with [`crate::secret_box`] (AES-256-GCM, master key in the environment,
//!    hub#114). Whoever reads the database — a backup, a support dump, a stolen volume — gets the
//!    envelope and not the key, because the key was never next to it.
//! 3. **Referenced by name only**, as `{{secret.NAME}}`, and only from an `http` step
//!    (`def::FlowDefinition::validate`). The value is substituted while the request is built, in
//!    memory, and what gets written to `_flow_run_steps` is the same request with `***` where the
//!    secret was — see `flows::http`.
//!
//! Fail-closed on the master key: without `HUB_SECRETS_KEY` a secret cannot be STORED. The
//! alternative — storing it in the clear "for now" — is how a credential ends up in a plain-text
//! backup that outlives the decision.
use std::collections::BTreeMap;

use erplora_db::{DatabaseAdapter, Params};
use serde_json::{json, Value as Json};

use crate::errors::{Result, RuntimeError};
use crate::registry::{new_id, now_rfc3339};
use crate::secret_box;

pub const ERR_SECRET_NOT_FOUND: &str = "flow.secret_not_found";
pub const ERR_SECRETS_KEY_MISSING: &str = "flow.secrets_key_missing";
pub const ERR_INVALID_SECRET_NAME: &str = "flow.invalid_secret_name";
pub const ERR_SECRET_UNREADABLE: &str = "flow.secret_unreadable";

/// A secret as everybody outside this module sees it: **its name and when it was touched**. There
/// is no `value` field, and that absence is the design — a struct with a value is a struct that
/// eventually gets serialised into a response.
#[derive(Debug, Clone, serde::Serialize, PartialEq)]
pub struct SecretInfo {
    pub name: String,
    pub created_at: String,
    pub updated_at: String,
    pub updated_by: String,
}

fn domain(code: &str, message: impl Into<String>) -> RuntimeError {
    RuntimeError::Domain {
        code: code.to_string(),
        message: message.into(),
    }
}

/// `API_KEY`, `WHATSAPP_TOKEN` — upper snake case, like an environment variable.
///
/// It is not cosmetic: the name travels inside a mapping path (`{{secret.API_KEY}}`), so a name
/// with a dot or a brace in it would parse as something else entirely, and one that differs only
/// in case would be two secrets an owner reads as one.
fn check_name(name: &str) -> Result<()> {
    let ok = !name.is_empty()
        && name.len() <= 64
        && name.starts_with(|c: char| c.is_ascii_uppercase())
        && name
            .chars()
            .all(|c| c.is_ascii_uppercase() || c.is_ascii_digit() || c == '_');
    if ok {
        return Ok(());
    }
    Err(domain(
        ERR_INVALID_SECRET_NAME,
        format!(
            "`{name}` is not a secret name: use UPPER_SNAKE_CASE (A-Z, 0-9, `_`), starting with a \
             letter, up to 64 characters — it is read back as `{{{{secret.NAME}}}}`"
        ),
    ))
}

fn master_key() -> Result<secret_box::SecretsKey> {
    match secret_box::master_key_from_env() {
        Ok(Some(key)) => Ok(key),
        Ok(None) => Err(domain(
            ERR_SECRETS_KEY_MISSING,
            format!(
                "{} is not set: a flow secret is refused rather than stored in the clear (hub#114)",
                secret_box::MASTER_KEY_ENV
            ),
        )),
        Err(e) => Err(domain(ERR_SECRETS_KEY_MISSING, format!("{e}"))),
    }
}

/// Creates or replaces a secret. Replacing keeps the row (and its `created_at`) so «when did this
/// credential last change» survives a rotation.
pub async fn put(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    name: &str,
    value: &str,
    by: &str,
) -> Result<SecretInfo> {
    check_name(name)?;
    if value.is_empty() {
        return Err(domain(
            ERR_INVALID_SECRET_NAME,
            format!("secret `{name}`: an empty value is a credential that will fail at 3 AM"),
        ));
    }
    let key = master_key()?;
    let value_enc = secret_box::encrypt(&key, value)
        .map_err(|e| domain(ERR_SECRETS_KEY_MISSING, format!("{e}")))?;

    let now = now_rfc3339();
    let mut p = Params::new();
    p.insert("id".into(), json!(new_id()));
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("name".into(), json!(name));
    p.insert("value".into(), json!(value_enc));
    p.insert("now".into(), json!(now));
    p.insert("by".into(), json!(by));
    db.execute(
        "INSERT INTO _flow_secrets (id, hub_id, name, value_enc, created_at, created_by, \
                                    updated_at, updated_by) \
         VALUES (:id, :hub_id, :name, :value, :now, :by, :now, :by) \
         ON CONFLICT (hub_id, name) WHERE deleted_at IS NULL DO UPDATE SET \
           value_enc = :value, updated_at = :now, updated_by = :by",
        &p,
    )
    .await?;
    get_info(db, hub_id, name).await
}

/// The names this hub holds. **Never the values** — this is what `GET …/secrets` answers.
pub async fn list(db: &dyn DatabaseAdapter, hub_id: &str) -> Result<Vec<SecretInfo>> {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    let res = db
        .query(
            "SELECT name, created_at, updated_at, updated_by FROM _flow_secrets \
             WHERE hub_id = :hub_id AND deleted_at IS NULL ORDER BY name",
            &p,
        )
        .await?;
    Ok(res.rows.iter().map(info_row).collect())
}

async fn get_info(db: &dyn DatabaseAdapter, hub_id: &str, name: &str) -> Result<SecretInfo> {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("name".into(), json!(name));
    let res = db
        .query(
            "SELECT name, created_at, updated_at, updated_by FROM _flow_secrets \
             WHERE hub_id = :hub_id AND name = :name AND deleted_at IS NULL",
            &p,
        )
        .await?;
    res.rows
        .first()
        .map(info_row)
        .ok_or_else(|| domain(ERR_SECRET_NOT_FOUND, format!("no secret named `{name}`")))
}

/// Forgets a secret. Soft-delete like everything else in this kernel: the row records that a
/// credential existed and who removed it, and the ciphertext stays unreadable either way.
pub async fn delete(db: &dyn DatabaseAdapter, hub_id: &str, name: &str, by: &str) -> Result<()> {
    get_info(db, hub_id, name).await?;
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("name".into(), json!(name));
    p.insert("now".into(), json!(now_rfc3339()));
    p.insert("by".into(), json!(by));
    db.execute(
        "UPDATE _flow_secrets SET deleted_at = :now, deleted_by = :by, value_enc = '' \
         WHERE hub_id = :hub_id AND name = :name AND deleted_at IS NULL",
        &p,
    )
    .await?;
    Ok(())
}

/// **The only reader.** Decrypts exactly the names a step asked for, at the moment its request is
/// built. `pub(crate)` on purpose: the REST layer cannot call this even by accident.
///
/// A name the step references and this hub does not hold is an ERROR, never an empty string:
/// sending `Authorization: Bearer ` to a real API is a request that leaves the hub, gets refused,
/// and looks like the API is down.
pub(crate) async fn resolve(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    names: &[String],
) -> Result<BTreeMap<String, String>> {
    let mut out = BTreeMap::new();
    if names.is_empty() {
        return Ok(out);
    }
    let key = master_key()?;
    for name in names {
        let mut p = Params::new();
        p.insert("hub_id".into(), json!(hub_id));
        p.insert("name".into(), json!(name));
        let res = db
            .query(
                "SELECT value_enc FROM _flow_secrets \
                 WHERE hub_id = :hub_id AND name = :name AND deleted_at IS NULL",
                &p,
            )
            .await?;
        let stored = res
            .rows
            .first()
            .and_then(|r| r["value_enc"].as_str().map(|s| s.to_string()))
            .ok_or_else(|| {
                domain(
                    ERR_SECRET_NOT_FOUND,
                    format!(
                        "this flow references `{{{{secret.{name}}}}}` and this hub has no secret \
                         called `{name}`"
                    ),
                )
            })?;
        // A row that is not an envelope was not written by `put`. Refuse instead of using it: the
        // one thing worse than not sending the credential is sending whatever that column holds.
        if !secret_box::is_encrypted(&stored) {
            return Err(domain(
                ERR_SECRET_UNREADABLE,
                format!("secret `{name}` is not stored in the encrypted envelope this hub writes"),
            ));
        }
        let value = secret_box::decrypt_or_legacy(Some(&key), &stored)
            .map_err(|e| domain(ERR_SECRET_UNREADABLE, format!("secret `{name}`: {e}")))?;
        out.insert(name.clone(), value);
    }
    Ok(out)
}

fn info_row(row: &Json) -> SecretInfo {
    let text = |k: &str| row[k].as_str().unwrap_or_default().to_string();
    SecretInfo {
        name: text("name"),
        created_at: text("created_at"),
        updated_at: text("updated_at"),
        updated_by: text("updated_by"),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::flows::test_support;
    use crate::secret_box::test_support::{env_lock, test_key_b64, EnvVarGuard};
    use erplora_db::testutil::fresh_db;

    const HUB: &str = "hub-secrets";

    async fn db() -> impl DatabaseAdapter {
        let db = fresh_db().await;
        test_support::ensure_schema(&db, HUB).await;
        db
    }

    #[tokio::test]
    async fn a_stored_secret_is_unreadable_in_the_database_and_comes_back_only_for_a_step() {
        let _lock = env_lock();
        let _key = EnvVarGuard::set(&test_key_b64(7));
        let db = db().await;

        put(&db, HUB, "API_KEY", "sk-live-42", "hub_user:1")
            .await
            .unwrap();

        // What the column holds is the envelope, not the credential.
        let stored = db
            .query("SELECT value_enc FROM _flow_secrets", &Params::new())
            .await
            .unwrap()
            .rows[0]["value_enc"]
            .as_str()
            .unwrap()
            .to_string();
        assert!(
            !stored.contains("sk-live-42"),
            "the value is encrypted at rest"
        );
        assert!(secret_box::is_encrypted(&stored));

        // And the ONE reader gets it back.
        let resolved = resolve(&db, HUB, &["API_KEY".to_string()]).await.unwrap();
        assert_eq!(resolved["API_KEY"], "sk-live-42");
    }

    #[tokio::test]
    async fn listing_secrets_answers_names_and_has_nowhere_to_put_a_value() {
        let _lock = env_lock();
        let _key = EnvVarGuard::set(&test_key_b64(7));
        let db = db().await;
        put(&db, HUB, "API_KEY", "sk-live-42", "hub_user:1")
            .await
            .unwrap();
        put(&db, HUB, "WEBHOOK_TOKEN", "whsec-9", "hub_user:1")
            .await
            .unwrap();

        let names: Vec<String> = list(&db, HUB)
            .await
            .unwrap()
            .into_iter()
            .map(|s| s.name)
            .collect();
        assert_eq!(names, vec!["API_KEY", "WEBHOOK_TOKEN"]);
        // Serialising the listing is what the endpoint does; no value can ride along.
        let json = serde_json::to_string(&list(&db, HUB).await.unwrap()).unwrap();
        assert!(
            !json.contains("sk-live-42") && !json.contains("whsec-9"),
            "{json}"
        );
    }

    #[tokio::test]
    async fn rotating_a_secret_replaces_the_value_and_keeps_the_row() {
        let _lock = env_lock();
        let _key = EnvVarGuard::set(&test_key_b64(7));
        let db = db().await;
        let first = put(&db, HUB, "API_KEY", "old", "hub_user:1").await.unwrap();
        let second = put(&db, HUB, "API_KEY", "new", "hub_user:2").await.unwrap();

        assert_eq!(
            first.created_at, second.created_at,
            "the same row was rotated"
        );
        assert_eq!(second.updated_by, "hub_user:2");
        assert_eq!(list(&db, HUB).await.unwrap().len(), 1);
        assert_eq!(
            resolve(&db, HUB, &["API_KEY".to_string()]).await.unwrap()["API_KEY"],
            "new"
        );
    }

    #[tokio::test]
    async fn a_deleted_secret_stops_resolving_and_leaves_no_ciphertext_behind() {
        let _lock = env_lock();
        let _key = EnvVarGuard::set(&test_key_b64(7));
        let db = db().await;
        put(&db, HUB, "API_KEY", "sk-live-42", "hub_user:1")
            .await
            .unwrap();
        delete(&db, HUB, "API_KEY", "hub_user:1").await.unwrap();

        assert!(list(&db, HUB).await.unwrap().is_empty());
        assert!(resolve(&db, HUB, &["API_KEY".to_string()]).await.is_err());
        let leftovers = db
            .query("SELECT value_enc FROM _flow_secrets", &Params::new())
            .await
            .unwrap();
        assert_eq!(
            leftovers.rows[0]["value_enc"],
            json!(""),
            "the tombstone keeps no envelope"
        );
        // Re-creating it later is not a conflict with its own tombstone.
        put(&db, HUB, "API_KEY", "sk-live-43", "hub_user:1")
            .await
            .unwrap();
        assert_eq!(
            resolve(&db, HUB, &["API_KEY".to_string()]).await.unwrap()["API_KEY"],
            "sk-live-43"
        );
    }

    #[tokio::test]
    async fn a_secret_belongs_to_its_hub() {
        let _lock = env_lock();
        let _key = EnvVarGuard::set(&test_key_b64(7));
        let db = db().await;
        put(&db, HUB, "API_KEY", "sk-live-42", "hub_user:1")
            .await
            .unwrap();
        assert!(resolve(&db, "hub-other", &["API_KEY".to_string()])
            .await
            .is_err());
        assert!(list(&db, "hub-other").await.unwrap().is_empty());
    }

    #[tokio::test]
    async fn a_name_a_step_could_not_reference_is_refused() {
        let _lock = env_lock();
        let _key = EnvVarGuard::set(&test_key_b64(7));
        let db = db().await;
        for name in ["api.key", "api key", "1KEY", "", "lower"] {
            assert!(
                put(&db, HUB, name, "v", "hub_user:1").await.is_err(),
                "`{name}` is not addressable as {{{{secret.{name}}}}}"
            );
        }
    }

    #[tokio::test]
    async fn a_secret_a_step_names_and_the_hub_does_not_hold_is_an_error_not_an_empty_string() {
        let _lock = env_lock();
        let _key = EnvVarGuard::set(&test_key_b64(7));
        let db = db().await;
        let err = resolve(&db, HUB, &["MISSING".to_string()])
            .await
            .expect_err("`Authorization: Bearer ` would look like the API is down");
        assert!(format!("{err}").contains("MISSING"), "{err}");
    }

    #[tokio::test]
    async fn without_the_master_key_a_secret_is_refused_rather_than_stored_in_the_clear() {
        let _lock = env_lock();
        let _key = EnvVarGuard::unset();
        let db = db().await;
        let err = put(&db, HUB, "API_KEY", "sk-live-42", "hub_user:1")
            .await
            .expect_err("storing it unencrypted would outlive the decision in a backup");
        assert!(
            format!("{err}").contains(secret_box::MASTER_KEY_ENV),
            "{err}"
        );
        assert!(list(&db, HUB).await.unwrap().is_empty(), "nothing landed");
    }

    #[tokio::test]
    async fn a_value_that_is_not_the_envelope_this_hub_writes_is_refused() {
        let _lock = env_lock();
        let _key = EnvVarGuard::set(&test_key_b64(7));
        let db = db().await;
        // Somebody (a bad restore, a hand-written INSERT) put a plain value in the column.
        let mut p = Params::new();
        p.insert("id".into(), json!(new_id()));
        p.insert("hub_id".into(), json!(HUB));
        p.insert("now".into(), json!(now_rfc3339()));
        db.execute(
            "INSERT INTO _flow_secrets (id, hub_id, name, value_enc, created_at, updated_at) \
             VALUES (:id, :hub_id, 'API_KEY', 'sk-plain', :now, :now)",
            &p,
        )
        .await
        .unwrap();

        let err = resolve(&db, HUB, &["API_KEY".to_string()])
            .await
            .expect_err("sending whatever that column holds is worse than not calling");
        assert!(format!("{err}").contains("API_KEY"), "{err}");
    }
}
