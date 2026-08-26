-- Sector-pack seed fixture: restaurant (es) — hub#1050.
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
-- Why it is SMALL: the published catalogue carried 583 statements, most of them more rows of
-- the same shape. What the assertion needs is one row per table shape, not a catalogue: the
-- statements below are lifted verbatim from it, keeping every column list intact and every
-- reference resolvable, so a schema drift still shows up here.
--
-- Contract (ADR-0007/0123): ids and refs TEXT, money INTEGER cents, rates REAL, flags 0/1 INTEGER,
-- dates/times ISO-8601 TEXT. Every statement is idempotent (`WHERE NOT EXISTS`), so re-applying it
-- neither duplicates nor fails. hub_id literal `00000000-0000-0000-0000-000000000001`: the runtime
-- rewrites identity rows to the hub being seeded.

INSERT INTO inventory_category (id, hub_id, name, slug, icon, "order", created_at, updated_at)
SELECT 'cat-restaurant-refrescos', '00000000-0000-0000-0000-000000000001', 'Refrescos y zumos', 'refrescos', 'nutrition-outline', 1, '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00'
WHERE NOT EXISTS (SELECT 1 FROM inventory_category WHERE hub_id = '00000000-0000-0000-0000-000000000001' AND name = 'Refrescos y zumos');
INSERT INTO inventory_category (id, hub_id, name, slug, icon, "order", created_at, updated_at)
SELECT 'cat-restaurant-carnes', '00000000-0000-0000-0000-000000000001', 'Carnes', 'carnes', 'restaurant-outline', 13, '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00'
WHERE NOT EXISTS (SELECT 1 FROM inventory_category WHERE hub_id = '00000000-0000-0000-0000-000000000001' AND name = 'Carnes');
INSERT INTO inventory_product (id, hub_id, name, sku, description, product_type, price, cost, stock, low_stock_threshold, tax_category_key, image, created_at, updated_at)
SELECT 'prod-restaurant-agua_con_gas', '00000000-0000-0000-0000-000000000001', 'Agua con gas', 'agua_con_gas', '', 'physical', 220, 0, 1000000000, 0, 'restaurant.drink', 'catalog/hospitality/agua_con_gas.webp', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00'
WHERE NOT EXISTS (SELECT 1 FROM inventory_product WHERE hub_id = '00000000-0000-0000-0000-000000000001' AND sku = 'agua_con_gas');
INSERT INTO inventory_product_categories (product_id, category_id)
SELECT 'prod-restaurant-agua_con_gas', 'cat-restaurant-refrescos'
WHERE NOT EXISTS (SELECT 1 FROM inventory_product_categories WHERE product_id = 'prod-restaurant-agua_con_gas' AND category_id = 'cat-restaurant-refrescos');
INSERT INTO inventory_product (id, hub_id, name, sku, description, product_type, price, cost, stock, low_stock_threshold, tax_category_key, image, created_at, updated_at)
SELECT 'prod-restaurant-alitas_pollo', '00000000-0000-0000-0000-000000000001', 'Alitas pollo', 'alitas_pollo', '', 'physical', 1350, 0, 1000000000, 0, 'restaurant.food', 'catalog/hospitality/alitas_pollo.webp', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00'
WHERE NOT EXISTS (SELECT 1 FROM inventory_product WHERE hub_id = '00000000-0000-0000-0000-000000000001' AND sku = 'alitas_pollo');
INSERT INTO inventory_product_categories (product_id, category_id)
SELECT 'prod-restaurant-alitas_pollo', 'cat-restaurant-carnes'
WHERE NOT EXISTS (SELECT 1 FROM inventory_product_categories WHERE product_id = 'prod-restaurant-alitas_pollo' AND category_id = 'cat-restaurant-carnes');
INSERT INTO hub_user (id, name, pin_hash, role, cloud_user_id, is_active, created_at)
SELECT 'user-restaurant-cashier1', 'Cajero 1', 'cashier1-seed-salt:9d81582af594e1cc780151726e43aceb5da668e780bf455ca41b6bfc0a7074ca', 'employee', NULL, 1, '2026-01-01T00:00:00+00:00'
WHERE NOT EXISTS (SELECT 1 FROM hub_user WHERE name = 'Cajero 1');
INSERT INTO staff_member (id, hub_id, first_name, last_name, user_id, status, is_bookable, created_at, updated_at)
SELECT 'staff-restaurant-cashier1', '00000000-0000-0000-0000-000000000001', 'Cajero', 'Uno', 'user-restaurant-cashier1', 'active', 0, '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00'
WHERE NOT EXISTS (SELECT 1 FROM staff_member WHERE id = 'staff-restaurant-cashier1');
INSERT INTO hub_user (id, name, pin_hash, role, cloud_user_id, is_active, created_at)
SELECT 'user-restaurant-cashier2', 'Cajero 2', 'cashier2-seed-salt:fe8ab1c960ef7d0abbbd1c7598ed2036f7aabc2408571edfdaff16d6bc1bdb0f', 'employee', NULL, 1, '2026-01-01T00:00:00+00:00'
WHERE NOT EXISTS (SELECT 1 FROM hub_user WHERE name = 'Cajero 2');
INSERT INTO staff_member (id, hub_id, first_name, last_name, user_id, status, is_bookable, created_at, updated_at)
SELECT 'staff-restaurant-cashier2', '00000000-0000-0000-0000-000000000001', 'Cajero', 'Dos', 'user-restaurant-cashier2', 'active', 0, '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00'
WHERE NOT EXISTS (SELECT 1 FROM staff_member WHERE id = 'staff-restaurant-cashier2');
