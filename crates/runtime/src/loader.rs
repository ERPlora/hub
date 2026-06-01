//! Carga de los artefactos del módulo desde disco (SQL, schemas) relativos a su carpeta.
//! (La descarga del `module.zip` desde S3 + verificación SHA256 vive en `erplora-source`.)
use std::path::Path;

use crate::errors::Result;

/// Lee un fichero de texto relativo a la carpeta del módulo (p. ej. `queries/list.sql`).
pub fn read_text(module_dir: &Path, rel: &str) -> Result<String> {
    Ok(std::fs::read_to_string(module_dir.join(rel))?)
}
