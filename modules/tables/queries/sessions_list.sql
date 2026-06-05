-- Lista de sesiones de mesa (activas o histórico). Runtime inyecta :hub_id.
-- Portado de TableService.list_sessions (orden por opened_at desc, limit 20).
-- Nota: duration_minutes (legacy property) se calcula en la UI/WASM, no en SQL.
SELECT s.id, s.table_id, t.number AS table_number, s.guests_count, s.status,
       s.waiter_id, s.opened_at, s.closed_at, s.notes
FROM tables_session s
LEFT JOIN tables_table t ON t.id = s.table_id AND t.is_deleted = 0
WHERE s.hub_id = :hub_id AND s.is_deleted = 0
ORDER BY s.opened_at DESC
LIMIT 20;
