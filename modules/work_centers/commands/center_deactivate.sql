-- Desactivación lógica de un centro (NO borra: solo is_active=0, lo saca de listados activos).
-- Portado de WorkCenterService.deactivate_center. La guarda "ya inactivo" se evalúa en runtime.
UPDATE work_centers_center
SET is_active = 0,
    updated_by = :current_user_id,
    updated_at = :now
WHERE id = :id AND hub_id = :hub_id AND is_deleted = 0;
