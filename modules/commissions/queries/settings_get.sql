-- Ajustes de comisiones del hub (singleton). Runtime inyecta :hub_id.
-- Portado de routes._get_settings. Si no hay fila, el SDK/UI muestra defaults y el
-- comando settings.upsert crea la fila al guardar.
SELECT id, default_commission_rate, calculation_basis, payout_frequency, payout_day,
       minimum_payout_amount, apply_tax_withholding, tax_withholding_rate,
       show_commission_on_receipt, show_pending_commission
FROM commissions_settings
WHERE hub_id = :hub_id AND is_deleted = 0
LIMIT 1;
