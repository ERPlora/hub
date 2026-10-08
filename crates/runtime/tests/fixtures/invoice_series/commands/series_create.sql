-- Alta de serie. Runtime inyecta :new_id, :hub_id, :current_user_id, :now.
-- Portado de InvoiceSeriesService.create_series. current_sequence arranca en 0, is_active=1.
-- NOTA: la unicidad de `code` por hub la garantiza el índice parcial uq_invoice_series_hub_code.
-- NOTA: si is_default=1, el degradado de la default hermana (mismo país+tipo) NO se hace aquí
-- (es lógica de invariante condicional) → se gestiona vía el command set_default (WASM). Ver WASM-TODO.md.
INSERT INTO invoice_series_series
  (id, hub_id, code, name, document_type, prefix, suffix, format,
   country_code, region_code, fiscal_year, current_sequence,
   is_default, is_active,
   is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :code, :name, :document_type, :prefix, :suffix, :format,
   :country_code, :region_code, :fiscal_year, 0,
   :is_default, 1,
   0, :current_user_id, :current_user_id, :now, :now);
