-- Revocación de un mandato activo (solo si status='active'). Runtime inyecta :hub_id,
-- :current_user_id, :now. Portado de SepaService.revoke_mandate.
-- El append del motivo a notes y el guard de estado fuera de 'active' van a runtime/WASM
-- si se requiere mensaje de error específico — ver WASM-TODO §append-notes (no bloqueante).
UPDATE sepa_remittances_mandate
SET status     = 'revoked',
    revoked_at = :now,
    updated_by = :current_user_id,
    updated_at = :now
WHERE id = :mandate_id AND hub_id = :hub_id AND is_deleted = 0 AND status = 'active';
