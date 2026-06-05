-- Alta de evento de seguimiento sobre un envío. Runtime inyecta :new_id, :hub_id,
-- :current_user_id, :now. Portado de CarriersService.record_tracking_event.
-- occurred_at: si no se pasa, el SDK/WASM rellena con :now. raw_data llega como JSON-TEXT o NULL.
INSERT INTO carriers_tracking_event
  (id, hub_id, shipment_id, event_code, description, location, occurred_at, raw_data,
   is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :shipment_id, :event_code, :description, :location, :occurred_at, :raw_data,
   0, :current_user_id, :current_user_id, :now, :now);
