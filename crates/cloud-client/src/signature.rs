//! Firma criptográfica de módulos (ed25519, detached) — hub#239.
//!
//! Históricamente `erplora sign` solo (re)calculaba un SHA256 del `module.zip`: eso prueba
//! **integridad de transporte**, NO **autoría**. Cualquiera con acceso de escritura a la caché
//! de descargas, a `HUB_MODULES_DIR` o al propio zip publicado podía reemplazarlo por código
//! propio (migraciones SQL + handlers WASM) y el hub lo ejecutaba. Esta es la verificación real
//! que falta: el **publicador** firma el bundle con una clave ed25519 del marketplace y el hub
//! **verifica la firma** contra un anillo de claves públicas de confianza ANTES de instalar.
//!
//! Esquema: **ed25519** (RFC 8032) vía [`ring`]. La firma es **detached**: 64 bytes que cubren
//! TODOS los bytes del `module.zip`. Es la pieza que el ARQUITECTURA.md siempre describió
//! (§2.2: «Verificar firma + SHA256»; §7.4: `erplora module sign  # firma + SHA256`) pero que
//! nunca se cableó — solo existía el SHA256.
//!
//! ## Modelo de confianza
//!
//! - El hub mantiene un **anillo de claves públicas de confianza** ([`TrustedKeyRing`]): las
//!   claves ed25519 (32 bytes) cuyo firmante acepta. Default **deny-all**: si el anillo está
//!   vacío, NINGÚN módulo verifica (fail-closed). En producción se carga de `HUB_MODULE_TRUSTED_KEYS`
//!   (ver [`TrustedKeyRing::from_env`]).
//! - La política por defecto es [`SignaturePolicy::Enforce`]: un módulo sin firma, o firmado por
//!   una clave que no está en el anillo, se **rechaza**.
//! - [`SignaturePolicy::DevTrust`] es el **escape hatch de desarrollo** explícito: acepta módulos
//!   sin firma. Solo debe construirse tras un flag explícito (`HUB_DEV_MODE`); NUNCA es el
//!   default. Así `install {dir}` y los módulos horneados siguen siendo instalables en local sin
//!   firmar nada, pero la imagen de producción (sin el flag) los rechaza.
//!
//! ## TODO (distribución de claves — fuera de alcance de este fix)
//!
//! La rotación/revocación de claves, el fetch del anillo desde el Cloud Portal y la identidad del
//! publicador por módulo quedan como trabajo pendiente (ver §«Lo que falta» en el commit). Hoy el
//! anillo es estático y configurable por env; rotar exige redistribuir el env, pero el DEFAULT es
//! deny y cualquier módulo del marketplace quedará bloqueado hasta que el anillo lleve la clave
//! del marketplace — que es exactamente el invariante de seguridad que faltaba.
//!
//! ## Port a `erplora sign` (toolkit — ERPlora/module-toolkit, repo EXTERNO)
//!
//! La función [`Signer`] es la implementación de referencia del firmante. El `erplora sign` real
//! vive en `module-toolkit/src/pack.mjs` (otro repo, fuera del alcance de este fix) y hoy solo
//! recalcula SHA256. El puerto Node es directo con cualquier lib ed25519 (p. ej. `@noble/ed25519`
//! o `tweetnacl`), y debe producir un JSON [`ModuleSignature`] `{ key_id, sig_b64 }` y escribirlo
//! junto al zip:
//!
//! ```text
//! // erplora sign (esquema, ~15 líneas):
//! //   1. leer build/<id>-v<ver>.zip como bytes
//! //   2. cargar el seed/privada del marketplace (env/secret manager): 32 bytes
//! //   3. sig = ed25519.sign(zipBytes, privateKey)            // 64 bytes detached
//! //   4. escribir build/<id>-v<ver>.zip.sig = JSON { key_id, sig_b64: base64(sig) }
//! //   5. el SaaS expone esa signature en versions/ (campo `signature` del ModuleVersion)
//! //      para que el hub la verifique (server/src/install.rs, hub#239).
//! ```
//!
//! El PKCS#8 del marketplace se genera UNA VEZ con [`Signer::generate`] y su pública
//! ([`Signer::public_key`], hex/base64) se distribuye a los hubs vía `HUB_MODULE_TRUSTED_KEYS`.
//! El formato de la firma (base64 de 64 bytes, clave cruda de 32 bytes) es el de RFC 8032 y casa
//! con cualquier implementación ed25519 estándar — por eso el toolkit Node y el verificador Rust
//! (`ring`) son interoperables sin puente de formato.
use base64::Engine;
use ring::signature::{Ed25519KeyPair, KeyPair, UnparsedPublicKey, ED25519};

/// Longitud de una clave pública ed25519 (bytes). Constante de `ring`.
pub const PUBLIC_KEY_LEN: usize = 32;
/// Longitud de una firma ed25519 detached (bytes). Constante de `ring`.
pub const SIGNATURE_LEN: usize = 64;

/// Error de verificación de firma. Estable, legible y `PartialEq` (para tests).
#[derive(Debug, Clone, PartialEq, Eq, thiserror::Error)]
pub enum SignatureError {
    /// La firma no valida contra ninguna clave de confianza (firma falsa o clave ajena).
    #[error("firma del módulo inválida: no valida contra ninguna clave de confianza")]
    Invalid,
    /// El módulo no trae firma y la política es `Enforce`.
    #[error("módulo sin firma: la política exige firma verificada (hub#239)")]
    Missing,
    /// La firma viniera mal codificada (no es base64/hex de 64 bytes).
    #[error("firma mal codificada ({0})")]
    BadEncoding(String),
    /// Una clave del anillo no es un pubkey ed25519 válido (32 bytes).
    #[error("clave de confianza mal codificada ({0})")]
    BadKey(String),
}

/// Identificador opaco del par de claves que firma (lo elige el publicador; típicamente un
/// key-id corto o el slug del marketplace). Viaja junto a la firma para que el verificador sepa
/// qué clave probar primero y para trazabilidad.
#[derive(Debug, Clone, PartialEq, Eq, serde::Serialize, serde::Deserialize)]
pub struct ModuleSignature {
    /// Id de la clave (humano/opaco). No se usa para confiar — solo para selección/registro.
    pub key_id: String,
    /// Firma ed25519 detached de 64 bytes, **base64 (standard)**. Cubre los bytes del `module.zip`.
    pub sig_b64: String,
}

impl ModuleSignature {
    /// Construye la firma a partir de los bytes crudos (64).
    pub fn from_bytes(key_id: impl Into<String>, sig: &[u8]) -> Self {
        Self { key_id: key_id.into(), sig_b64: base64::engine::general_purpose::STANDARD.encode(sig) }
    }

    /// Decodifica la firma a sus 64 bytes crudos.
    pub fn sig_bytes(&self) -> Result<[u8; SIGNATURE_LEN], SignatureError> {
        let raw = base64::engine::general_purpose::STANDARD
            .decode(self.sig_b64.trim())
            .map_err(|e| SignatureError::BadEncoding(e.to_string()))?;
        let arr: [u8; SIGNATURE_LEN] = raw
            .as_slice()
            .try_into()
            .map_err(|_: _| {
                SignatureError::BadEncoding(format!(
                    "esperaba {SIGNATURE_LEN} bytes, llegaron {}",
                    raw.len()
                ))
            })?;
        Ok(arr)
    }
}

/// Anillo de claves públicas ed25519 de confianza. Default vacío = **deny-all**.
///
/// Una firma valida si lo hace ALGUNA de las claves del anillo (soporta rotación: dos claves
/// pueden estar activas a la vez). Vacío => ninguna firma valida => todo módulo se rechaza bajo
/// `Enforce`, que es el fail-closed correcto.
#[derive(Debug, Clone, Default)]
pub struct TrustedKeyRing {
    keys: Vec<TrustedKey>,
}

#[derive(Debug, Clone)]
struct TrustedKey {
    key_id: String,
    pk_bytes: [u8; PUBLIC_KEY_LEN],
}

impl TrustedKeyRing {
    /// Anillo vacío (deny-all). Útil para tests de «sin claves, todo rechazado».
    pub fn empty() -> Self {
        Self { keys: Vec::new() }
    }

    /// `true` si no hay claves de confianza ⇒ toda verificación bajo `Enforce` falla.
    pub fn is_empty(&self) -> bool {
        self.keys.is_empty()
    }

    /// Añade una clave pública en raw 32 bytes. Devuelve error si la longitud no es correcta.
    pub fn add_bytes(&mut self, key_id: impl Into<String>, pk: &[u8]) -> Result<(), SignatureError> {
        let key_id = key_id.into();
        let pk_bytes: [u8; PUBLIC_KEY_LEN] = pk.try_into().map_err(|_: _| {
            SignatureError::BadKey(format!(
                "clave {key_id}: esperaba {PUBLIC_KEY_LEN} bytes, llegaron {}",
                pk.len()
            ))
        })?;
        self.keys.push(TrustedKey { key_id, pk_bytes });
        Ok(())
    }

    /// Añade una clave pública codificada en **hex** (64 chars) o **base64 (standard)**.
    pub fn add_encoded(&mut self, key_id: impl Into<String>, encoded: &str) -> Result<(), SignatureError> {
        let trimmed = encoded.trim();
        let bytes = decode_hex_or_b64(trimmed)
            .map_err(|e| SignatureError::BadKey(format!("clave {trimmed}: {e}")))?;
        self.add_bytes(key_id, &bytes)
    }

    /// Carga el anillo desde la variable de entorno `HUB_MODULE_TRUSTED_KEYS`:
    /// claves separadas por coma, cada una `key_id=hex|base64` (o solo `hex|base64`, en cuyo caso
    /// el key_id es el hash corto de la clave). Espacios tolerados. Ausencia o vacío ⇒ anillo
    /// vacío (deny-all). Claves ilegibles se ignoran con WARN (mejor arrancar con menos claves
    /// que no arrancar), pero se devuelven en el conteo de errores para diagnóstico.
    ///
    /// TODO (rotación): hoy el anillo es estático por arranque. El siguiente paso es un fetch
    /// desde el Cloud + revocación; ver commit/message del fix.
    pub fn from_env(raw: Option<&str>) -> (Self, Vec<String>) {
        let Some(raw) = raw.map(str::trim).filter(|s| !s.is_empty()) else {
            return (Self::empty(), Vec::new());
        };
        let mut ring = Self::empty();
        let mut bad = Vec::new();
        for (i, entry) in raw.split(',').enumerate() {
            let entry = entry.trim();
            if entry.is_empty() {
                continue;
            }
            let res = match entry.split_once('=') {
                Some((id, key)) => ring.add_encoded(id.trim(), key),
                None => {
                    // Sin key_id: lo derivamos de un prefijo del hash de la clave para que sea estable.
                    let kid = format!("auto-{i}");
                    ring.add_encoded(&kid, entry)
                }
            };
            if let Err(e) = res {
                bad.push(format!("{entry}: {e}"));
            }
        }
        (ring, bad)
    }

    /// Verifica `sig` sobre `message` contra CUALQUIERA de las claves del anillo. Ok si alguna
    /// valida (devuelve el `key_id` de la clave que validó, para trazabilidad). Si el anillo está
    /// vacío, devuelve `Invalid` (deny-all: sin claves de confianza, nada verifica).
    fn verify(&self, sig: &ModuleSignature, message: &[u8]) -> Result<&str, SignatureError> {
        let sig_bytes = sig.sig_bytes()?;
        for key in &self.keys {
            let pk = UnparsedPublicKey::new(&ED25519, key.pk_bytes);
            if pk.verify(message, &sig_bytes).is_ok() {
                return Ok(&key.key_id);
            }
        }
        Err(SignatureError::Invalid)
    }
}

/// Política de verificación de firma al instalar un módulo.
#[derive(Debug, Clone)]
pub enum SignaturePolicy {
    /// **Default (deny).** El módulo DEBE traer una [`ModuleSignature`] válida firmada por una
    /// clave del anillo. Sin firma o firma inválida ⇒ rechazo.
    Enforce(TrustedKeyRing),
    /// **Escape hatch de desarrollo explícito.** Acepta módulos sin firma (con aviso). SOLO debe
    /// construirse tras `HUB_DEV_MODE` — nunca es el default y la imagen de prod no lo activa.
    DevTrust,
    /// **Modo `warn` de ADR-0193** — sin infraestructura de firma desplegada (anillo de confianza
    /// vacío en producción). La integridad la garantiza el **SHA256 obligatorio** del grant
    /// (ADR-0015), control vigente mientras el marketplace sea de origen único sobre TLS con rutas
    /// S3 inmutables.
    ///
    /// No es una licencia nueva: **ADR-0193 lo exige explícitamente** en sus consecuencias — «los
    /// ~24 módulos ya publicados no están firmados: hay que re-publicarlos […] **hasta entonces el
    /// Hub debe estar en `warn`, no `enforce`**». La firma es un protocolo de dos partes y el
    /// emisor NO está desplegado: en producción `GET /api/v1/marketplace/signing-key/` da 404 y
    /// `versions/` no expone `signature` (verificado 2026-08-03). Un `Enforce` con anillo vacío en
    /// ese mundo no protege nada: deniega el 100 % de las instalaciones legítimas — 403 en
    /// `request-install` y en el import de blueprints, que es como se tumbó el arranque de todo hub
    /// nuevo (ADR-0194).
    ///
    /// **No es fail-open silencioso:** se anuncia con WARN al arrancar, y basta desplegar la clave
    /// en `HUB_MODULE_TRUSTED_KEYS` para que el hub pase solo a [`Self::Enforce`], sin tocar código.
    Sha256Only,
}

impl SignaturePolicy {
    /// Aplica la política a un módulo: bajo `Enforce` exige y verifica la firma; bajo `DevTrust`
    /// acepta cualquier cosa (incluido `None`). Devuelve el `key_id` de la **clave de confianza**
    /// que validó (autoritativa, no el auto-declarado en la firma) bajo `Enforce`.
    pub fn check(&self, sig: Option<&ModuleSignature>, message: &[u8]) -> Result<Option<String>, SignatureError> {
        match self {
            Self::DevTrust | Self::Sha256Only => Ok(None),
            Self::Enforce(ring) => {
                let sig = sig.ok_or(SignatureError::Missing)?;
                let verified_key_id = ring.verify(sig, message)?;
                Ok(Some(verified_key_id.to_string()))
            }
        }
    }

    /// `true` si esta política exige firma verificada — es decir, hay un anillo de confianza
    /// desplegado. Los dos modos sin anillo ([`Self::DevTrust`], [`Self::Sha256Only`]) no pueden
    /// exigir nada: no tienen con qué verificar.
    pub fn requires_signature(&self) -> bool {
        matches!(self, Self::Enforce(_))
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// Firma (lado del publicador). Aquí para tests y como referencia del `erplora sign`
// real (el toolkit vive en otro repo: ERPlora/module-toolkit — ver TODO en el fix).
// `erplora sign` debe portarse a estos ~10 líneas: cargar el seed/privada, firmar
// los bytes del zip, escribir `<zip>.sig` = JSON de ModuleSignature.
// ─────────────────────────────────────────────────────────────────────────────

/// Material de firma de un solo uso: el par de claves ed25519 + su propia pública (para
/// construir el anillo en tests). Se crea desde un PKCS#8 (lo que genera `ring`).
#[derive(Debug)]
pub struct Signer {
    kp: Ed25519KeyPair,
}

impl Signer {
    /// Construye el firmante desde un seed PKCS#8 v2 (lo que produce `Ed25519KeyPair::generate`).
    pub fn from_pkcs8(pkcs8: &[u8]) -> Result<Self, SignatureError> {
        let kp = Ed25519KeyPair::from_pkcs8(pkcs8)
            .map_err(|e| SignatureError::BadKey(format!("pkcs8 inválido: {e}")))?;
        Ok(Self { kp })
    }

    /// Clave pública de este firmante (32 bytes) — para añadirla al `TrustedKeyRing` del verificador.
    pub fn public_key(&self) -> [u8; PUBLIC_KEY_LEN] {
        let mut pk = [0u8; PUBLIC_KEY_LEN];
        pk.copy_from_slice(self.kp.public_key().as_ref());
        pk
    }

    /// Firma `message` y devuelve una [`ModuleSignature`] detached con `key_id`.
    pub fn sign(&self, key_id: impl Into<String>, message: &[u8]) -> ModuleSignature {
        let sig = self.kp.sign(message);
        ModuleSignature::from_bytes(key_id, sig.as_ref())
    }

    /// Genera un par de claves ed25519 efímero. Devuelve (firmante, pkcs8 del par).
    ///
    /// Es la vía del **publicador** (toolkit `erplora sign` + tests): produce un par fresco cuyo
    /// PKCS#8 se persiste como secreto del marketplace y cuya pública se añade al anillo del hub.
    /// En producción el toolkit carga un PKCS#8 ya existente vía [`from_pkcs8`] en vez de generar.
    pub fn generate(rng: &ring::rand::SystemRandom) -> (Self, Vec<u8>) {
        let pkcs8 = Ed25519KeyPair::generate_pkcs8(rng).expect("generar par ed25519");
        let kp = Ed25519KeyPair::from_pkcs8(pkcs8.as_ref()).expect("par válido recién generado");
        (Self { kp }, pkcs8.as_ref().to_vec())
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// helpers
// ─────────────────────────────────────────────────────────────────────────────

fn decode_hex_or_b64(s: &str) -> Result<Vec<u8>, String> {
    // hex de 64 chars => 32 bytes. Si casa, es hex.
    if s.len() == PUBLIC_KEY_LEN * 2 && s.chars().all(|c| c.is_ascii_hexdigit()) {
        return hex::decode(s).map_err(|e| e.to_string());
    }
    // si no, prueba base64 standard.
    base64::engine::general_purpose::STANDARD
        .decode(s)
        .map_err(|e| e.to_string())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn rng() -> ring::rand::SystemRandom {
        ring::rand::SystemRandom::new()
    }

    /// Firma válida de la clave de confianza ⇒ acepta.
    #[test]
    fn firma_valida_acepta() {
        let (signer, _) = Signer::generate(&rng());
        let mut ring = TrustedKeyRing::empty();
        ring.add_bytes("marketplace", &signer.public_key()).unwrap();
        let policy = SignaturePolicy::Enforce(ring);

        let msg = b"contenido del zip";
        let sig = signer.sign("marketplace", msg);
        assert_eq!(policy.check(Some(&sig), msg), Ok(Some("marketplace".into())));
    }

    /// Módulo sin firma bajo `Enforce` ⇒ rechazado (`Missing`).
    #[test]
    fn sin_firma_rechazado_bajo_enforce() {
        let ring = TrustedKeyRing::empty();
        let policy = SignaturePolicy::Enforce(ring);
        assert_eq!(policy.check(None, b"zip"), Err(SignatureError::Missing));
    }

    /// Firma sobre un zip manipulado (otros bytes) ⇒ rechazado (`Invalid`).
    #[test]
    fn firma_sobre_bytes_distintos_rechazada() {
        let (signer, _) = Signer::generate(&rng());
        let mut ring = TrustedKeyRing::empty();
        ring.add_bytes("marketplace", &signer.public_key()).unwrap();
        let policy = SignaturePolicy::Enforce(ring);

        let sig = signer.sign("marketplace", b"zip original");
        // se verifica contra otros bytes (tampering):
        assert_eq!(policy.check(Some(&sig), b"zip MANIPULADO"), Err(SignatureError::Invalid));
    }

    /// Firma de una clave que NO está en el anillo ⇒ rechazado (`Invalid`).
    #[test]
    fn firma_de_clave_ajena_rechazada() {
        let (signer_trusted, _) = Signer::generate(&rng());
        let (signer_attacker, _) = Signer::generate(&rng());
        let mut ring = TrustedKeyRing::empty();
        // solo confiamos en la primera:
        ring.add_bytes("marketplace", &signer_trusted.public_key()).unwrap();
        let policy = SignaturePolicy::Enforce(ring);

        let msg = b"zip";
        let sig = signer_attacker.sign("marketplace-evil", msg);
        assert_eq!(policy.check(Some(&sig), msg), Err(SignatureError::Invalid));
    }

    /// DevTrust acepta módulos sin firma (escape hatch de desarrollo explícito).
    #[test]
    fn dev_trust_acepta_sin_firma() {
        let policy = SignaturePolicy::DevTrust;
        assert_eq!(policy.check(None, b"zip"), Ok(None));
        assert!(!policy.requires_signature());
    }

    /// Anillo vacío bajo Enforce => toda firma rechazada (deny-all / fail-closed).
    #[test]
    fn anillo_vacio_deny_all() {
        let (signer, _) = Signer::generate(&rng());
        let ring = TrustedKeyRing::empty();
        let policy = SignaturePolicy::Enforce(ring);
        let msg = b"zip";
        let sig = signer.sign("marketplace", msg);
        assert_eq!(policy.check(Some(&sig), msg), Err(SignatureError::Invalid));
        assert!(policy.requires_signature());
    }

    /// Clave cargada por hex y por base64 ⇒ misma clave pública.
    #[test]
    fn add_encoded_hex_o_base64() {
        let (signer, _) = Signer::generate(&rng());
        let pk = signer.public_key();
        let hex_s = hex::encode(pk);
        let b64_s = base64::engine::general_purpose::STANDARD.encode(pk);

        let mut r_hex = TrustedKeyRing::empty();
        r_hex.add_encoded("k", &hex_s).unwrap();
        let mut r_b64 = TrustedKeyRing::empty();
        r_b64.add_encoded("k", &b64_s).unwrap();

        let msg = b"zip";
        let sig = signer.sign("k", msg);
        assert!(matches!(SignaturePolicy::Enforce(r_hex).check(Some(&sig), msg), Ok(_)));
        assert!(matches!(SignaturePolicy::Enforce(r_b64).check(Some(&sig), msg), Ok(_)));
    }

    /// from_env: entradas múltiples separadas por coma, hex y base64, con y sin key_id.
    #[test]
    fn from_env_carga_claves_validas_e_ignora_rotas() {
        let (signer, _) = Signer::generate(&rng());
        let pk_hex = hex::encode(signer.public_key());
        let raw = format!("marketplace={pk_hex}, basura-no-es-clave, , otra=!!");
        let (ring, bad) = TrustedKeyRing::from_env(Some(&raw));
        // Las dos últimas no decodifican a 32 bytes ni en hex ni en base64 → 2 entradas rotas.
        assert_eq!(bad.len(), 2, "entradas rotas ignoradas: {bad:?}");
        assert!(!ring.is_empty(), "la clave buena carga");
        let msg = b"zip";
        let sig = signer.sign("marketplace", msg);
        assert!(matches!(
            SignaturePolicy::Enforce(ring).check(Some(&sig), msg),
            Ok(_)
        ));
    }

    /// from_env ausente/vacío => deny-all.
    #[test]
    fn from_env_vacio_es_deny_all() {
        assert!(TrustedKeyRing::from_env(None).0.is_empty());
        assert!(TrustedKeyRing::from_env(Some("")).0.is_empty());
        assert!(TrustedKeyRing::from_env(Some("   ")).0.is_empty());
    }

    /// Firma mal codificada (longitud errónea) => BadEncoding.
    #[test]
    fn firma_mal_codificada() {
        let bad = ModuleSignature { key_id: "k".into(), sig_b64: "no-es-base64-valida@@@".into() };
        let mut ring = TrustedKeyRing::empty();
        ring.add_bytes("k", &[0u8; PUBLIC_KEY_LEN]).unwrap();
        let policy = SignaturePolicy::Enforce(ring);
        assert!(matches!(policy.check(Some(&bad), b"zip"), Err(SignatureError::BadEncoding(_))));
    }
}
