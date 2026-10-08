-- Lista de series del hub con filtros opcionales. Runtime inyecta :hub_id.
-- Portado de InvoiceSeriesService.list_series (filtros document_type/country_code/active_only;
-- orden por defecto primero, luego por código). Los binds opcionales se neutralizan con '' (= sin filtro).
SELECT id, code, name, document_type, prefix, suffix, format,
       country_code, region_code, fiscal_year, current_sequence,
       is_default, is_active, start_date, end_date, created_at
FROM invoice_series_series
WHERE hub_id = :hub_id
  AND is_deleted = 0
