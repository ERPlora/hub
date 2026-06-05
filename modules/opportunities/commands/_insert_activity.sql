-- Inserción de una actividad. Comando interno invocado por el handler WASM log_activity tras
-- resolver completed_at (NULL si scheduled_for; :now si la actividad es un registro inmediato).
-- Runtime inyecta :hub_id, :current_user_id, :now. El handler pasa :new_id, :completed_at
-- (NULL o :now) y :scheduled_for (NULL o ISO datetime).
INSERT INTO opportunities_activity
  (id, hub_id, opportunity_id, activity_type, description, scheduled_for,
   completed_at, completed_by_ref, is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :opportunity_id, :activity_type, :description, :scheduled_for,
   :completed_at, :completed_by_ref, 0, :current_user_id, :current_user_id, :now, :now);
