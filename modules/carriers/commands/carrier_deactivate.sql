-- Desactivación lógica de un transportista (NO borra: lo saca de futuras selecciones por defecto).
-- Portado de CarriersService.deactivate_carrier. El guard "ya inactivo" lo aplica el SDK/runtime.
UPDATE carriers_carrier
SET is_active = 0,
    updated_by = :current_user_id,
    updated_at = :now
WHERE id = :carrier_id AND hub_id = :hub_id AND is_deleted = 0;
