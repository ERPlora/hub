-- Alta de almacén. Runtime inyecta :new_id, :hub_id, :current_user_id, :now.
-- Portado de LocationService.create_warehouse. (hub_id, code) único lo garantiza el
-- índice uq_locations_warehouse_hub_code.
--
-- Invariant "un solo almacén por defecto por hub": si :is_default = 1, primero se
-- degradan los demás defaults. La UPDATE está guardada por el bind, así que con
-- :is_default = 0 es un no-op (no toca filas). Ambas sentencias corren en la misma
-- transacción (transaction: true).
UPDATE locations_warehouse
SET is_default = 0,
    updated_by = :current_user_id,
    updated_at = :now
WHERE hub_id = :hub_id AND is_deleted = 0 AND is_default = 1 AND :is_default = 1;

INSERT INTO locations_warehouse
  (id, hub_id, code, name, address, is_active, is_default,
   is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :code, :name, :address, 1, :is_default,
   0, :current_user_id, :current_user_id, :now, :now);
