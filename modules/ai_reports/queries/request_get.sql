-- Una petición de informe AI por id (scope hub_id). Portado de AIReportService.get_request.
SELECT id, request_number, template_id, user_query, data_context,
       prompt_used, llm_response, tokens_used, cost_eur, status,
       requested_by_ref, started_at, completed_at, error_message, created_at
FROM ai_reports_request
WHERE id = :request_id AND hub_id = :hub_id AND is_deleted = 0;
