-- Seed suplementario de IVA España (hub#107). Lo aplica el instalador del runtime DESPUÉS de la
-- semilla propia del módulo `taxes`, SOLO para hubs cuyo `country_code` = ES (resuelto por el
-- instalador; por defecto ES, ADR-0085).
--
-- Por qué existe este fichero en el repo del HUB (no en el módulo `taxes`):
--   1) El módulo `taxes` ya siembra las categorías canónicas + las reglas IVA ES del *sector
--      restauración* (21% product/service/alcohol, 10% food/drink/delivery). Pero NO cubre el
--      **tipo superreducido del 4%** (pan, libros, medicamentos, alimentos básicos) ni el tipo
--      general del 21% ligado a categorías genéricas que un hub de hostelería usa al alta de
--      productos fuera del catálogo de restauración. Este seed COMPLETA la baseline IVA ES.
--   2) Es el vehículo idempotente (WHERE NOT EXISTS por la clave natural) para que un hub ES de
--      hostelería, al instalar `taxes`, arranque con una base fiscal UTIL —sin que el usuario
--      tenga que configurar el IVA a mano para poder vender (hub#107). Idéntica mecánica que la
--      semilla del módulo (`apply_module_seed`, ADR-0147): inyecta :hub_id/:now/:current_user_id.
--
-- IDEMPOTENTE y COMPOSICIÓN SEGURA con la semilla del módulo: misma clave natural
-- `(hub_id, country_code, tax_category_key, region_code, parent_id)` y mismo `id`
-- (`<hub_id>|taxrule|<CC>|<key>`), así que re-instalar `taxes` o re-aplicar este seed no duplica
-- (las `WHERE NOT EXISTS` del módulo y de aquí son compatibles). Mismo SQL en SQLite y Postgres
-- (TEXT + || estándar).

-- ── Categorías canónicas que la baseline del 4% necesita (la semilla del módulo no las trae) ──
INSERT INTO taxes_category (id, hub_id, key, name, description, is_system, is_active, is_deleted, created_by, updated_by, created_at, updated_at)
SELECT (:hub_id || '|taxcat|product.super_reduced'), :hub_id, 'product.super_reduced', 'Product — super-reduced (bread, books, basics)', '', 1, 1, 0, :current_user_id, :current_user_id, :now, :now
WHERE NOT EXISTS (SELECT 1 FROM taxes_category WHERE hub_id = :hub_id AND key = 'product.super_reduced');

INSERT INTO taxes_category (id, hub_id, key, name, description, is_system, is_active, is_deleted, created_by, updated_by, created_at, updated_at)
SELECT (:hub_id || '|taxcat|product.reduced'), :hub_id, 'product.reduced', 'Product — reduced (food staples, pharmacy)', '', 1, 1, 0, :current_user_id, :current_user_id, :now, :now
WHERE NOT EXISTS (SELECT 1 FROM taxes_category WHERE hub_id = :hub_id AND key = 'product.reduced');

-- ── Reglas IVA España: tipo GENERAL 21% (categorías genéricas) ──
-- region_code NULL = aplica a todo el país; vigentes desde 2012-09-01 (último cambio del IVA ES).
INSERT INTO taxes_rule (id, hub_id, country_code, region_code, tax_category_key, rate_pct, tax_type, parent_id, component_label, valid_from, valid_to, is_active, is_deleted, created_by, updated_by, created_at, updated_at)
SELECT (:hub_id || '|taxrule|ES|product.generic'), :hub_id, 'ES', NULL, 'product.generic', 21, 'vat', NULL, NULL, '2012-09-01', NULL, 1, 0, :current_user_id, :current_user_id, :now, :now
WHERE NOT EXISTS (SELECT 1 FROM taxes_rule WHERE hub_id = :hub_id AND country_code = 'ES' AND tax_category_key = 'product.generic' AND parent_id IS NULL AND region_code IS NULL);

INSERT INTO taxes_rule (id, hub_id, country_code, region_code, tax_category_key, rate_pct, tax_type, parent_id, component_label, valid_from, valid_to, is_active, is_deleted, created_by, updated_by, created_at, updated_at)
SELECT (:hub_id || '|taxrule|ES|service.generic'), :hub_id, 'ES', NULL, 'service.generic', 21, 'vat', NULL, NULL, '2012-09-01', NULL, 1, 0, :current_user_id, :current_user_id, :now, :now
WHERE NOT EXISTS (SELECT 1 FROM taxes_rule WHERE hub_id = :hub_id AND country_code = 'ES' AND tax_category_key = 'service.generic' AND parent_id IS NULL AND region_code IS NULL);

-- ── Reglas IVA España: tipo REDUCIDO 10% (hostelería: comida/bebida en local, para llevar) ──
INSERT INTO taxes_rule (id, hub_id, country_code, region_code, tax_category_key, rate_pct, tax_type, parent_id, component_label, valid_from, valid_to, is_active, is_deleted, created_by, updated_by, created_at, updated_at)
SELECT (:hub_id || '|taxrule|ES|restaurant.food'), :hub_id, 'ES', NULL, 'restaurant.food', 10, 'vat', NULL, NULL, '2012-09-01', NULL, 1, 0, :current_user_id, :current_user_id, :now, :now
WHERE NOT EXISTS (SELECT 1 FROM taxes_rule WHERE hub_id = :hub_id AND country_code = 'ES' AND tax_category_key = 'restaurant.food' AND parent_id IS NULL AND region_code IS NULL);

INSERT INTO taxes_rule (id, hub_id, country_code, region_code, tax_category_key, rate_pct, tax_type, parent_id, component_label, valid_from, valid_to, is_active, is_deleted, created_by, updated_by, created_at, updated_at)
SELECT (:hub_id || '|taxrule|ES|restaurant.drink'), :hub_id, 'ES', NULL, 'restaurant.drink', 10, 'vat', NULL, NULL, '2012-09-01', NULL, 1, 0, :current_user_id, :current_user_id, :now, :now
WHERE NOT EXISTS (SELECT 1 FROM taxes_rule WHERE hub_id = :hub_id AND country_code = 'ES' AND tax_category_key = 'restaurant.drink' AND parent_id IS NULL AND region_code IS NULL);

INSERT INTO taxes_rule (id, hub_id, country_code, region_code, tax_category_key, rate_pct, tax_type, parent_id, component_label, valid_from, valid_to, is_active, is_deleted, created_by, updated_by, created_at, updated_at)
SELECT (:hub_id || '|taxrule|ES|restaurant.delivery'), :hub_id, 'ES', NULL, 'restaurant.delivery', 10, 'vat', NULL, NULL, '2012-09-01', NULL, 1, 0, :current_user_id, :current_user_id, :now, :now
WHERE NOT EXISTS (SELECT 1 FROM taxes_rule WHERE hub_id = :hub_id AND country_code = 'ES' AND tax_category_key = 'restaurant.delivery' AND parent_id IS NULL AND region_code IS NULL);

INSERT INTO taxes_rule (id, hub_id, country_code, region_code, tax_category_key, rate_pct, tax_type, parent_id, component_label, valid_from, valid_to, is_active, is_deleted, created_by, updated_by, created_at, updated_at)
SELECT (:hub_id || '|taxrule|ES|product.reduced'), :hub_id, 'ES', NULL, 'product.reduced', 10, 'vat', NULL, NULL, '2012-09-01', NULL, 1, 0, :current_user_id, :current_user_id, :now, :now
WHERE NOT EXISTS (SELECT 1 FROM taxes_rule WHERE hub_id = :hub_id AND country_code = 'ES' AND tax_category_key = 'product.reduced' AND parent_id IS NULL AND region_code IS NULL);

-- ── Reglas IVA España: tipo SUPERREDUCIDO 4% (pan, libros, medicamentos, alimentos básicos) ──
-- Este es el tipo que faltaba (hub#107): sin él, un producto dado de alta en una categoría
-- básica no resuelve regla y el cálculo de IVA / factura falla o degrada al fallback.
INSERT INTO taxes_rule (id, hub_id, country_code, region_code, tax_category_key, rate_pct, tax_type, parent_id, component_label, valid_from, valid_to, is_active, is_deleted, created_by, updated_by, created_at, updated_at)
SELECT (:hub_id || '|taxrule|ES|product.super_reduced'), :hub_id, 'ES', NULL, 'product.super_reduced', 4, 'vat', NULL, NULL, '2012-09-01', NULL, 1, 0, :current_user_id, :current_user_id, :now, :now
WHERE NOT EXISTS (SELECT 1 FROM taxes_rule WHERE hub_id = :hub_id AND country_code = 'ES' AND tax_category_key = 'product.super_reduced' AND parent_id IS NULL AND region_code IS NULL);
