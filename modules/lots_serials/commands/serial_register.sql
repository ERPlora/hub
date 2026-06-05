-- Alta de número de serie. Runtime inyecta :new_id, :hub_id, :current_user_id, :now.
-- Portado de LotService.register_serial. El serial es único por hub (índice uq_serial_hub_serial).
-- La validación de que :lot_id existe (si no es NULL) la hace el runtime antes de ejecutar.
INSERT INTO lots_serials_serial
  (id, hub_id, serial, product_ref, lot_id, status, current_location_ref,
   sold_at, sold_to_customer, notes,
   is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :serial, :product_ref, :lot_id, 'in_stock', :current_location_ref,
   NULL, '', :notes,
   0, :current_user_id, :current_user_id, :now, :now);
