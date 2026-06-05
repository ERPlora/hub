-- Lista de sugerencias de aprovisionamiento; filtros opcionales por run, status y tipo.
-- Runtime inyecta :hub_id. Portado de MRPService.list_suggestions.
-- (:run_id / :status / :suggested_type = '' → ese filtro no se aplica.)
SELECT id, run_id, related_requirement_id, product_ref, suggested_type,
       quantity, suggested_date, lead_time_days, status, approved_by_ref, notes
FROM mrp_suggestion
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:run_id = ''         OR run_id = :run_id)
  AND (:status = ''         OR status = :status)
  AND (:suggested_type = '' OR suggested_type = :suggested_type)
ORDER BY created_at DESC
LIMIT :limit;
