-- Un item de referencia por hub (idempotente por clave natural, ADR-0147). Da filas a la
-- query pública `menu.items.list` sin depender de una escritura previa. `:hub_id`/`:now`/
-- `:current_user_id` los inyecta el runtime al sembrar.
INSERT INTO menu_items (id, hub_id, name, is_deleted, created_by, updated_by, created_at, updated_at)
SELECT 'seed-cafe', :hub_id, 'Cafe con leche', 0, :current_user_id, :current_user_id, :now, :now
WHERE NOT EXISTS (
    SELECT 1 FROM menu_items WHERE hub_id = :hub_id AND id = 'seed-cafe'
);
