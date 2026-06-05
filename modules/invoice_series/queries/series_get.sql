-- Una serie por id (scope hub_id). Portado de InvoiceSeriesService.get_series.
SELECT id, code, name, document_type, prefix, suffix, format,
       country_code, region_code, fiscal_year, current_sequence,
       is_default, is_active, start_date, end_date, created_at
FROM invoice_series_series
WHERE id = :series_id AND hub_id = :hub_id AND is_deleted = 0;
