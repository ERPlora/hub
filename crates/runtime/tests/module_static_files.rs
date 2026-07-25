use std::sync::{Arc, Mutex};

use erplora_db::testutil::fresh_db;
use erplora_runtime::module_storage::ModuleStorage;
use erplora_runtime::{Result, Runtime};

#[derive(Debug, Default)]
struct RecordingStorage {
    ensured: Mutex<Vec<(String, String)>>,
}

#[async_trait::async_trait]
impl ModuleStorage for RecordingStorage {
    async fn ensure_module_folder(&self, hub_id: &str, folder: &str) -> Result<()> {
        self.ensured.lock().unwrap().push((hub_id.to_string(), folder.to_string()));
        Ok(())
    }

    async fn write_module_file(
        &self,
        _hub_id: &str,
        _folder: &str,
        _relative_path: &str,
        _bytes: &[u8],
        _content_type: &str,
    ) -> Result<String> {
        unreachable!("this test only provisions the folder")
    }
}

fn fixture(manifest: &str) -> std::path::PathBuf {
    let dir = std::env::temp_dir().join(format!("erplora-static-files-{}", uuid::Uuid::new_v4()));
    std::fs::create_dir_all(&dir).unwrap();
    std::fs::write(dir.join("module.json"), manifest).unwrap();
    dir
}

#[tokio::test]
async fn install_materializes_declared_static_files_folder() {
    let db = fresh_db().await;
    let mut runtime = Runtime::with_hub_id(Box::new(db), "hub-storage");
    runtime.ensure_system_tables().await.unwrap();
    let storage = Arc::new(RecordingStorage::default());
    runtime.set_module_storage(storage.clone());
    let dir = fixture(
        r#"{
          "id":"archive",
          "name":"Archive",
          "version":"1.0.0",
          "static_files":{"folder":"archive"}
        }"#,
    );

    runtime.install_from_dir(&dir).await.unwrap();

    assert_eq!(
        storage.ensured.lock().unwrap().as_slice(),
        &[("hub-storage".to_string(), "archive".to_string())]
    );
    std::fs::remove_dir_all(dir).unwrap();
}

#[tokio::test]
async fn install_rejects_static_files_path_traversal() {
    let db = fresh_db().await;
    let mut runtime = Runtime::with_hub_id(Box::new(db), "hub-storage");
    runtime.ensure_system_tables().await.unwrap();
    let dir = fixture(
        r#"{
          "id":"archive",
          "name":"Archive",
          "version":"1.0.0",
          "static_files":{"folder":"../archive"}
        }"#,
    );

    let error = runtime.install_from_dir(&dir).await.unwrap_err().to_string();

    assert!(error.contains("static_files.folder"));
    std::fs::remove_dir_all(dir).unwrap();
}
