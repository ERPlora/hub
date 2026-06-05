-- Acuse de una alerta de crédito. Runtime inyecta :current_user_id, :now.
-- Portado de CreditRiskService.acknowledge_alert. Solo marca alertas no acusadas (acknowledged_at
-- IS NULL). El append opcional de :notes con prefijo [ACK] se aplica aquí.
UPDATE credit_risk_alert
SET acknowledged_at = :now,
    acknowledged_by_ref = :current_user_id,
    notes = CASE
              WHEN :notes = '' THEN notes
              WHEN notes = ''  THEN '[ACK] ' || :notes
              ELSE notes || char(10) || '[ACK] ' || :notes
            END,
    updated_by = :current_user_id,
    updated_at = :now
WHERE id = :alert_id AND hub_id = :hub_id AND is_deleted = 0
  AND acknowledged_at IS NULL;
