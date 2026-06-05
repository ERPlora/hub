-- Edición de campos mutables de una serie. Portado de InvoiceSeriesService.update_series.
-- Campos editables: name, prefix, suffix, format, country_code, region_code,
-- start_date, end_date, is_active. `code` y `current_sequence` NO son editables
-- desde aquí para preservar la integridad fiscal (igual que el legacy).
UPDATE invoice_series_series SET
  name         = :name,
  prefix       = :prefix,
  suffix       = :suffix,
  format       = :format,
  country_code = :country_code,
  region_code  = :region_code,
  start_date   = :start_date,
  end_date     = :end_date,
  is_active    = :is_active,
  updated_by   = :current_user_id,
  updated_at   = :now
WHERE id = :series_id AND hub_id = :hub_id AND is_deleted = 0;
