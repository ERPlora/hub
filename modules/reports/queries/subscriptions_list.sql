-- Suscripciones del hub (con filtro opcional por informe). Runtime inyecta :hub_id.
-- Portado de ReportService.list_subscriptions. Bind :report_id: '' = sin filtro.
SELECT id, report_id, subscriber_ref, frequency, delivery_method,
       is_active, last_sent_at, created_at
FROM reports_subscription
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:report_id = '' OR report_id = :report_id)
ORDER BY created_at DESC;
