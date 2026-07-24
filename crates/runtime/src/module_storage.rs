//! Almacenamiento persistente privado de módulos.
//!
//! Un módulo declara `static_files.folder` en `module.json`; el runtime nunca recibe una ruta
//! física. El host resuelve `media/modules/<folder>/` contra su backend (disco en Local,
//! Cloud→S3 en Cloud) y media todas las escrituras.

use crate::Result;

/// Backend de ficheros persistentes de módulos, inyectado por el host del runtime.
#[async_trait::async_trait]
pub trait ModuleStorage: Send + Sync + std::fmt::Debug {
    /// Materializa `media/modules/<folder>/`. Debe ser idempotente.
    async fn ensure_module_folder(&self, hub_id: &str, folder: &str) -> Result<()>;

    /// Escribe un fichero relativo a la carpeta declarada y devuelve su ruta relativa a `media/`.
    async fn write_module_file(
        &self,
        hub_id: &str,
        folder: &str,
        relative_path: &str,
        bytes: &[u8],
        content_type: &str,
    ) -> Result<String>;
}

/// Valida una ruta de fichero relativa y portable. Acepta subcarpetas, pero nunca rutas absolutas,
/// componentes vacíos, `.`/`..`, separadores Windows ni un path que termine en `/`.
pub fn valid_relative_file_path(path: &str) -> bool {
    !path.is_empty()
        && path.len() <= 512
        && !path.starts_with('/')
        && !path.ends_with('/')
        && !path.contains('\\')
        && path
            .split('/')
            .all(|part| !part.is_empty() && part != "." && part != ".." && part.len() <= 128)
}

#[cfg(test)]
mod tests {
    use super::valid_relative_file_path;

    #[test]
    fn only_accepts_safe_relative_file_paths() {
        assert!(valid_relative_file_path("xml/record-1.xml"));
        assert!(valid_relative_file_path("record.xml"));
        assert!(!valid_relative_file_path("../record.xml"));
        assert!(!valid_relative_file_path("/record.xml"));
        assert!(!valid_relative_file_path("xml//record.xml"));
        assert!(!valid_relative_file_path("xml\\record.xml"));
        assert!(!valid_relative_file_path("xml/"));
    }
}
