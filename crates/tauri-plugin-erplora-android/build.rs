// Declara los comandos del plugin para que `tauri-plugin` autogenere sus permisos ACL
// (`allow-check-permissions`, `allow-request-permissions`) y compile el módulo Android.
// `open_app_settings` (hub#1886): the way back once Android stops showing a permission dialog.
const COMMANDS: &[&str] = &["check_permissions", "request_permissions", "open_app_settings"];

fn main() {
    tauri_plugin::Builder::new(COMMANDS)
        .android_path("android")
        .build();
}
