-- Ajustes (singleton) del hub. Portado de SettingsService.get_settings.
-- Si no existe fila, el SDK/handler crea el default vía services.settings.update.
SELECT default_duration, default_buffer_time, default_tax_rate, show_prices,
       show_duration, allow_online_booking, include_tax_in_price, currency
FROM services_settings
WHERE hub_id = :hub_id AND is_deleted = 0
LIMIT 1;
