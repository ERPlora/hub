-- Eventos de runtime de un centro (con filtros opcionales). Runtime inyecta :hub_id.
-- Portado de WorkCenterService.list_events. :event_type ('' = sin filtro), :start_date y
-- :end_date ('' = sin filtro) y :limit los pasa el SDK/UI. Orden descendente por inicio.
SELECT id, work_center_id, event_type, started_at, ended_at,
       duration_minutes, reason, operator_ref, notes
FROM work_centers_event
WHERE hub_id = :hub_id AND is_deleted = 0
  AND work_center_id = :work_center_id
  AND (:event_type = '' OR event_type = :event_type)
  AND (:start_date = '' OR started_at >= :start_date)
  AND (:end_date  = '' OR started_at <= :end_date)
ORDER BY started_at DESC
LIMIT :limit;
