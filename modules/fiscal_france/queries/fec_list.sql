-- Exports FEC generados por el hub (solo metadatos; el payload no se persiste). Runtime inyecta :hub_id.
SELECT id, period_start, period_end, format_type, generated_at, total_entries, created_at
FROM fiscal_france_fec
WHERE hub_id = :hub_id AND is_deleted = 0
ORDER BY created_at DESC
LIMIT :limit;
