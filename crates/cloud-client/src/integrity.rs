//! Verificación de integridad SHA256 de los `module.zip` descargados (ARQUITECTURA.md §2.2).
use sha2::{Digest, Sha256};

#[derive(Debug, thiserror::Error, PartialEq, Eq)]
pub enum IntegrityError {
    #[error("sha256 no coincide: esperado {expected}, calculado {actual}")]
    Mismatch { expected: String, actual: String },
}

/// SHA256 en hex (minúsculas) de `bytes`.
pub fn sha256_hex(bytes: &[u8]) -> String {
    let mut h = Sha256::new();
    h.update(bytes);
    hex::encode(h.finalize())
}

/// SHA256 en hex (minúsculas) de todo lo que dé `reader`, en streaming (hub#981): el gemelo
/// de [`sha256_hex`] para verificar un zip ya volcado a disco sin cargarlo entero en RAM.
pub fn sha256_hex_reader(reader: &mut impl std::io::Read) -> std::io::Result<String> {
    let mut h = Sha256::new();
    std::io::copy(reader, &mut h)?;
    Ok(hex::encode(h.finalize()))
}

/// Compara un SHA256 ya calculado (p. ej. sobre la marcha durante una descarga en streaming,
/// hub#981) con el esperado, case-insensitive.
pub fn verify_sha256_hex(actual: &str, expected: &str) -> Result<(), IntegrityError> {
    if actual.eq_ignore_ascii_case(expected) {
        Ok(())
    } else {
        Err(IntegrityError::Mismatch {
            expected: expected.to_lowercase(),
            actual: actual.to_lowercase(),
        })
    }
}

/// Comprueba que el SHA256 de `bytes` coincide con `expected` (case-insensitive).
pub fn verify_sha256(bytes: &[u8], expected: &str) -> Result<(), IntegrityError> {
    verify_sha256_hex(&sha256_hex(bytes), expected)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn known_vector() {
        // sha256("") = e3b0c442...855
        assert_eq!(&sha256_hex(b"")[..8], "e3b0c442");
        assert!(verify_sha256(b"abc", &sha256_hex(b"abc")).is_ok());
        assert!(verify_sha256(b"abc", "deadbeef").is_err());
    }
}
