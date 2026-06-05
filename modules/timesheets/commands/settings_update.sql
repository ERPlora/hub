-- Upsert de la configuración (singleton) de timesheets del hub.
-- Runtime inyecta :new_id, :hub_id, :current_user_id, :now.
-- Portado de TimesheetService.update_settings (get_or_create + setattr). El índice
-- único uq_timesheets_settings_hub garantiza una sola fila por hub; ON CONFLICT
-- actualiza la existente. Los binds traen el valor final ya resuelto por el SDK
-- (los None del legacy se resuelven a los valores actuales antes de invocar).
INSERT INTO timesheets_settings
  (id, hub_id, default_billable, require_approval, approval_period,
   is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :default_billable, :require_approval, :approval_period,
   0, :current_user_id, :current_user_id, :now, :now)
ON CONFLICT (hub_id) DO UPDATE SET
   default_billable = excluded.default_billable,
   require_approval = excluded.require_approval,
   approval_period  = excluded.approval_period,
   updated_by       = :current_user_id,
   updated_at       = :now;
