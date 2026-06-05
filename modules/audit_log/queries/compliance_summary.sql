-- Resumen de cumplimiento: recuentos por event_type y severity en un rango de fechas.
-- Portado de AuditService.get_compliance_summary. Runtime inyecta :hub_id.
-- El legacy hace dos agregaciones separadas (por event_type y por severity); aquí devolvemos
-- una sola rejilla (event_type, severity, count) y el SDK/UI hace el pivot a by_event_type /
-- by_severity / total. :start_date/:end_date son ISO 8601 (requeridos).
SELECT event_type, severity, COUNT(*) AS count
FROM audit_log_event
WHERE hub_id = :hub_id AND is_deleted = 0
  AND occurred_at >= :start_date
  AND occurred_at <= :end_date
GROUP BY event_type, severity
ORDER BY event_type ASC, severity ASC;
