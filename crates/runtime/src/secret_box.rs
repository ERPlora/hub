//! Envelope encryption at-rest para secretos del Hub (ERPlora/hub#114).
//!
//! Primer consumidor: `certificate.rs` (`_hub_certificate.pkcs12_b64`/`password`, el `.p12` fiscal
//! del negocio — con esto se firma ante la AEAT). Quien lea la BD ya no puede firmar en nombre del
//! negocio: el blob solo se puede abrir con la master key, que vive FUERA de la BD (env), nunca al
//! lado del dato que protege.
//!
//! **Esquema:** AES-256-GCM vía `ring` (ya resuelto en `Cargo.lock` — lo trae `rustls`/`reqwest`
//! transitivamente para TLS; no se añade una dependencia nueva al árbol, solo se declara directa).
//! Precedente de diseño ([ADR-0016](../../../architecture/00-overview/decision-log.md#adr-0016) —
//! cifrado en reposo de secretos del SaaS = Fernet + master key en env): ADR-0016 cubre hoy el lado
//! **Cloud/SaaS** (API keys LLM, token de WhatsApp); el lado **Hub** queda explícitamente abierto
//! ([ADR-0148](../../../architecture/00-overview/decision-log.md), precondición 2: *"Secret store
//! cifrado at-rest en el Hub (ADR-0016 sigue abierto)"*). Este módulo aplica el mismo PRINCIPIO
//! (master key fuera de la BD, en el entorno) con el primitivo AEAD nativo de Rust ya presente en
//! el árbol en vez de Fernet (no hay crate `fernet` en el workspace y añadir una dependencia nueva
//! de cripto para esto no está justificado). **A validar con el humano:** si se prefiere unificar
//! el esquema exacto con el del SaaS más adelante, o mantenerlos independientes (Cloud=Python/Fernet,
//! Hub=Rust/AES-GCM) — ver el informe final de `hub#114`.
//!
//! **Formato almacenado, versionado:** `v1:` + base64-estándar(nonce[12] || ciphertext || tag).
//! El prefijo permite rotar de esquema en el futuro (`v2:` conviviría con `v1:` sin migración
//! bloqueante). La detección de "¿está cifrado?" NO es solo el prefijo, es ESTRUCTURAL
//! ([`is_encrypted`]/`parse_envelope`): para `pkcs12_b64` legacy el prefijo bastaría (base64 nunca
//! contiene `:`), pero el `password` legacy es texto libre y podría empezar por `v1:` por
//! casualidad — se exige además base64 válido de al menos nonce+tag bytes tras el prefijo.
//!
//! **Compatibilidad con filas legacy (en claro, sin prefijo):** [`decrypt_or_legacy`] las devuelve
//! tal cual — LEER nunca exige master key para datos viejos. Volver a ESCRIBIR esa fila (p. ej. subir
//! un certificado de reemplazo) sí exige la master key y la cifra: la migración de filas legacy es
//! **perezosa, en el próximo write** (más simple y segura que una migración de arranque: no ejecuta
//! escrituras como efecto lateral de una lectura, no necesita permiso de escritura en rutas de solo
//! lectura, y no bloquea el arranque del hub si la clave llega tarde). **A validar con el humano:**
//! si se prefiere además una migración explícita de arranque (barrido de filas legacy) para no
//! depender de que alguien vuelva a subir el certificado.

use base64::Engine as _;
use ring::aead::{Aad, LessSafeKey, Nonce, UnboundKey, AES_256_GCM, NONCE_LEN};
use ring::rand::{SecureRandom, SystemRandom};

/// Nombre de la variable de entorno con la master key (AES-256, 32 bytes, base64-estándar).
/// Provisioning: el operador la genera UNA vez (`openssl rand -base64 32`) y la inyecta como
/// secreto del contenedor del Hub (mismo mecanismo que `HUB_CLOUD_API_TOKEN`/`HUB_JWT_PUBLIC_KEY`,
/// `crates/server/src/state.rs`); NUNCA se genera ni se guarda en la propia BD (eso no protegería
/// nada: la clave estaría al lado del secreto que cifra).
pub const MASTER_KEY_ENV: &str = "HUB_SECRETS_KEY";

const KEY_LEN: usize = 32; // AES-256
const PREFIX: &str = "v1:";

#[derive(Debug, thiserror::Error)]
pub enum SecretBoxError {
    #[error("{0} no está definida: no se puede cifrar/leer un secreto sin master key (ADR-0016, hub#114)")]
    MissingKey(&'static str),
    #[error("{0} inválida: {1}")]
    InvalidKey(&'static str, String),
    #[error("no se pudo descifrar: clave incorrecta o dato corrupto")]
    Decrypt,
    #[error("no se pudo cifrar: {0}")]
    Encrypt(String),
}

/// Master key de 32 bytes (AES-256) para [`encrypt`]/[`decrypt`]. Se construye SOLO desde
/// [`MASTER_KEY_ENV`] ([`master_key_from_env`]) o, en tests, con [`SecretsKey::for_test`].
pub struct SecretsKey([u8; KEY_LEN]);

impl std::fmt::Debug for SecretsKey {
    /// Redactado a propósito: un `{:?}` de `Result<Option<SecretsKey>, _>` (p.ej. en un
    /// `.unwrap()`/`.expect()` de test que falla) NUNCA debe imprimir los bytes de la clave.
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_tuple("SecretsKey").field(&"<redacted>").finish()
    }
}

impl SecretsKey {
    #[cfg(test)]
    pub(crate) fn for_test(fill: u8) -> Self {
        Self([fill; KEY_LEN])
    }

    fn less_safe_key(&self) -> LessSafeKey {
        // `AES_256_GCM.key_len() == KEY_LEN` está garantizado por el tipo (array de KEY_LEN
        // bytes): `UnboundKey::new` solo puede fallar si la longitud no casa con el algoritmo.
        let unbound = UnboundKey::new(&AES_256_GCM, &self.0)
            .expect("SecretsKey siempre tiene 32 bytes, la longitud exacta de AES_256_GCM");
        LessSafeKey::new(unbound)
    }
}

/// Lee y valida la master key desde [`MASTER_KEY_ENV`]. `Ok(None)` si la variable no está
/// definida (o está vacía) — el LLAMADOR decide la política (fail-closed en escritura, permisivo
/// en lectura de filas legacy). `Err` si está definida pero no es una clave válida (base64 de
/// exactamente 32 bytes): un typo del operador debe fallar claro, no silenciarse como "sin clave".
pub fn master_key_from_env() -> Result<Option<SecretsKey>, SecretBoxError> {
    key_from_env_var(MASTER_KEY_ENV)
}

fn key_from_env_var(name: &'static str) -> Result<Option<SecretsKey>, SecretBoxError> {
    let raw = match std::env::var(name) {
        Ok(v) if !v.trim().is_empty() => v,
        _ => return Ok(None),
    };
    let bytes = base64::engine::general_purpose::STANDARD
        .decode(raw.trim())
        .map_err(|e| SecretBoxError::InvalidKey(name, format!("no es base64 válido: {e}")))?;
    let len = bytes.len();
    let key: [u8; KEY_LEN] = bytes.try_into().map_err(|_| {
        SecretBoxError::InvalidKey(
            name,
            format!("debe decodificar a {KEY_LEN} bytes (AES-256); decodificó a {len}"),
        )
    })?;
    Ok(Some(SecretsKey(key)))
}

/// Bytes del envelope (`nonce || ciphertext || tag`) si `value` parsea ESTRUCTURALMENTE como el
/// formato de este módulo; `None` en caso contrario (→ el valor es legacy/en claro). El prefijo
/// `v1:` solo no basta: el `pkcs12_b64` legacy es base64 (nunca contiene `:`), pero el password
/// legacy es TEXTO LIBRE y podría empezar por `v1:` por casualidad — se exige además que el resto
/// sea base64-estándar válido con al menos nonce+tag bytes (el mínimo que [`encrypt`] produce,
/// incluso con plaintext vacío). Riesgo residual documentado: un password legacy que sea
/// literalmente `v1:` + base64 válido de ≥28 bytes se malinterpretaría — combinación tan
/// improbable que no justifica una migración de datos; el remedio operativo es resubir el
/// certificado.
fn parse_envelope(value: &str) -> Option<Vec<u8>> {
    let b64 = value.strip_prefix(PREFIX)?;
    let raw = base64::engine::general_purpose::STANDARD.decode(b64).ok()?;
    if raw.len() < NONCE_LEN + AES_256_GCM.tag_len() {
        return None;
    }
    Some(raw)
}

/// `true` si `value` ya está en el formato cifrado de este módulo (envelope `v1:` estructuralmente
/// válido — ver [`parse_envelope`]).
pub fn is_encrypted(value: &str) -> bool {
    parse_envelope(value).is_some()
}

/// Cifra `plaintext` con `key` → `v1:` + base64(nonce || ciphertext || tag). Nonce aleatorio de
/// 12 bytes por llamada (requisito de unicidad de AES-GCM; nunca se reutiliza un nonce con la
/// misma clave).
pub fn encrypt(key: &SecretsKey, plaintext: &str) -> Result<String, SecretBoxError> {
    let rng = SystemRandom::new();
    let mut nonce_bytes = [0u8; NONCE_LEN];
    rng.fill(&mut nonce_bytes)
        .map_err(|_| SecretBoxError::Encrypt("no se pudo generar el nonce aleatorio".into()))?;
    let nonce = Nonce::assume_unique_for_key(nonce_bytes);

    let mut in_out = plaintext.as_bytes().to_vec();
    key.less_safe_key()
        .seal_in_place_append_tag(nonce, Aad::empty(), &mut in_out)
        .map_err(|_| SecretBoxError::Encrypt("fallo del cifrado AEAD".into()))?;

    let mut blob = Vec::with_capacity(NONCE_LEN + in_out.len());
    blob.extend_from_slice(&nonce_bytes);
    blob.extend_from_slice(&in_out);
    Ok(format!(
        "{PREFIX}{}",
        base64::engine::general_purpose::STANDARD.encode(blob)
    ))
}

/// Descifra un envelope ya parseado por [`parse_envelope`] (`nonce || ciphertext || tag`).
/// `Err(Decrypt)` uniforme ante cualquier fallo (tag/autenticación inválida, UTF-8 inválido tras
/// abrir) — no hay que distinguirle al llamador *por qué* falló: "clave incorrecta o dato corrupto"
/// es toda la información que un atacante no debería poder usar para adivinar nada más, y toda la
/// que un operador necesita para saber qué mirar (¿la clave es la correcta? ¿el dato se corrompió?).
fn decrypt_raw(key: &SecretsKey, raw: &[u8]) -> Result<String, SecretBoxError> {
    debug_assert!(raw.len() >= NONCE_LEN + AES_256_GCM.tag_len());
    let (nonce_bytes, ciphertext) = raw.split_at(NONCE_LEN);
    let nonce =
        Nonce::try_assume_unique_for_key(nonce_bytes).map_err(|_| SecretBoxError::Decrypt)?;

    let mut in_out = ciphertext.to_vec();
    let plain = key
        .less_safe_key()
        .open_in_place(nonce, Aad::empty(), &mut in_out)
        .map_err(|_| SecretBoxError::Decrypt)?;
    String::from_utf8(plain.to_vec()).map_err(|_| SecretBoxError::Decrypt)
}

/// Descifra con compatibilidad hacia atrás: las filas escritas ANTES de este fix (`hub#114`) están
/// en claro y NO parsean como envelope ([`parse_envelope`]) — se devuelven TAL CUAL, sin exigir
/// master key (leer datos legacy nunca debe romperse por no tener clave). Solo las filas YA
/// cifradas la exigen; si falta, el error es explícito. Nunca hay fallback de "descifrado fallido →
/// devolver el valor tal cual": eso enmascararía una clave mal rotada devolviendo ciphertext como
/// si fuera la contraseña.
pub fn decrypt_or_legacy(key: Option<&SecretsKey>, value: &str) -> Result<String, SecretBoxError> {
    let Some(raw) = parse_envelope(value) else {
        return Ok(value.to_string());
    };
    let key = key.ok_or(SecretBoxError::MissingKey(MASTER_KEY_ENV))?;
    decrypt_raw(key, &raw)
}

/// Helpers de test compartidos con `certificate.rs`: serializar el acceso a la variable de
/// entorno global `HUB_SECRETS_KEY` entre tests que corren en paralelo (`cargo test` multi-hilo).
#[cfg(test)]
pub(crate) mod test_support {
    use std::sync::{Mutex, MutexGuard, OnceLock};

    /// Un solo `Mutex` para TODOS los tests (de este módulo y de `certificate.rs`) que tocan
    /// `HUB_SECRETS_KEY`: la env var es estado global del proceso, así que dos tests mutándola en
    /// paralelo se pisarían de forma no determinista sin esto.
    pub(crate) fn env_lock() -> MutexGuard<'static, ()> {
        static LOCK: OnceLock<Mutex<()>> = OnceLock::new();
        LOCK.get_or_init(|| Mutex::new(()))
            .lock()
            .unwrap_or_else(|e| e.into_inner())
    }

    /// Base64-estándar de 32 bytes rellenos con `fill` — valor válido para `HUB_SECRETS_KEY` en
    /// tests de otros módulos (p.ej. `certificate.rs`) que no construyen un [`super::SecretsKey`]
    /// directamente porque ejercitan el camino real (env var → `set`/`load_pkcs12`).
    pub(crate) fn test_key_b64(fill: u8) -> String {
        use base64::Engine as _;
        base64::engine::general_purpose::STANDARD.encode([fill; super::KEY_LEN])
    }

    /// RAII: fija (o borra con [`EnvVarGuard::unset`]) `HUB_SECRETS_KEY` y restaura el valor
    /// previo al salir de scope — incluso si el test entra en pánico a mitad, para no filtrar
    /// estado a los tests siguientes.
    pub(crate) struct EnvVarGuard {
        prev: Option<String>,
    }

    impl EnvVarGuard {
        pub(crate) fn set(value: &str) -> Self {
            let prev = std::env::var(super::MASTER_KEY_ENV).ok();
            // SAFETY: el llamador mantiene el guard de `env_lock()` durante toda la vida de este
            // `EnvVarGuard`, así que ningún otro hilo de test lee/escribe esta env var a la vez.
            unsafe { std::env::set_var(super::MASTER_KEY_ENV, value) };
            Self { prev }
        }

        pub(crate) fn unset() -> Self {
            let prev = std::env::var(super::MASTER_KEY_ENV).ok();
            // SAFETY: idem `set` — serializado por `env_lock()`.
            unsafe { std::env::remove_var(super::MASTER_KEY_ENV) };
            Self { prev }
        }
    }

    impl Drop for EnvVarGuard {
        fn drop(&mut self) {
            // SAFETY: idem `set` — serializado por `env_lock()` (el guard vive hasta después de
            // este `drop`, porque el test lo declara ANTES que el `EnvVarGuard`, y Rust libera en
            // orden inverso de declaración).
            unsafe {
                match &self.prev {
                    Some(v) => std::env::set_var(super::MASTER_KEY_ENV, v),
                    None => std::env::remove_var(super::MASTER_KEY_ENV),
                }
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::test_support::{env_lock, EnvVarGuard};
    use super::*;

    #[test]
    fn roundtrip_returns_original_plaintext() {
        let key = SecretsKey::for_test(7);
        let encrypted = encrypt(&key, "s3cr3t-p12-password").unwrap();
        assert!(is_encrypted(&encrypted));
        assert_eq!(
            decrypt_or_legacy(Some(&key), &encrypted).unwrap(),
            "s3cr3t-p12-password"
        );
    }

    #[test]
    fn ciphertext_never_contains_the_plaintext() {
        let key = SecretsKey::for_test(1);
        let encrypted = encrypt(&key, "MUY-SECRETO-123").unwrap();
        assert!(!encrypted.contains("MUY-SECRETO-123"));
        assert!(encrypted.starts_with("v1:"));
    }

    #[test]
    fn two_encryptions_of_the_same_plaintext_differ() {
        // Nonce aleatorio por llamada: nunca se repite el blob para el mismo secreto (protege
        // contra fuga por comparación entre filas / rotación posterior).
        let key = SecretsKey::for_test(2);
        let a = encrypt(&key, "same-secret").unwrap();
        let b = encrypt(&key, "same-secret").unwrap();
        assert_ne!(a, b);
    }

    #[test]
    fn wrong_key_fails_cleanly_not_panics() {
        let right = SecretsKey::for_test(9);
        let wrong = SecretsKey::for_test(10);
        let encrypted = encrypt(&right, "top-secret").unwrap();
        let err = decrypt_or_legacy(Some(&wrong), &encrypted).unwrap_err();
        assert!(matches!(err, SecretBoxError::Decrypt));
    }

    #[test]
    fn tampered_ciphertext_fails_authentication() {
        let key = SecretsKey::for_test(3);
        let encrypted = encrypt(&key, "top-secret").unwrap();
        // Voltea TODOS los bits del último byte (parte del tag GCM, al final del blob) — a
        // diferencia de tocar el último carácter base64 (podría coincidir por azar con el nonce
        // aleatorio y no cambiar nada), un XOR con 0xFF garantiza un byte distinto siempre.
        let b64 = encrypted.strip_prefix("v1:").unwrap();
        let mut raw = base64::engine::general_purpose::STANDARD
            .decode(b64)
            .unwrap();
        let last = raw.len() - 1;
        raw[last] ^= 0xFF;
        let tampered = format!(
            "v1:{}",
            base64::engine::general_purpose::STANDARD.encode(raw)
        );

        let err = decrypt_or_legacy(Some(&key), &tampered).unwrap_err();
        assert!(matches!(err, SecretBoxError::Decrypt));
    }

    #[test]
    fn legacy_plaintext_passes_through_unchanged_even_without_key() {
        let legacy = "contraseña-en-claro-de-antes-del-fix";
        assert!(!is_encrypted(legacy));
        assert_eq!(decrypt_or_legacy(None, legacy).unwrap(), legacy);
    }

    #[test]
    fn legacy_password_that_merely_starts_with_v1_passes_through() {
        // El password legacy es TEXTO LIBRE (a diferencia del pkcs12_b64, que es base64 y nunca
        // contiene `:`): puede empezar por "v1:" sin ser un envelope nuestro. Solo un valor que
        // parsea ESTRUCTURALMENTE como envelope (base64-estándar válido tras el prefijo, con al
        // menos nonce+tag bytes) se trata como cifrado; el resto pasa como legacy, con o sin clave.
        let key = SecretsKey::for_test(11);
        for legacy in ["v1:mi-contraseña", "v1:", "v1:no base64!", "v1:QQ=="] {
            assert!(
                !is_encrypted(legacy),
                "malinterpretado como cifrado: {legacy:?}"
            );
            assert_eq!(decrypt_or_legacy(Some(&key), legacy).unwrap(), legacy);
            assert_eq!(decrypt_or_legacy(None, legacy).unwrap(), legacy);
        }
    }

    #[test]
    fn encrypted_value_without_key_fails_explicitly() {
        let key = SecretsKey::for_test(4);
        let encrypted = encrypt(&key, "secreto").unwrap();
        let err = decrypt_or_legacy(None, &encrypted).unwrap_err();
        assert!(matches!(err, SecretBoxError::MissingKey(name) if name == MASTER_KEY_ENV));
    }

    #[test]
    fn master_key_from_env_absent_is_none() {
        let _lock = env_lock();
        let _guard = EnvVarGuard::unset();
        assert!(master_key_from_env().unwrap().is_none());
    }

    #[test]
    fn master_key_from_env_valid_base64_32_bytes() {
        let _lock = env_lock();
        let raw = [42u8; KEY_LEN];
        let b64 = base64::engine::general_purpose::STANDARD.encode(raw);
        let _guard = EnvVarGuard::set(&b64);
        let key = master_key_from_env().unwrap().expect("clave presente");
        // Cifra/descifra con ella para comprobar que se decodificó bien (sin exponer los bytes
        // internos: `SecretsKey` no implementa Debug/PartialEq a propósito).
        let encrypted = encrypt(&key, "check").unwrap();
        assert_eq!(decrypt_or_legacy(Some(&key), &encrypted).unwrap(), "check");
    }

    #[test]
    fn master_key_from_env_invalid_base64_errs() {
        let _lock = env_lock();
        let _guard = EnvVarGuard::set("no-es-base64-válido-!!!");
        let err = master_key_from_env().unwrap_err();
        assert!(matches!(err, SecretBoxError::InvalidKey(_, _)));
    }

    #[test]
    fn master_key_from_env_wrong_length_errs() {
        let _lock = env_lock();
        let short = base64::engine::general_purpose::STANDARD.encode([1u8; 16]);
        let _guard = EnvVarGuard::set(&short);
        let err = master_key_from_env().unwrap_err();
        assert!(matches!(err, SecretBoxError::InvalidKey(_, _)));
    }
}
