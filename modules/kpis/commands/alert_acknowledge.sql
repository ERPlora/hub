-- Reconocimiento de una alerta (estampa acknowledged_at/by). Runtime inyecta
-- :hub_id, :current_user_id, :now. Portado de KPIService.acknowledge_alert.
-- La guarda de idempotencia (rechazar si ya está reconocida) la asegura el filtro
-- acknowledged_at IS NULL. El append de notas con timestamp al campo message va a
-- WASM si se quiere conservar (ver WASM-TODO); aquí solo se estampa el reconocimiento.
UPDATE kpis_alert
SET acknowledged_at     = :now,
    acknowledged_by_ref = :acknowledged_by_ref,
    updated_by          = :current_user_id,
    updated_at          = :now
WHERE id = :alert_id AND hub_id = :hub_id AND is_deleted = 0
  AND acknowledged_at IS NULL;
