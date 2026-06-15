//! Verificación del **access JWT de usuario** emitido por el Cloud Portal (ARQUITECTURA.md §2.3).
//!
//! El Cloud firma los tokens con **RS256** (`rest_framework_simplejwt`, `SIGNING_KEY=PRIVATE_KEY`);
//! el Hub los verifica **offline** contra la clave pública (`GET /api/v1/auth/public-key/`). El
//! token lleva identidad — claim `user_id` (= `User.id`) + `exp` (1h) + `token_type` — **no**
//! permisos ni hub. Por eso esto solo autentica *quién* es el usuario; el alcance de permisos en
//! el hub es un problema aparte (no resuelto en el token).
use jsonwebtoken::{decode, Algorithm, DecodingKey, Validation};
use serde::Deserialize;

/// Claims verificadas del access token. `user_id` se deja como `Value` porque SimpleJWT emite el
/// PK crudo (entero o uuid según el modelo `User`); usa [`UserClaims::user_id_str`].
#[derive(Debug, Clone, Deserialize)]
pub struct UserClaims {
    pub user_id: serde_json::Value,
    #[serde(default)]
    pub token_type: String,
    pub exp: i64,
}

impl UserClaims {
    /// `user_id` como cadena (sirve igual si el PK es entero o uuid).
    pub fn user_id_str(&self) -> String {
        match &self.user_id {
            serde_json::Value::String(s) => s.clone(),
            other => other.to_string(),
        }
    }
}

#[derive(Debug, thiserror::Error)]
pub enum UserJwtError {
    #[error("clave pública inválida: {0}")]
    Key(String),
    #[error("token inválido o caducado: {0}")]
    Verify(String),
    #[error("token_type inesperado: `{0}` (se esperaba `access`)")]
    TokenType(String),
}

/// Verifica firma **RS256** + **expiración** del access JWT contra la clave pública (PEM) del
/// Cloud y devuelve las claims. No valida `aud`/`iss` (el Cloud no los pone) y rechaza tokens cuyo
/// `token_type` no sea `access` (p. ej. un refresh usado como access).
pub fn verify_user_jwt(token: &str, public_key_pem: &str) -> Result<UserClaims, UserJwtError> {
    let key = DecodingKey::from_rsa_pem(public_key_pem.as_bytes())
        .map_err(|e| UserJwtError::Key(e.to_string()))?;

    let mut validation = Validation::new(Algorithm::RS256);
    validation.validate_exp = true;
    // SimpleJWT no emite aud/iss; no exigir claims estándar más allá de exp.
    validation.required_spec_claims.clear();

    let data = decode::<UserClaims>(token, &key, &validation)
        .map_err(|e| UserJwtError::Verify(e.to_string()))?;

    if !data.claims.token_type.is_empty() && data.claims.token_type != "access" {
        return Err(UserJwtError::TokenType(data.claims.token_type.clone()));
    }
    Ok(data.claims)
}
