// Declara los comandos del plugin para que `tauri-plugin` autogenere sus permisos ACL
// (`allow-check-permissions`, `allow-request-permissions`) y compile el módulo Android.
const COMMANDS: &[&str] = &["check_permissions", "request_permissions"];

fn main() {
    tauri_plugin::Builder::new(COMMANDS)
        .android_path("android")
        .build();
}
