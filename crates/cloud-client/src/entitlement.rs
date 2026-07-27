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
    pub modules: Vec<EntitledModule>,
    pub iat: i64,
    pub exp: i64,
    /// Hasta este unix-ts el hub puede operar offline con este token cacheado.
    pub grace_until: i64,
    /// Claim ADITIVO (2026-07-12): gracia ESPECÍFICA de los módulos **de pago** (5 días en el
    /// SaaS, separada de la global de 7 de `grace_until` que usa el gate de la app). Tokens
    /// antiguos no lo traen → `None` (retrocompatible) y la rama (b) de la revalidación cae a
    /// `grace_until`.
    #[serde(default)]
    pub paid_grace_until: Option<i64>,
    /// Claim ADITIVO (saas#812, ADR-0154): nombre del **plan** contratado. Solo informativo del
    /// lado del hub (la UI puede pintarlo); no gobierna ningún gate. Tokens antiguos no lo traen
    /// → `None`.
    #[serde(default)]
    pub plan: Option<String>,
    /// Claim ADITIVO (saas#812, ADR-0154): nº máximo de **dispositivos activos** simultáneos que
    /// permite el plan. `0` = **ilimitado** (Hub Cloud multi-dispositivo, o token antiguo sin el
    /// claim → default). Con `1`, el runtime aplica *single active device session* con desalojo
    /// (takeover) al abrir sesión en un dispositivo nuevo (ver `identity::enforce_device_limit`).
    #[serde(default)]
    pub max_devices: u32,
    /// Claim ADITIVO (saas#817, ADR-0154): cuota de base de datos del plan en GiB.
    /// `0` = ilimitado/autoscaling, y también el fallback retrocompatible para tokens antiguos.
    #[serde(default)]
    pub max_database_size_gb: u32,
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

#[cfg(test)]
mod tests {
    use super::*;
    use jsonwebtoken::{encode, Algorithm, EncodingKey, Header};
    use serde_json::json;

    const PRIV: &str = r#"-----BEGIN PRIVATE KEY-----
MIIEvgIBADANBgkqhkiG9w0BAQEFAASCBKgwggSkAgEAAoIBAQDzGzIyJJGCZ9C6
y6Bm5rDSD6oyPm6vNLbP1XE3JsIdtZx8yRBpfomjsgtl5BNixVgqFAxts5m7odJ1
A3i2oKdBqsVK1wF+jpVaEf8O6+ts+8s3ju8AZCyUSNjCqRUObUC9jjOCW5VSWSnU
sZdGNXU7UTWOtbvOxqy+IdFE0DOeazH+i2SSQ+WV4u37rlidGh0GHYSsnbQeHRyX
Z4iyYxCfQDlqGAYCPp3GCvEdra+TiZXmJfIl7as8/cTqBY3wOuscwCi7pGLGODQy
H8QawNShpzvUHNqtTo5/o4DVTWf3j0LUJDCllswkMIRMX9m9M9Dhvqr6qD9dei+j
uR8WwyGdAgMBAAECggEAEKuWv5V+XODdkVGRSD0dduoYE6XwVRdaSdorD0sbGIpx
lqT6+SDyM0VsPqprIeTCbPA/Ae7E5fbsxZVdW7icf4ZETSN9OL5yQ2DkipNm62xA
vSiR/wbff7OXGZIanYikXds4cQHytVjj42/iHbBgv5aMA6M2o7E/+zG6deuI/p3c
8iq9mBEA8ErV10ybS5lMyo1ZkIXWG2OStP4yXVg4jH9GVVBKrV/vFVDPXgJLY6nv
aOBRu130OwK89STAqI13kBZ3H+wksu6UFc9NoQFPRnTf6pW+NhiO9F0RRAZwVC+N
mJJ4xwKUB8sg9p6/mIfqQTjDuKd1IsvFcaDZgd3KSQKBgQD9BUOv1ok6PnSrSSrU
5RsiJHuJcqR//qvFpyABejsB0Ilmco/dgQN6Knc4JZWX2FVcK8mofTbpQPKc6aOZ
GE+15xP3W62MIgaz5kyltxqa0g9DIRKktmiQtGWHDUkL8kXyLwaNxHjj03h/3ku/
AaiAt8qZ1xhBl4JvBKhmrUOnXwKBgQD1+AtzZ9fHLjN3GOk4SRvIMOt1mB0OOnZY
19jTPJD+Pyw9AH8ohhhdTIQTRMm+TIC5n/G6lMtJu9iSwqY2Kis60UyJa6BxwJpf
WTB1hyRUe9jGtwv9Aj9dyLwAyGAqp00WTkwoF7nRZO6pEpwCntydOsHFLlGR3hG2
+LYU4dkEgwKBgQCgN2QsBSJyMjg4eiVYGBc9YHKlj2Wg8wecKf63UMnqlT1cFPEK
ZvZntlo1wH7gXwl2Svfv7BIIU6sNN1jzyZQ38DIRcQkM8kLiSdOBH9gF7zvg2yFu
EV9XOhQMF5qIqQonmCWDQcT3JuJnvcCjG46yqy7siWp/pkvetslX8yEi6wKBgAdz
MN2Y+pck1hg4X+/9fuLsYGVaax7gNG9ycjXLstSQk0Vxu2g9z4Ub6TAwODAUXx3A
M3EkSpf8IY4oaSJg2phYeIn9AYoQfFyA9g/JPRd1/NXf+3P5WnP7vX4Ek60XDiWr
z3Czb0RhWz0xvBn0N9hnTDEtuvjBEiZJmDI/uPQDAoGBAOIt9bClD86rZ+gQttCH
+IQF7kWpM5sFJ1T99WgzVhh2KcoAbYBJXeNBrDaV5RXH81lgpJCr33UUb6dEH6Ro
jmmYhehBeEknoM0QbKpNkltZHLxv3hOEr3cdJxFhTfF1xtknyuD4PkCQxNCopR1N
2LZnAS37uyj9SuBl2xKDyikA
-----END PRIVATE KEY-----
"#;
    const PUB: &str = r#"-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA8xsyMiSRgmfQusugZuaw
0g+qMj5urzS2z9VxNybCHbWcfMkQaX6Jo7ILZeQTYsVYKhQMbbOZu6HSdQN4tqCn
QarFStcBfo6VWhH/DuvrbPvLN47vAGQslEjYwqkVDm1AvY4zgluVUlkp1LGXRjV1
O1E1jrW7zsasviHRRNAznmsx/otkkkPlleLt+65YnRodBh2ErJ20Hh0cl2eIsmMQ
n0A5ahgGAj6dxgrxHa2vk4mV5iXyJe2rPP3E6gWN8DrrHMAou6Rixjg0Mh/EGsDU
oac71BzarU6Of6OA1U1n949C1CQwpZbMJDCETF/ZvTPQ4b6q+qg/XXovo7kfFsMh
nQIDAQAB
-----END PUBLIC KEY-----
"#;

    fn sign(exp: i64, grace_until: i64) -> String {
        let claims = json!({
            "hub_id": "h1",
            "modules": [{"module_id": "pos", "tier": "basic", "version": "1.0.0"}],
            "iat": 1000,
            "exp": exp,
            "grace_until": grace_until,
        });
        let key = EncodingKey::from_rsa_pem(PRIV.as_bytes()).unwrap();
        encode(&Header::new(Algorithm::RS256), &claims, &key).unwrap()
    }

    #[test]
    fn verifies_within_grace_even_after_exp() {
        // now (3000) is past exp (2000) but within grace_until (9000): offline-first.
        let token = sign(2000, 9000);
        let claims = verify_entitlement(&token, PUB, 3000).unwrap();
        assert_eq!(claims.hub_id, "h1");
        assert!(claims.allows("pos"));
        assert!(!claims.allows("not-installed"));
    }

    #[test]
    fn token_antiguo_sin_paid_grace_until_deserializa_con_none() {
        // Retrocompat del claim ADITIVO: los tokens que el SaaS emitió sin `paid_grace_until`
        // siguen verificando EXACTAMENTE igual y el campo queda a None (fallback a grace_until).
        let token = sign(2000, 9000);
        let claims = verify_entitlement(&token, PUB, 3000).unwrap();
        assert_eq!(claims.paid_grace_until, None);
    }

    #[test]
    fn token_legacy_con_deployment_mode_se_ignora_sin_romper() {
        // LOCKSTEP con saas: el claim `deployment_mode` se retiró del token (ADR-0154). El Hub
        // ya no lo lee, pero un SaaS antiguo puede seguir emitiéndolo un tiempo. Sin
        // `deny_unknown_fields`, serde debe IGNORARLO en silencio y verificar igual (tolerancia).
        let claims_json = json!({
            "hub_id": "h1",
            "deployment_mode": "cloud",
            "modules": [{"module_id": "pos", "tier": "basic", "version": "1.0.0"}],
            "iat": 1000,
            "exp": 2000,
            "grace_until": 9000,
        });
        let key = EncodingKey::from_rsa_pem(PRIV.as_bytes()).unwrap();
        let token = encode(&Header::new(Algorithm::RS256), &claims_json, &key).unwrap();
        let claims = verify_entitlement(&token, PUB, 3000).unwrap();
        assert_eq!(claims.hub_id, "h1");
        assert!(claims.allows("pos"));
    }

    #[test]
    fn token_con_limites_del_plan_los_expone_en_las_claims() {
        // Claims ADITIVOS del SaaS (saas#812/#817, ADR-0154): plan, dispositivos y cuota de BD.
        // El parseo debe exponerlos solo después de verificar la firma.
        let claims_json = json!({
            "hub_id": "h1",
            "modules": [{"module_id": "pos", "tier": "premium", "version": "1.0.0"}],
            "iat": 1000,
            "exp": 2000,
            "grace_until": 9000,
            "plan": "restaurant",
            "max_devices": 1,
            "max_database_size_gb": 5,
        });
        let key = EncodingKey::from_rsa_pem(PRIV.as_bytes()).unwrap();
        let token = encode(&Header::new(Algorithm::RS256), &claims_json, &key).unwrap();
        let claims = verify_entitlement(&token, PUB, 3000).unwrap();
        assert_eq!(claims.plan.as_deref(), Some("restaurant"));
        assert_eq!(claims.max_devices, 1);
        assert_eq!(claims.max_database_size_gb, 5);
    }

    #[test]
    fn token_antiguo_sin_limites_del_plan_usa_defaults_ilimitados() {
        // Retrocompat: un token anterior a saas#812/#817 no trae plan ni límites. Deben quedar
        // en `None` / `0` sin romper la verificación (0 = ilimitado/fail-open).
        let token = sign(2000, 9000); // `sign` NO incluye los claims aditivos del plan.
        let claims = verify_entitlement(&token, PUB, 3000).unwrap();
        assert_eq!(claims.plan, None);
        assert_eq!(claims.max_devices, 0);
        assert_eq!(claims.max_database_size_gb, 0);
    }

    #[test]
    fn token_con_paid_grace_until_lo_expone_en_las_claims() {
        let claims_json = json!({
            "hub_id": "h1",
            "modules": [{"module_id": "pos", "tier": "premium", "version": "1.0.0"}],
            "iat": 1000,
            "exp": 2000,
            "grace_until": 9000,
            "paid_grace_until": 5000,
        });
        let key = EncodingKey::from_rsa_pem(PRIV.as_bytes()).unwrap();
        let token = encode(&Header::new(Algorithm::RS256), &claims_json, &key).unwrap();
        let claims = verify_entitlement(&token, PUB, 3000).unwrap();
        assert_eq!(claims.paid_grace_until, Some(5000));
        assert_eq!(claims.grace_until, 9000);
    }

    #[test]
    fn rejects_past_grace_window() {
        let token = sign(2000, 9000);
        let err = verify_entitlement(&token, PUB, 9001).unwrap_err();
        assert!(matches!(err, EntitlementError::GraceExpired));
    }

    #[test]
    fn rejects_tampered_token() {
        let token = sign(2000, 9000) + "tamper";
        assert!(verify_entitlement(&token, PUB, 3000).is_err());
    }

    #[test]
    fn rejects_invalid_public_key() {
        let token = sign(2000, 9000);
        let bad = "-----BEGIN PUBLIC KEY-----\nnot-a-real-key\n-----END PUBLIC KEY-----\n";
        assert!(verify_entitlement(&token, bad, 3000).is_err());
    }
}
