-- Transición generated → sent tras subir el fichero al banco. Runtime inyecta :hub_id,
-- :current_user_id, :now. Portado de SepaService.mark_sent (solo desde status='generated').
UPDATE sepa_remittances_remittance
SET status     = 'sent',
    sent_at    = :now,
    updated_by = :current_user_id,
    updated_at = :now
WHERE id = :remittance_id AND hub_id = :hub_id AND is_deleted = 0 AND status = 'generated';
