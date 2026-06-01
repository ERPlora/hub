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

/// Comprueba que el SHA256 de `bytes` coincide con `expected` (case-insensitive).
pub fn verify_sha256(bytes: &[u8], expected: &str) -> Result<(), IntegrityError> {
    let actual = sha256_hex(bytes);
    if actual.eq_ignore_ascii_case(expected) {
        Ok(())
    } else {
        Err(IntegrityError::Mismatch { expected: expected.to_lowercase(), actual })
    }
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
