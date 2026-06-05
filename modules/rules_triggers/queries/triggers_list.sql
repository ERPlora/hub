-- Triggers activos del hub (con filtro opcional por event_type). Runtime inyecta :hub_id.
-- Portado de RulesService.list_triggers (active_only por defecto, orden por created_at desc).
-- (:event_type = '' => sin filtro.)
SELECT id, code, name, event_type, entity_filter, is_active,
       last_fired_at, fire_count
FROM rules_triggers_trigger
WHERE hub_id = :hub_id AND is_deleted = 0 AND is_active = 1
  AND (:event_type = '' OR event_type = :event_type)
ORDER BY created_at DESC;
