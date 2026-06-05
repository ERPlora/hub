-- Agregados de peticiones por estado en una ventana de :since_iso (created_at >= :since_iso).
-- Portado de AIReportService.get_request_stats (que ademas suma totales globales — esa
-- suma final la hace el SDK/UI sobre estas filas, o un handler WASM; ver WASM-TODO).
-- Runtime inyecta :hub_id. :since_iso es el timestamp ISO calculado por el caller.
SELECT status,
       COUNT(*)              AS count,
       SUM(tokens_used)      AS tokens,
       SUM(cost_eur)         AS cost_eur
FROM ai_reports_request
WHERE hub_id = :hub_id AND is_deleted = 0
  AND created_at >= :since_iso
GROUP BY status;
