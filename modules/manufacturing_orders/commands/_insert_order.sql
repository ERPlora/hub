-- Alta de cabecera de orden de fabricación. Comando interno invocado por el handler
-- WASM (create_mo) tras generar mo_number con el contador atómico y validar payload.
-- Runtime inyecta :hub_id, :current_user_id, :now; el WASM provee :new_id y :mo_number.
INSERT INTO manufacturing_orders_order
  (id, hub_id, mo_number, product_ref, quantity_planned, quantity_produced,
   scheduled_date, due_date, status, priority, work_center_ref, notes,
   started_at, completed_at,
   is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :mo_number, :product_ref, :quantity_planned, 0,
   :scheduled_date, :due_date, 'draft', :priority, :work_center_ref, :notes,
   NULL, NULL,
   0, :current_user_id, :current_user_id, :now, :now);
