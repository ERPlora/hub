-- Alertas de crédito del hub (filtros opcionales por severidad y acuse). Runtime inyecta :hub_id.
-- Portado de CreditRiskService.list_alerts. :severity '' = sin filtro. :acknowledged: ''=todas,
-- 'true'=solo con acuse, 'false'=solo sin acuse.
SELECT id, customer_credit_id, alert_type, severity, triggered_at,
       acknowledged_at, acknowledged_by_ref, resolved_at, notes
FROM credit_risk_alert
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:severity = '' OR severity = :severity)
  AND (:acknowledged = ''
       OR (:acknowledged = 'true'  AND acknowledged_at IS NOT NULL)
       OR (:acknowledged = 'false' AND acknowledged_at IS NULL))
ORDER BY triggered_at DESC;
