# apps/tauri (STUB)

Empaquetado **desktop/móvil** (Tauri v2) del mismo shell + runtime Rust. ARQUITECTURA.md §1, §3.

Expondrá `erplora_query`/`erplora_command` por `invoke` (IPC) + Tauri events (push) →
delegando en `crates/runtime`. DB local = SQLite (`HUB_SQLITE_PATH`, §8). Sin red salvo
marketplace/AI/primer-login (§2.8).

**Pendiente**: requiere toolchain Rust + Tauri CLI. De-risk #2 del §12 (Tauri `invoke` y
Axum llamando al *mismo* `runtime`).
