-- Alta de una línea de consumo de material. Comando interno invocado por el handler
-- WASM (create_mo) por cada material validado. Runtime inyecta :hub_id,
-- :current_user_id, :now; el WASM provee :new_id y :mo_id (cabecera ya insertada).
INSERT INTO manufacturing_orders_material
  (id, hub_id, mo_id, material_ref, quantity_planned, quantity_consumed, unit, status,
   is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :mo_id, :material_ref, :quantity_planned, 0, :unit, 'pending',
   0, :current_user_id, :current_user_id, :now, :now);
