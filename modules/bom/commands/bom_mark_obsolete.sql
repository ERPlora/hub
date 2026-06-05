-- Marca una BOM como obsolete y limpia el flag default. Portado de BOMService.mark_obsolete.
-- Runtime inyecta :hub_id, :current_user_id, :now. El rastro textual del motivo (reason)
-- en notes (concatenación con prefijo [OBSOLETE]) lo compone el handler/host si se quiere
-- conservar — ver WASM-TODO. Aquí solo se cambia el estado. No afecta filas ya obsolete.
UPDATE bom_bom
SET status = 'obsolete',
    is_default = 0,
    updated_by = :current_user_id,
    updated_at = :now
WHERE id = :bom_id AND hub_id = :hub_id AND is_deleted = 0 AND status != 'obsolete';
