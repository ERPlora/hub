fn main() {
    // ADR-0050 (mismo origen): la ventana carga el runtime Axum embebido (127.0.0.1:8787), que es un
    // **origen remoto** para Tauri. El ACL solo permite un `invoke` desde un origen remoto si el
    // comando tiene un permiso `allow-<cmd>` concedido por una capability con `remote.urls`. Sin un
    // `AppManifest::commands(...)`, esos permisos NO existen y el ACL rechaza TODOS los comandos de la
    // app en el bundle (dev lo enmascara: origen local sin app-manifest desactiva el gate). Declaramos
    // aquí los comandos para que `tauri-build` autogenere `allow-<cmd>`; la capability los concede.
    // Mantener en sync con `generate_handler![...]` en `lib.rs`.
    tauri_build::try_build(
        tauri_build::Attributes::new().app_manifest(tauri_build::AppManifest::new().commands(&[
            // Gate de entitlement + identidad/enrol (nativo).
            "validate_entitlement",
            "device_context",
            "enroll_device",
            "rotate_machine_token",
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
