//! Entitlement de módulos para la app Tauri **gratuita** (gate de arranque).
//!
//! El hub pregunta al Cloud `GET /api/v1/hub/device/entitlement/` (con el JWT del
//! usuario) y recibe un **token RS256 firmado** (el mismo par de claves que el JWT de
//! usuario; clave pública en `GET /api/v1/auth/public-key/`). La app:
//!  1. cachea el token + la clave pública,
//!  2. lo **verifica OFFLINE** con [`verify_entitlement`] contra la clave pública cacheada,
//!  3. mientras esté dentro de la **ventana de gracia** (`grace_until`), arranca sin red y
//!     monta solo los módulos de `claims.modules`.
//!
//! La verificación NO usa `exp` para bloquear: el offline-first exige seguir operando
//! tras `exp` hasta `grace_until` (lo emite el Cloud, ver `entitlement.py`). Por eso
//! desactivamos la validación de `exp` de `jsonwebtoken` y comprobamos `grace_until` aquí.

use jsonwebtoken::{decode, Algorithm, DecodingKey, Validation};
use serde::{Deserialize, Serialize};

/// Un módulo al que el hub tiene derecho. `Serialize` además de `Deserialize`: el gate Tauri lo
/// devuelve al frontend dentro de `GateOutcome` (vía `invoke`).
#[derive(Debug, Clone, Deserialize, Serialize, PartialEq, Eq)]
pub struct EntitledModule {
    pub module_id: String,
    pub tier: String,
    pub version: String,
}

/// Cuerpo JSON de la respuesta del endpoint `entitlement/`.
///
/// `modules` aquí es una conveniencia (sin firmar) para pintar UI; la lista
/// **autoritativa** es la de [`EntitlementClaims`] tras verificar el `token`.
#[derive(Debug, Clone, Deserialize)]
pub struct EntitlementResponse {
    pub token: String,
    #[serde(default)]
    pub algorithm: String,
    #[serde(default)]
    pub modules: Vec<EntitledModule>,
    #[serde(default)]
    pub expires_at: String,
    #[serde(default)]
    pub grace_until: String,
}

impl EntitlementResponse {
    pub fn parse(json: &str) -> Result<Self, serde_json::Error> {
        serde_json::from_str(json)
    }
}

/// Claims decodificadas y **verificadas** del token firmado.
#[derive(Debug, Clone, Deserialize, PartialEq, Eq)]
pub struct EntitlementClaims {
    pub hub_id: String,
    pub deployment_mode: String,
    pub modules: Vec<EntitledModule>,
    pub iat: i64,
    pub exp: i64,
    /// Hasta este unix-ts el hub puede operar offline con este token cacheado.
    pub grace_until: i64,
}

impl EntitlementClaims {
    /// `true` si `module_id` está entre los módulos autorizados.
    pub fn allows(&self, module_id: &str) -> bool {
        self.modules.iter().any(|m| m.module_id == module_id)
    }
}

#[derive(Debug, thiserror::Error)]
pub enum EntitlementError {
    #[error("clave pública inválida: {0}")]
    Key(String),
    #[error("verificación del token fallida: {0}")]
    Verify(String),
    #[error("token caducado más allá de la ventana de gracia")]
    GraceExpired,
}

/// Verifica la firma RS256 del token **offline** contra la clave pública (PEM) y
/// comprueba la ventana de gracia. Devuelve las claims si el token es válido y aún
/// dentro de `grace_until`.
///
/// `now_unix` lo pasa el llamador (reloj del sistema) para mantener la función pura
/// y testeable sin depender del reloj real.
pub fn verify_entitlement(
    token: &str,
    public_key_pem: &str,
    now_unix: i64,
) -> Result<EntitlementClaims, EntitlementError> {
    let key = DecodingKey::from_rsa_pem(public_key_pem.as_bytes())
        .map_err(|e| EntitlementError::Key(e.to_string()))?;

    let mut validation = Validation::new(Algorithm::RS256);
    // La gracia la imponemos nosotros (ver doc del módulo): no bloquear por `exp`.
    validation.validate_exp = false;
    validation.required_spec_claims.clear();

    let data = decode::<EntitlementClaims>(token, &key, &validation)
        .map_err(|e| EntitlementError::Verify(e.to_string()))?;

    if now_unix > data.claims.grace_until {
        return Err(EntitlementError::GraceExpired);
    }
    Ok(data.claims)
}
