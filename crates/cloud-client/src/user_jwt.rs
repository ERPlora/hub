//! Verificación del **access JWT de usuario** emitido por el Cloud Portal (ARQUITECTURA.md §2.3).
//!
//! El Cloud firma los tokens con **RS256** (`rest_framework_simplejwt`, `SIGNING_KEY=PRIVATE_KEY`);
//! el Hub los verifica **offline** contra la clave pública (`GET /api/v1/auth/public-key/`). El
//! token lleva identidad — claim `user_id` (= `User.id`) + `exp` (1h) + `token_type` — **no**
//! permisos ni hub. Por eso esto solo autentica *quién* es el usuario; el alcance de permisos en
//! el hub es un problema aparte (no resuelto en el token).
use jsonwebtoken::{decode, Algorithm, DecodingKey, Validation};
use serde::Deserialize;

/// Pertenencia a un hub declarada en el JWT (claim *coarse* `hubs`, ADR-0157). El Hub solo mira
/// `id` para su **gate de presencia** (`hub_id ∈ payload.hubs`); `org` es informativo (a qué
/// organización del SaaS pertenece ese hub) y no lo usa el gate.
#[derive(Debug, Clone, Deserialize, PartialEq, Eq)]
pub struct HubMembership {
    pub id: String,
    #[serde(default)]
    pub org: String,
}

/// Pertenencia a una organización del SaaS declarada en el JWT (claim `organizations`, ADR-0157):
/// `{id, role}` con el rol del usuario EN esa organización (owner/admin/…). El SaaS ya lo emite
/// (`CustomTokenObtainPairSerializer.get_token`); es lo que permite al Hub saber con qué rol entra
/// alguien sin preguntar nada.
#[derive(Debug, Clone, Deserialize, PartialEq, Eq)]
pub struct OrgMembership {
    pub id: String,
    #[serde(default)]
    pub role: String,
}

/// Claims verificadas del access token. `user_id` se deja como `Value` porque SimpleJWT emite el
/// PK crudo (entero o uuid según el modelo `User`); usa [`UserClaims::user_id_str`].
#[derive(Debug, Clone, Deserialize)]
pub struct UserClaims {
    pub user_id: serde_json::Value,
    #[serde(default)]
    pub token_type: String,
    pub exp: i64,
    /// Email del usuario (claim del payload SaaS, ADR-0157). El Hub lo usa para **enlazar** el login
    /// con el `hub_user` **sembrado** (owner del env) o **invitado** por el admin, cuando ese
    /// `hub_user` aún no tiene `cloud_user_id`. **`#[serde(default)]`**: un token sin el claim →
    /// cadena vacía (el enlace por email se salta y se cae al provisioning por rol por defecto).
    #[serde(default)]
    pub email: String,
    /// Hubs a los que pertenece el usuario (claim *coarse* `hubs: [{id, org}]`, ADR-0157). El Hub
    /// lo usa para el gate de presencia. **`#[serde(default)]`**: los tokens emitidos por un SaaS
    /// previo a ADR-0157 no lo traen → lista vacía (no es miembro de nada → el gate rechaza).
    #[serde(default)]
    pub hubs: Vec<HubMembership>,
    /// Organizaciones del usuario con su ROL (claim `organizations: [{id, role}]`, ADR-0157).
    /// **`#[serde(default)]`**: un SaaS anterior no lo trae → lista vacía → sin rol, y se cae al
    /// rol por defecto de siempre. Nunca debe impedir el login.
    #[serde(default)]
    pub organizations: Vec<OrgMembership>,
}

impl UserClaims {
    /// `user_id` como cadena (sirve igual si el PK es entero o uuid).
    pub fn user_id_str(&self) -> String {
        match &self.user_id {
            serde_json::Value::String(s) => s.clone(),
            other => other.to_string(),
        }
    }

    /// **Gate de presencia (ADR-0157):** ¿está `hub_id` en el claim `hubs` del token? El Hub solo
    /// deja entrar si el hub de esta máquina figura en la membresía del usuario. Un token sin el
    /// claim (SaaS legacy) tiene `hubs` vacío → siempre `false` (rechazo, se pide invitación).
    pub fn is_member_of_hub(&self, hub_id: &str) -> bool {
        self.hubs.iter().any(|h| h.id == hub_id)
    }

    /// Rol del usuario en la ORGANIZACIÓN dueña de `hub_id`, si el token lo dice.
    ///
    /// El SaaS manda las dos piezas por separado —`hubs: [{id, org}]` y
    /// `organizations: [{id, role}]`— y cruzarlas da el rol sin tocar el SaaS. Hasta ahora el Hub
    /// solo leía `hubs`, así que el rol se perdía y **un admin de la organización entraba en su
    /// propio hub con el rol de mínimo privilegio**, sin poder administrarlo ni arreglarlo desde
    /// dentro (solo el email sembrado al desplegar tenía privilegio).
    ///
    /// Devuelve `None` —y el llamador cae al rol por defecto— cuando el hub no está en el token
    /// (el gate de presencia ya lo rechaza), cuando su `org` no figura en `organizations`, o
    /// cuando el token es de un SaaS anterior que no manda el claim. Es deliberado: sin saber el
    /// rol, lo seguro es no conceder nada.
    pub fn role_for_hub(&self, hub_id: &str) -> Option<String> {
        let org = &self.hubs.iter().find(|h| h.id == hub_id)?.org;
        if org.is_empty() {
            return None;
        }
        self.organizations
            .iter()
            .find(|o| &o.id == org)
            .map(|o| o.role.clone())
            .filter(|r| !r.is_empty())
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

#[cfg(test)]
mod tests {
    use super::*;
    use jsonwebtoken::{encode, Algorithm, EncodingKey, Header};
    use serde_json::json;

    // Par de claves RSA de prueba (idéntico al usado en `entitlement.rs`): el SaaS firma con la
    // privada, el Hub verifica con la pública.
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

    fn sign(claims: serde_json::Value) -> String {
        let key = EncodingKey::from_rsa_pem(PRIV.as_bytes()).unwrap();
        encode(&Header::new(Algorithm::RS256), &claims, &key).unwrap()
    }

    /// ADR-0157: el JWT lleva el claim *coarse* `hubs: [{id, org}]`. El Hub lo parsea y puede
    /// preguntar si el hub de esta máquina está presente (gate de presencia).
    #[test]
    fn hubs_claim_parses_and_membership_check() {
        let token = sign(json!({
            "user_id": 123,
            "token_type": "access",
            "exp": 9_999_999_999_i64,
            "organizations": [{"id": "org-A", "role": "owner"}],
            "hubs": [{"id": "hub-1", "org": "org-A"}, {"id": "hub-9", "org": "org-B"}],
        }));
        let claims = verify_user_jwt(&token, PUB).unwrap();
        assert_eq!(claims.hubs.len(), 2);
        assert!(claims.is_member_of_hub("hub-1"), "hub-1 está en el payload");
        assert!(claims.is_member_of_hub("hub-9"), "hub-9 está en el payload");
        assert!(
            !claims.is_member_of_hub("hub-x"),
            "hub-x NO está en el payload"
        );
    }

    /// ADR-0157 (corrección owner): el JWT lleva el `email` del usuario (payload de ejemplo del
    /// ADR: `{"sub":…,"email":"ana@bar.com",…}`). El Hub lo usa para ENLAZAR el login con el
    /// `hub_user` sembrado/invitado por email. Un token sin `email` parsea a cadena vacía.
    #[test]
    fn email_claim_parses_and_defaults_empty() {
        let token = sign(json!({
            "user_id": 123,
            "email": "ana@bar.com",
            "token_type": "access",
            "exp": 9_999_999_999_i64,
            "hubs": [{"id": "hub-1", "org": "org-A"}],
        }));
        let claims = verify_user_jwt(&token, PUB).unwrap();
        assert_eq!(claims.email, "ana@bar.com", "el email del payload se parsea");

        // Sin claim `email` → cadena vacía (retrocompat).
        let no_email = sign(json!({
            "user_id": 7,
            "token_type": "access",
            "exp": 9_999_999_999_i64,
        }));
        let claims = verify_user_jwt(&no_email, PUB).unwrap();
        assert!(claims.email.is_empty(), "sin `email` → cadena vacía");
    }


    /// El SaaS **ya manda** el rol: `organizations: [{id, role}]` junto a `hubs: [{id, org}]`
    /// (`CustomTokenObtainPairSerializer.get_token`). El Hub no lo leía, así que un admin de la
    /// organización entraba con el rol de mínimo privilegio y no podía administrar su propio hub.
    /// Cruzando el `org` del hub con `organizations` sale el rol sin tocar el SaaS.
    #[test]
    fn role_for_hub_cruza_el_org_del_hub_con_las_organizaciones() {
        let token = sign(json!({
            "user_id": 7,
            "token_type": "access",
            "exp": 9_999_999_999_i64,
            "organizations": [{"id": "org-1", "role": "admin"}, {"id": "org-2", "role": "employee"}],
            "hubs": [{"id": "hub-a", "org": "org-1"}, {"id": "hub-b", "org": "org-2"}],
        }));
        let claims = verify_user_jwt(&token, PUB).unwrap();
        assert_eq!(claims.role_for_hub("hub-a").as_deref(), Some("admin"));
        assert_eq!(claims.role_for_hub("hub-b").as_deref(), Some("employee"));
    }

    /// Un hub que no está en el token no da rol: el gate de presencia ya lo rechaza, y devolver
    /// algo aquí sería conceder privilegio a un hub del que no se es miembro.
    #[test]
    fn role_for_hub_de_un_hub_ajeno_no_da_nada() {
        let token = sign(json!({
            "user_id": 7, "token_type": "access", "exp": 9_999_999_999_i64,
            "organizations": [{"id": "org-1", "role": "owner"}],
            "hubs": [{"id": "hub-a", "org": "org-1"}],
        }));
        let claims = verify_user_jwt(&token, PUB).unwrap();
        assert_eq!(claims.role_for_hub("hub-de-otro"), None);
    }

    /// Retrocompat: un token sin `organizations` (SaaS anterior) parsea igual y no da rol, así que
    /// se cae al rol por defecto de siempre. Nunca debe romper el login.
    #[test]
    fn sin_claim_organizations_no_hay_rol_pero_el_token_vale() {
        let token = sign(json!({
            "user_id": 7, "token_type": "access", "exp": 9_999_999_999_i64,
            "hubs": [{"id": "hub-a", "org": "org-1"}],
        }));
        let claims = verify_user_jwt(&token, PUB).unwrap();
        assert!(claims.organizations.is_empty());
        assert_eq!(claims.role_for_hub("hub-a"), None);
        assert!(claims.is_member_of_hub("hub-a"), "el gate de presencia sigue funcionando");
    }

    /// Un hub cuyo `org` no figura en `organizations` tampoco da rol: sin saber el rol, lo seguro
    /// es no conceder nada y dejar que decida el rol por defecto.
    #[test]
    fn un_org_desconocido_no_concede_rol() {
        let token = sign(json!({
            "user_id": 7, "token_type": "access", "exp": 9_999_999_999_i64,
            "organizations": [{"id": "otra", "role": "owner"}],
            "hubs": [{"id": "hub-a", "org": "org-1"}],
        }));
        let claims = verify_user_jwt(&token, PUB).unwrap();
        assert_eq!(claims.role_for_hub("hub-a"), None);
    }

    /// Retrocompat: un token viejo (SaaS previo a ADR-0157) NO trae `hubs`. Debe parsear igual
    /// (lista vacía) y no reconocer a nadie como miembro (el gate lo rechazará).
    #[test]
    fn old_token_without_hubs_claim_parses_empty() {
        let token = sign(json!({
            "user_id": 7,
            "token_type": "access",
            "exp": 9_999_999_999_i64,
        }));
        let claims = verify_user_jwt(&token, PUB).unwrap();
        assert!(claims.hubs.is_empty(), "sin claim `hubs` → lista vacía");
        assert!(
            !claims.is_member_of_hub("hub-1"),
            "token sin `hubs` no es miembro de ningún hub"
        );
    }
}
