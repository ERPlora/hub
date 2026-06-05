-- Borrado lógico (soft-delete) de regla de comisión. Runtime inyecta :hub_id, :now,
-- :current_user_id. Portado de CommissionsService.delete_rule.
-- OJO: la guarda "no borrar si tiene transacciones pending/approved" (has_dependents) es
-- lógica de validación previa → ver WASM-TODO §3. Esta sentencia solo marca is_deleted.
UPDATE commissions_rule
SET is_deleted = 1,
    deleted_at = :now,
    updated_by = :current_user_id,
    updated_at = :now
WHERE hub_id = :hub_id AND is_deleted = 0 AND id = :rule_id;
