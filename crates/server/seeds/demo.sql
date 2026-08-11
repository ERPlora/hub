-- Seed de configuración inicial del despliegue DEMO de ERPlora (hub#36).
--
-- NO es "modo demo": es el MISMO hub Rust que se despliega en AWS, arrancado con SQLite y este
-- SQL cargado vía `HUB_SEED_SQL` (el runtime lo aplica una vez al arrancar, tras crear las tablas
-- de sistema). El terraform (aws/terraform/ecs_demo.tf) pasa este contenido inline.
--
-- IDEMPOTENTE: cada sentencia usa `WHERE NOT EXISTS` para poder re-arrancar sin duplicar ni fallar.
-- El runtime lo aplica con `crate::seed::apply` (split por `;`, una sentencia por `execute`).
--
-- `:hub_id` lo liga el runtime (`seed::apply`) con el hub_id del despliegue, no el fichero.
--
-- Esquema real (no tocar nombres de columna sin re-validar el test `seed.rs`):
--   hub_user(id, hub_id, name, pin_hash, role, cloud_user_id, is_active, created_at)  crates/runtime/src/identity.rs
--   hub_trusted_device(hub_id, device_id, label, trusted_at)                   crates/runtime/src/system_migrations.rs (v2 + v23)
--
-- PIN "0000" en formato LEGACY `salt_hex:hash_hex` que `identity.rs::check_pin` acepta y rehashea
-- perezosamente a argon2id en el primer login. Hash = SHA-256 de `"{salt}:{pin}"`:
--   salt = "demo-seed-salt", pin = "0000"
--   sha256("demo-seed-salt:0000") = 1dc5326634c5a049052910edddc64689c1389d7812621b2f5c6fe6b1bb065628
-- El test `seed::tests::demo_seed_enables_demo_pin_login_and_trusted_device` GARANTIZA que verifica.

-- Usuario "Demo": rol "admin" (el rol con más cobertura de permisos en los módulos POS), activo,
-- sin vínculo cloud, PIN "0000".
INSERT INTO hub_user (id, hub_id, name, pin_hash, role, cloud_user_id, is_active, created_at)
SELECT 'demo-user-0000000000000000000000', :hub_id, 'Demo',
       'demo-seed-salt:1dc5326634c5a049052910edddc64689c1389d7812621b2f5c6fe6b1bb065628',
       'admin', NULL, 1, '2026-01-01T00:00:00+00:00'
WHERE NOT EXISTS (SELECT 1 FROM hub_user WHERE hub_id = :hub_id AND name = 'Demo');

-- 🔴 AQUÍ HABÍA un dispositivo de confianza sembrado, `demo-trusted-device`, para que el login por
-- PIN funcionase sin login online previo. NO funcionaba, y no podía (hub#630): el `device_id` se lo
-- acuña el NAVEGADOR con un CSPRNG y lo guarda en el localStorage **del origen del hub**
-- (`apps/web/src/lib/device.ts`), así que ningún visitante iba a presentar jamás ese nombre. Era un
-- escritor sin lector posible — la demo arrancaba y se quedaba en «en este dispositivo todavía no
-- funciona el PIN», que es exactamente lo que el visitante no puede resolver: no tiene cuenta.
--
-- Lo sustituye el **trust-on-first-use** del core (`crates/server/src/lib.rs`, login por PIN): en un
-- hub de demo, el PRIMER dispositivo que se presenta queda adoptado y registrado, y los siguientes
-- se rechazan como siempre. Sembrar una fila aquí volvería a romperlo — la adopción solo actúa
-- cuando el hub no conoce ningún dispositivo todavía, y esta fila la haría inalcanzable.
