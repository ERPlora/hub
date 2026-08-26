-- Sector-pack seed fixture: beauty (es) — hub#1050.
--
-- What it is for: `sector_packs_pg_e2e` installs the whole POS module pack on a real Postgres and
-- then applies THIS file through `Runtime::apply_seed` — the same door the host uses for
-- `HUB_SEED_SQL`. A red here means the seed does not match the Postgres schema the modules just
-- migrated (a column that moved, a type Postgres refuses, syntax SQLite tolerates), or that
-- `seed::apply` stopped scoping to the hub the identity rows this file does not scope itself
-- (`hub_user`, hub#840).
--
-- Why it lives HERE and not in the `blueprints` repo: it used to be read out of that sibling
-- checkout, from the hand-written catalogue model ADR-0121 retired — which left the hub as the
-- only live consumer of a dead model and blocked its removal (blueprints#8). Since ADR-0121 a real
-- sector seed comes out of a hub's Export as a `.blueprint.zip`, and nothing in production reads a
-- hand-written catalogue any more, so what this suite needs is a fixture, and a fixture belongs to
-- the repo that asserts on it.
--
-- Why it is SMALL: the published catalogue carried 67 statements, most of them more rows of
-- the same shape. What the assertion needs is one row per table shape, not a catalogue: the
-- statements below are lifted verbatim from it, keeping every column list intact and every
-- reference resolvable, so a schema drift still shows up here.
--
-- Contract (ADR-0007/0123): ids and refs TEXT, money INTEGER cents, rates REAL, flags 0/1 INTEGER,
-- dates/times ISO-8601 TEXT. Every statement is idempotent (`WHERE NOT EXISTS`), so re-applying it
-- neither duplicates nor fails. hub_id literal `00000000-0000-0000-0000-000000000001`: the runtime
-- rewrites identity rows to the hub being seeded.

INSERT INTO services_settings (id, hub_id, default_duration, default_buffer_time, default_tax_category_key, show_prices, show_duration, allow_online_booking, include_tax_in_price, currency, is_deleted, created_by, updated_by, created_at, updated_at)
SELECT 'svcset-beauty', '00000000-0000-0000-0000-000000000001', 45, 5, 'service.generic', 1, 1, 1, 1, 'EUR', 0, NULL, NULL, '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00'
WHERE NOT EXISTS (SELECT 1 FROM services_settings WHERE hub_id = '00000000-0000-0000-0000-000000000001');
INSERT INTO services_category (id, hub_id, name, slug, description, parent_id, icon, color, image, sort_order, is_active, is_deleted, created_by, updated_by, created_at, updated_at)
SELECT 'cat-beauty-corte', '00000000-0000-0000-0000-000000000001', 'Corte y peinado', 'corte-peinado', '', NULL, 'cut-outline', '', '', 0, 1, 0, NULL, NULL, '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00'
WHERE NOT EXISTS (SELECT 1 FROM services_category WHERE hub_id = '00000000-0000-0000-0000-000000000001' AND slug = 'corte-peinado');
INSERT INTO services_category (id, hub_id, name, slug, description, parent_id, icon, color, image, sort_order, is_active, is_deleted, created_by, updated_by, created_at, updated_at)
SELECT 'cat-beauty-unas', '00000000-0000-0000-0000-000000000001', 'Manicura y pedicura', 'manicura-pedicura', '', NULL, 'hand-left-outline', '', '', 4, 1, 0, NULL, NULL, '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00'
WHERE NOT EXISTS (SELECT 1 FROM services_category WHERE hub_id = '00000000-0000-0000-0000-000000000001' AND slug = 'manicura-pedicura');
INSERT INTO services_service (id, hub_id, name, slug, description, short_description, category_id, pricing_type, price, min_price, max_price, cost, tax_category_key, duration_minutes, buffer_before, buffer_after, max_capacity, image, icon, color, is_bookable, requires_confirmation, allow_online_booking, sort_order, is_active, is_featured, sku, barcode, notes, is_deleted, created_by, updated_by, created_at, updated_at)
SELECT 'svc-beauty-corte_senora', '00000000-0000-0000-0000-000000000001', 'Corte de señora', 'corte-senora', '', '', 'cat-beauty-corte', 'fixed', 1800, NULL, NULL, 0, 'service.generic', 45, 0, 5, 1, 'catalog/beauty_hair/corte_senora.webp', '', '', 1, 0, 1, 0, 1, 1, 'corte_senora', '', '', 0, NULL, NULL, '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00'
WHERE NOT EXISTS (SELECT 1 FROM services_service WHERE hub_id = '00000000-0000-0000-0000-000000000001' AND slug = 'corte-senora');
INSERT INTO services_service (id, hub_id, name, slug, description, short_description, category_id, pricing_type, price, min_price, max_price, cost, tax_category_key, duration_minutes, buffer_before, buffer_after, max_capacity, image, icon, color, is_bookable, requires_confirmation, allow_online_booking, sort_order, is_active, is_featured, sku, barcode, notes, is_deleted, created_by, updated_by, created_at, updated_at)
SELECT 'svc-beauty-manicura', '00000000-0000-0000-0000-000000000001', 'Manicura básica', 'manicura-basica', '', '', 'cat-beauty-unas', 'fixed', 1500, NULL, NULL, 0, 'service.generic', 30, 0, 5, 1, 'catalog/beauty_body/manicura_basica.webp', '', '', 1, 0, 1, 0, 1, 0, 'manicura_basica', '', '', 0, NULL, NULL, '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00'
WHERE NOT EXISTS (SELECT 1 FROM services_service WHERE hub_id = '00000000-0000-0000-0000-000000000001' AND slug = 'manicura-basica');
INSERT INTO staff_role (id, hub_id, name, description, color, "order", is_active, is_deleted, created_by, updated_by, created_at, updated_at)
SELECT 'role-beauty-estilista', '00000000-0000-0000-0000-000000000001', 'Estilista', 'Corte, color y peinado', '#0091CE', 0, 1, 0, NULL, NULL, '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00'
WHERE NOT EXISTS (SELECT 1 FROM staff_role WHERE hub_id = '00000000-0000-0000-0000-000000000001' AND name = 'Estilista');
INSERT INTO staff_role (id, hub_id, name, description, color, "order", is_active, is_deleted, created_by, updated_by, created_at, updated_at)
SELECT 'role-beauty-esteticista', '00000000-0000-0000-0000-000000000001', 'Esteticista', 'Manicura, pedicura y estética', '#AD1457', 2, 1, 0, NULL, NULL, '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00'
WHERE NOT EXISTS (SELECT 1 FROM staff_role WHERE hub_id = '00000000-0000-0000-0000-000000000001' AND name = 'Esteticista');
INSERT INTO staff_member (id, hub_id, first_name, last_name, email, phone, employee_id, role_id, hire_date, status, bio, specialties, is_bookable, color, hourly_rate, commission_rate, notes, is_deleted, created_by, updated_by, created_at, updated_at)
SELECT 'staff-beauty-laura', '00000000-0000-0000-0000-000000000001', 'Laura', 'García', '', '', 'EMP-001', 'role-beauty-estilista', '2026-01-01', 'active', '', 'corte,color,mechas', 1, '#0091CE', 1200, 10.0, '', 0, NULL, NULL, '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00'
WHERE NOT EXISTS (SELECT 1 FROM staff_member WHERE hub_id = '00000000-0000-0000-0000-000000000001' AND employee_id = 'EMP-001');
INSERT INTO staff_member (id, hub_id, first_name, last_name, email, phone, employee_id, role_id, hire_date, status, bio, specialties, is_bookable, color, hourly_rate, commission_rate, notes, is_deleted, created_by, updated_by, created_at, updated_at)
SELECT 'staff-beauty-sara', '00000000-0000-0000-0000-000000000001', 'Sara', 'López', '', '', 'EMP-004', 'role-beauty-esteticista', '2026-01-01', 'active', '', 'manicura,pedicura,depilacion', 1, '#AD1457', 1200, 10.0, '', 0, NULL, NULL, '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00'
WHERE NOT EXISTS (SELECT 1 FROM staff_member WHERE hub_id = '00000000-0000-0000-0000-000000000001' AND employee_id = 'EMP-004');
INSERT INTO staff_service (id, hub_id, staff_id, service_id, service_name, custom_duration, custom_price, is_primary, is_active, is_deleted, created_by, updated_by, created_at, updated_at)
SELECT 'staffsvc-beauty-laura-corte', '00000000-0000-0000-0000-000000000001', 'staff-beauty-laura', 'svc-beauty-corte_senora', 'Corte de señora', NULL, NULL, 1, 1, 0, NULL, NULL, '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00'
WHERE NOT EXISTS (SELECT 1 FROM staff_service WHERE staff_id = 'staff-beauty-laura' AND service_id = 'svc-beauty-corte_senora');
INSERT INTO staff_service (id, hub_id, staff_id, service_id, service_name, custom_duration, custom_price, is_primary, is_active, is_deleted, created_by, updated_by, created_at, updated_at)
SELECT 'staffsvc-beauty-sara-manicura', '00000000-0000-0000-0000-000000000001', 'staff-beauty-sara', 'svc-beauty-manicura', 'Manicura básica', NULL, NULL, 1, 1, 0, NULL, NULL, '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00'
WHERE NOT EXISTS (SELECT 1 FROM staff_service WHERE staff_id = 'staff-beauty-sara' AND service_id = 'svc-beauty-manicura');
INSERT INTO staff_schedule (id, hub_id, staff_id, name, is_default, effective_from, effective_until, is_active, is_deleted, created_by, updated_by, created_at, updated_at)
SELECT 'sched-beauty-laura', '00000000-0000-0000-0000-000000000001', 'staff-beauty-laura', 'Horario habitual', 1, '2026-01-01', NULL, 1, 0, NULL, NULL, '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00'
WHERE NOT EXISTS (SELECT 1 FROM staff_schedule WHERE hub_id = '00000000-0000-0000-0000-000000000001' AND staff_id = 'staff-beauty-laura' AND is_default = 1);
INSERT INTO staff_schedule (id, hub_id, staff_id, name, is_default, effective_from, effective_until, is_active, is_deleted, created_by, updated_by, created_at, updated_at)
SELECT 'sched-beauty-sara', '00000000-0000-0000-0000-000000000001', 'staff-beauty-sara', 'Horario habitual', 1, '2026-01-01', NULL, 1, 0, NULL, NULL, '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00'
WHERE NOT EXISTS (SELECT 1 FROM staff_schedule WHERE hub_id = '00000000-0000-0000-0000-000000000001' AND staff_id = 'staff-beauty-sara' AND is_default = 1);
INSERT INTO staff_working_hours (id, hub_id, schedule_id, day_of_week, start_time, end_time, break_start, break_end, is_working, is_deleted, created_by, updated_by, created_at, updated_at)
SELECT 'wh-beauty-laura-0', '00000000-0000-0000-0000-000000000001', 'sched-beauty-laura', 0, '09:30:00', '20:00:00', '14:00:00', '16:00:00', 1, 0, NULL, NULL, '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00'
WHERE NOT EXISTS (SELECT 1 FROM staff_working_hours WHERE schedule_id = 'sched-beauty-laura' AND day_of_week = 0);
INSERT INTO staff_settings (id, hub_id, default_work_start, default_work_end, default_break_duration, min_advance_booking, max_daily_hours, overtime_threshold, show_staff_photos, show_staff_bio, allow_staff_selection, notify_new_appointment, notify_cancellation, is_deleted, created_by, updated_by, created_at, updated_at)
SELECT 'staffset-beauty', '00000000-0000-0000-0000-000000000001', '09:30:00', '20:00:00', 120, 1, 10, 40, 1, 1, 1, 1, 1, 0, NULL, NULL, '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00'
WHERE NOT EXISTS (SELECT 1 FROM staff_settings WHERE hub_id = '00000000-0000-0000-0000-000000000001');
INSERT INTO schedules_settings (id, hub_id, timezone, week_starts_on, slot_duration, auto_close_enabled, is_deleted, created_by, created_at, updated_by, updated_at)
SELECT 'schedset-beauty', '00000000-0000-0000-0000-000000000001', 'Europe/Madrid', 1, 30, 0, 0, NULL, '2026-01-01T00:00:00+00:00', NULL, '2026-01-01T00:00:00+00:00'
WHERE NOT EXISTS (SELECT 1 FROM schedules_settings WHERE hub_id = '00000000-0000-0000-0000-000000000001');
INSERT INTO schedules_business_hours (id, hub_id, day_of_week, open_time, close_time, is_closed, break_start, break_end, is_deleted, created_by, created_at, updated_by, updated_at)
SELECT 'bh-beauty-0', '00000000-0000-0000-0000-000000000001', 0, '09:30', '20:00', 0, '14:00', '16:00', 0, NULL, '2026-01-01T00:00:00+00:00', NULL, '2026-01-01T00:00:00+00:00'
WHERE NOT EXISTS (SELECT 1 FROM schedules_business_hours WHERE hub_id = '00000000-0000-0000-0000-000000000001' AND day_of_week = 0);
INSERT INTO pricing_price_list (id, hub_id, code, name, currency, is_default, is_active, valid_from, valid_until, segment, is_deleted, created_by, updated_by, created_at, updated_at)
SELECT 'pl-beauty-general', '00000000-0000-0000-0000-000000000001', 'TARIFA_GENERAL', 'Tarifa general', 'EUR', 1, 1, '2026-01-01', NULL, NULL, 0, NULL, NULL, '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00'
WHERE NOT EXISTS (SELECT 1 FROM pricing_price_list WHERE hub_id = '00000000-0000-0000-0000-000000000001' AND code = 'TARIFA_GENERAL');
INSERT INTO pricing_price_list_item (id, hub_id, price_list_id, product_ref, price, min_quantity, max_quantity, is_deleted, created_by, updated_by, created_at, updated_at)
SELECT 'pli-beauty-corte_senora', '00000000-0000-0000-0000-000000000001', 'pl-beauty-general', 'svc-beauty-corte_senora', 1800, 1, NULL, 0, NULL, NULL, '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00'
WHERE NOT EXISTS (SELECT 1 FROM pricing_price_list_item WHERE hub_id = '00000000-0000-0000-0000-000000000001' AND price_list_id = 'pl-beauty-general' AND product_ref = 'svc-beauty-corte_senora');
INSERT INTO pricing_price_list_item (id, hub_id, price_list_id, product_ref, price, min_quantity, max_quantity, is_deleted, created_by, updated_by, created_at, updated_at)
SELECT 'pli-beauty-manicura', '00000000-0000-0000-0000-000000000001', 'pl-beauty-general', 'svc-beauty-manicura', 1500, 1, NULL, 0, NULL, NULL, '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00'
WHERE NOT EXISTS (SELECT 1 FROM pricing_price_list_item WHERE hub_id = '00000000-0000-0000-0000-000000000001' AND price_list_id = 'pl-beauty-general' AND product_ref = 'svc-beauty-manicura');
INSERT INTO hub_user (id, name, pin_hash, role, cloud_user_id, is_active, created_at)
SELECT 'user-beauty-cashier1', 'Cajero 1', 'cashier1-seed-salt:9d81582af594e1cc780151726e43aceb5da668e780bf455ca41b6bfc0a7074ca', 'employee', NULL, 1, '2026-01-01T00:00:00+00:00'
WHERE NOT EXISTS (SELECT 1 FROM hub_user WHERE name = 'Cajero 1');
INSERT INTO staff_member (id, hub_id, first_name, last_name, user_id, status, is_bookable, created_at, updated_at)
SELECT 'staff-beauty-cashier1', '00000000-0000-0000-0000-000000000001', 'Cajero', 'Uno', 'user-beauty-cashier1', 'active', 0, '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00'
WHERE NOT EXISTS (SELECT 1 FROM staff_member WHERE id = 'staff-beauty-cashier1');
INSERT INTO hub_user (id, name, pin_hash, role, cloud_user_id, is_active, created_at)
SELECT 'user-beauty-cashier2', 'Cajero 2', 'cashier2-seed-salt:fe8ab1c960ef7d0abbbd1c7598ed2036f7aabc2408571edfdaff16d6bc1bdb0f', 'employee', NULL, 1, '2026-01-01T00:00:00+00:00'
WHERE NOT EXISTS (SELECT 1 FROM hub_user WHERE name = 'Cajero 2');
INSERT INTO staff_member (id, hub_id, first_name, last_name, user_id, status, is_bookable, created_at, updated_at)
SELECT 'staff-beauty-cashier2', '00000000-0000-0000-0000-000000000001', 'Cajero', 'Dos', 'user-beauty-cashier2', 'active', 0, '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00'
WHERE NOT EXISTS (SELECT 1 FROM staff_member WHERE id = 'staff-beauty-cashier2');
