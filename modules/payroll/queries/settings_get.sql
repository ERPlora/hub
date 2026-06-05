-- Configuración de nómina del hub (singleton). Runtime inyecta :hub_id.
-- Portado de PayrollSettingsService.get_settings. Si no hay fila, la UI usa defaults.
SELECT id, default_pay_period, currency, overtime_multiplier, night_shift_multiplier,
       holiday_multiplier, social_security_rate, income_tax_rate, auto_calculate_deductions
FROM payroll_settings
WHERE hub_id = :hub_id AND is_deleted = 0
LIMIT 1;
