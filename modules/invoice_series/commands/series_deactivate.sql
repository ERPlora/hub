-- Desactivación suave de una serie (deja de poder emitir números). Portado de
-- InvoiceSeriesService.deactivate_series: marca is_active=0 y, si era la default, la degrada.
-- NO es un soft-delete: la serie sigue existiendo (auditoría fiscal), solo queda inactiva.
UPDATE invoice_series_series SET
  is_active  = 0,
  is_default = 0,
  updated_by = :current_user_id,
  updated_at = :now
WHERE id = :series_id AND hub_id = :hub_id AND is_deleted = 0;
