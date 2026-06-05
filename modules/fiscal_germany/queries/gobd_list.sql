-- Lista de exportaciones de auditoría GoBD del hub. Runtime inyecta :hub_id.
SELECT id, period_start, period_end, generated_at, total_records, audit_zip_path, created_at
FROM fiscal_germany_gobd_export
WHERE hub_id = :hub_id AND is_deleted = 0
ORDER BY created_at DESC
LIMIT :limit;
