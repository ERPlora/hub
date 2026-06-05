-- Peticiones de informe AI recientes con filtros opcionales. Runtime inyecta :hub_id.
-- Portado de AIReportService.list_requests. Binds opcionales: :status y :requested_by
-- ('' = sin filtro). :limit acota el nº de filas devueltas (orden por created_at desc).
SELECT id, request_number, template_id, user_query, data_context,
       prompt_used, llm_response, tokens_used, cost_eur, status,
       requested_by_ref, started_at, completed_at, error_message, created_at
FROM ai_reports_request
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:status       = '' OR status           = :status)
  AND (:requested_by = '' OR requested_by_ref = :requested_by)
ORDER BY created_at DESC
LIMIT :limit;
