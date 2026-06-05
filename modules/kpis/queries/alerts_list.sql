-- Alertas del hub (por defecto las no reconocidas, más recientes primero).
-- Portado de KPIService.list_alerts. Runtime inyecta :hub_id.
-- Filtros: :status (unacknowledged|acknowledged|all) lo decide el SDK pasando
-- :only_unack (1 = solo acknowledged_at NULL, 0 = todas); :kpi_id ('' = sin filtro);
-- :alert_type ('' = sin filtro).
SELECT id, kpi_id, value_id, alert_type, triggered_at, message,
       acknowledged_at, acknowledged_by_ref
FROM kpis_alert
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:only_unack = 0 OR acknowledged_at IS NULL)
  AND (:kpi_id = '' OR kpi_id = :kpi_id)
  AND (:alert_type = '' OR alert_type = :alert_type)
ORDER BY triggered_at DESC;
