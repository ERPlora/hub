-- Aprueba una BOM: draft → active, estampando aprobador y fecha.
-- Runtime inyecta :hub_id, :current_user_id, :now. Portado de BOMService.approve_bom.
-- La guarda de estado (solo draft puede aprobarse) la aplica el runtime: este UPDATE
-- solo afecta filas en draft, así que una BOM ya active/obsolete no cambia.
UPDATE bom_bom
SET status = 'active',
    approved_by_ref = :current_user_id,
    approved_at = :now,
    updated_by = :current_user_id,
    updated_at = :now
WHERE id = :bom_id AND hub_id = :hub_id AND is_deleted = 0 AND status = 'draft';
