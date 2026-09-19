-- Initial configuration seed of the ERPlora DEMO deployment (hub#36).
--
-- It is NOT a "demo mode": it is the SAME Rust hub as any other, booted with this SQL through
-- `HUB_SEED_SQL` (the runtime applies it at every boot, after creating the system tables). This
-- file is the ORIGINAL: the production demo receives the SaaS's byte-identical copy of these
-- statements (`hub_demo_seed.sql`, flattened to one line by `_demo_seed_sql_inline`), and the local
-- hub (`scripts/dev.mjs`) and the e2e bench load this very file through `HUB_SEED_SQL_PATH`.
--
-- IDEMPOTENT: every statement uses `WHERE NOT EXISTS` so it can re-boot without duplicating or
-- failing. The runtime applies it with `crate::seed::apply` (split on `;`, one statement per
-- `execute`). Comments go on whole lines only: the SaaS flattening drops `--` lines, and a trailing
-- `--` on a single-line env value would comment out every statement after it.
--
-- `:hub_id` is bound by the runtime (`seed::apply`) to the deployment's hub_id, not by the file.
--
-- Real schema (do not rename columns without re-running the `seed.rs` test):
--   hub_user(id, hub_id, name, pin_hash, role, cloud_user_id, is_active, created_at)  crates/runtime/src/identity.rs
--   hub_settings(hub_id, key, value, updated_at, updated_by)                    crates/runtime/src/system_migrations.rs (v4)
--   hub_trusted_device(hub_id, device_id, label, trusted_at)                   crates/runtime/src/system_migrations.rs (v2 + v23)
--
-- PIN "000000" (hub#1929) in the LEGACY `salt_hex:hash_hex` format that `identity.rs::check_pin`
-- accepts and lazily rehashes to argon2id on the first login. Hash = SHA-256 of `"{salt}:{pin}"`:
--   salt = "demo-seed-salt", pin = "000000"
--   sha256("demo-seed-salt:000000") = e35965261d83711c5304a8a53178f8b9e978177904203918d3f4b331ff2e9a2d
-- The test `seed::tests::demo_seed_enables_demo_pin_login_and_trusted_device` GUARANTEES it verifies.

-- The demo asks for SIX digits, like every hub provisioned today (ADR-0372), and its PIN fills
-- them (hub#1929). The pinpad submits at exactly `pin_length` digits (hub#1037): without this row
-- the demo would fall back to the runtime default of 4 and a six-digit PIN could never be typed.
-- It lives in the SEED and not in provisioning because the local hub applies this same file.
-- Same shape as the SaaS's `_pin_length_seed_sql`, and like it it never overwrites: the seed runs
-- at every boot, and a length the admin changed in Ajustes outranks the one the demo was born with.
-- ORDER MATTERS: this statement runs BEFORE the user's and only while "Demo" does not exist yet,
-- so the six-digit keypad and the six-digit PIN are born in the same pass. A database that
-- already holds the old four-digit "Demo" (a persistent local `erplora_hub_dev`, a live demo)
-- keeps its `0000` — the user row below never overwrites — and must keep its four-digit keypad
-- too, or that PIN could never be typed (test `demo_seed_keeps_a_four_digit_demo_on_its_four_digit_keypad`).
INSERT INTO hub_settings (hub_id, key, value, updated_at, updated_by)
SELECT :hub_id, 'pin_length', '6', '2026-01-01T00:00:00+00:00', 'system:provisioning'
WHERE NOT EXISTS (SELECT 1 FROM hub_settings WHERE hub_id = :hub_id AND key = 'pin_length')
  AND NOT EXISTS (SELECT 1 FROM hub_user WHERE hub_id = :hub_id AND name = 'Demo');

-- "Demo" user: role "admin" (the role with the widest permission coverage in the POS modules),
-- active, no cloud link, PIN "000000".
INSERT INTO hub_user (id, hub_id, name, pin_hash, role, cloud_user_id, is_active, created_at)
SELECT 'demo-user-0000000000000000000000', :hub_id, 'Demo',
       'demo-seed-salt:e35965261d83711c5304a8a53178f8b9e978177904203918d3f4b331ff2e9a2d',
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
