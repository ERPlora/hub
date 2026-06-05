-- Helper interno: inserta un aviso e-Transport en estado 'draft'. Lo invoca el
-- handler WASM tras generar el document_number atómico (ETR-YYYYMMDD-NNNN) y validar.
-- :goods es JSON serializado por el handler. Runtime inyecta :hub_id, :current_user_id, :now.
INSERT INTO fiscal_romania_etransport
  (id, hub_id, document_number, transport_type, origin_city, destination_city,
   vehicle_plate, departure_date, goods, status,
   is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :document_number, :transport_type, :origin_city, :destination_city,
   :vehicle_plate, :departure_date, :goods, 'draft',
   0, :current_user_id, :current_user_id, :now, :now);
