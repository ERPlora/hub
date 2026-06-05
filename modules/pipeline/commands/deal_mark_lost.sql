-- Marca un deal ABIERTO como perdido con un motivo libre. Runtime inyecta :hub_id,
-- :current_user_id, :now. Portado de PipelineService.mark_lost.
-- La guarda de estado (solo deals con status='open' pueden marcarse lost) se aplica en
-- el WHERE: si el deal ya está won/lost no actualiza nada. El runtime valida el motivo.
UPDATE pipeline_deal
SET status = 'lost',
    lost_at = :now,
    lost_reason = :reason,
    updated_by = :current_user_id,
    updated_at = :now
WHERE id = :deal_id AND hub_id = :hub_id AND is_deleted = 0 AND status = 'open';
