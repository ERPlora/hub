-- Upsert de ajustes de comisiones (singleton por hub). Runtime inyecta :new_id, :hub_id,
-- :current_user_id, :now. Portado de routes.settings_save. uq_commissions_settings_hub
-- garantiza un único registro: el ON CONFLICT(hub_id) actualiza la fila existente.
INSERT INTO commissions_settings
  (id, hub_id, default_commission_rate, calculation_basis, payout_frequency, payout_day,
   minimum_payout_amount, apply_tax_withholding, tax_withholding_rate,
   show_commission_on_receipt, show_pending_commission,
   is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :default_commission_rate, :calculation_basis, :payout_frequency, :payout_day,
   :minimum_payout_amount, :apply_tax_withholding, :tax_withholding_rate,
   :show_commission_on_receipt, :show_pending_commission,
   0, :current_user_id, :current_user_id, :now, :now)
ON CONFLICT(hub_id) DO UPDATE SET
  default_commission_rate    = excluded.default_commission_rate,
  calculation_basis          = excluded.calculation_basis,
  payout_frequency           = excluded.payout_frequency,
  payout_day                 = excluded.payout_day,
  minimum_payout_amount      = excluded.minimum_payout_amount,
  apply_tax_withholding      = excluded.apply_tax_withholding,
  tax_withholding_rate       = excluded.tax_withholding_rate,
  show_commission_on_receipt = excluded.show_commission_on_receipt,
  show_pending_commission    = excluded.show_pending_commission,
  is_deleted                 = 0,
  deleted_at                 = NULL,
  updated_by                 = :current_user_id,
  updated_at                 = :now;
