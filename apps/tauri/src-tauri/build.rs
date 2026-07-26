fn main() {
    // ADR-0159 (cliente fino): la ventana carga ORÍGENES REMOTOS (el SaaS para el onboarding y la
    // PWA del hub cloud en `https://<sub>.erplora.com`). El ACL de Tauri solo permite un `invoke`
    // desde un origen remoto si el comando tiene un permiso `allow-<cmd>` concedido por una
    // capability con `remote.urls`. Sin un `AppManifest::commands(...)`, esos permisos NO existen y
    // el ACL rechaza TODOS los comandos de la app en el bundle (dev lo enmascara: origen local sin
    // app-manifest desactiva el gate). Declaramos aquí los comandos para que `tauri-build`
    // autogenere `allow-<cmd>`; la capability los concede. Mantener en sync con
    // `generate_handler![...]` en `lib.rs`.
    tauri_build::try_build(
        tauri_build::Attributes::new().app_manifest(tauri_build::AppManifest::new().commands(&[
            // Identidad de dispositivo (X-Device-Id, sesión única ADR-0154) + olvido del hub.
            "device_context",
            "forget_hub",
            // Hardware (el shell ES el bridge, §2.7).
            "erplora_bridge_status",
            "erplora_discover_printers",
            "erplora_get_devices",
            "erplora_print",
            "erplora_test_print",
            "erplora_open_drawer",
            "erplora_set_device_role",
            "erplora_set_device_name",
            "erplora_remove_device",
        ])),
    )
    .expect("error en tauri-build (app manifest / capabilities)");
}
