-- Inserción interna de un evento de webhook, invocada por el handler WASM record_event tras
-- resolver idempotencia (event_id ya presente → no inserta). El handler aporta :new_id,
-- :store_id, :event_type, :event_id, :occurred_at, :payload. Runtime inyecta :hub_id,
-- :current_user_id, :now. status arranca en 'received'.
INSERT INTO uber_eats_event
  (id, hub_id, store_id, event_type, event_id, occurred_at, processed_at, payload, status,
   is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :store_id, :event_type, :event_id, :occurred_at, NULL, :payload, 'received',
   0, :current_user_id, :current_user_id, :now, :now);
