-- Upsert de la configuración de nómina del hub (singleton uq_payroll_settings_hub).
-- Runtime inyecta :new_id, :hub_id, :current_user_id, :now. Portado de
-- PayrollSettingsService.update_settings. ON CONFLICT(hub_id) actualiza la fila existente.
-- La validación de default_pay_period (weekly|biweekly|monthly) la hace el JSON Schema.
INSERT INTO payroll_settings
  (id, hub_id, default_pay_period, currency, overtime_multiplier, night_shift_multiplier,
   holiday_multiplier, social_security_rate, income_tax_rate, auto_calculate_deductions,
   is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :default_pay_period, :currency, :overtime_multiplier, :night_shift_multiplier,
   :holiday_multiplier, :social_security_rate, :income_tax_rate, :auto_calculate_deductions,
   0, :current_user_id, :current_user_id, :now, :now)
ON CONFLICT(hub_id) DO UPDATE SET
   default_pay_period        = excluded.default_pay_period,
   currency                  = excluded.currency,
   overtime_multiplier       = excluded.overtime_multiplier,
   night_shift_multiplier    = excluded.night_shift_multiplier,
   holiday_multiplier        = excluded.holiday_multiplier,
   social_security_rate      = excluded.social_security_rate,
   income_tax_rate           = excluded.income_tax_rate,
   auto_calculate_deductions = excluded.auto_calculate_deductions,
   updated_by                = :current_user_id,
   updated_at                = :now,
   is_deleted                = 0,
   deleted_at                = NULL;
