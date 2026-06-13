-- Seed de configuración inicial del despliegue DEMO de ERPlora (hub#36).
--
-- NO es "modo demo": es el MISMO hub Rust que se despliega en AWS, arrancado con SQLite y este
-- SQL cargado vía `HUB_SEED_SQL` (el runtime lo aplica una vez al arrancar, tras crear las tablas
-- de sistema). El terraform (aws/terraform/ecs_demo.tf) pasa este contenido inline.
--
-- IDEMPOTENTE: cada sentencia usa `WHERE NOT EXISTS` para poder re-arrancar sin duplicar ni fallar.
-- El runtime lo aplica con `crate::seed::apply` (split por `;`, una sentencia por `execute_batch`).
--
-- Esquema real (no tocar nombres de columna sin re-validar el test `seed.rs`):
--   hub_user(id, name, pin_hash, role, cloud_user_id, is_active, created_at)   crates/runtime/src/identity.rs
--   hub_trusted_device(device_id, label, trusted_at)                           crates/runtime/src/system_migrations.rs (v2)
--
-- PIN "0000" en formato LEGACY `salt_hex:hash_hex` que `identity.rs::check_pin` acepta y rehashea
-- perezosamente a argon2id en el primer login. Hash = SHA-256 de `"{salt}:{pin}"`:
--   salt = "demo-seed-salt", pin = "0000"
--   sha256("demo-seed-salt:0000") = 1dc5326634c5a049052910edddc64689c1389d7812621b2f5c6fe6b1bb065628
-- El test `seed::tests::demo_seed_enables_demo_pin_login_and_trusted_device` GARANTIZA que verifica.

-- Usuario "Demo": rol "admin" (el rol con más cobertura de permisos en los módulos POS), activo,
-- sin vínculo cloud, PIN "0000".
INSERT INTO hub_user (id, name, pin_hash, role, cloud_user_id, is_active, created_at)
SELECT 'demo-user-0000000000000000000000', 'Demo',
       'demo-seed-salt:1dc5326634c5a049052910edddc64689c1389d7812621b2f5c6fe6b1bb065628',
       'admin', NULL, 1, '2026-01-01T00:00:00+00:00'
WHERE NOT EXISTS (SELECT 1 FROM hub_user WHERE name = 'Demo');

-- Dispositivo de confianza del demo: permite el login por PIN sin login online previo cuando el
-- device-trust está activo. `device_id` = 'demo-trusted-device'.
INSERT INTO hub_trusted_device (device_id, label, trusted_at)
SELECT 'demo-trusted-device', 'Demo device', '2026-01-01T00:00:00+00:00'
WHERE NOT EXISTS (SELECT 1 FROM hub_trusted_device WHERE device_id = 'demo-trusted-device');
