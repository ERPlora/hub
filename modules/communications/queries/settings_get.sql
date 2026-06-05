-- Ajustes singleton del hub (incluye configuración del footer). El runtime inyecta :hub_id.
-- Devuelve 0 o 1 fila; si no existe, la UI usa valores por defecto y crea vía settings.upsert.
SELECT id, is_enabled, gpt_routing_enabled, gpt_routing_prompt,
       email_sync_interval_seconds, email_max_sync_days, auto_close_hours,
       notify_on_new_thread, notify_on_assignment,
       footer_enabled, footer_html, footer_include_logo, footer_logo_url,
       footer_company_name, footer_address, footer_phone, footer_website,
       footer_social_links
FROM communications_settings
WHERE hub_id = :hub_id AND is_deleted = 0
LIMIT 1;
