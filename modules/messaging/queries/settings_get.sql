-- Configuración de mensajería del hub (singleton por hub_id). Runtime inyecta :hub_id.
SELECT id, whatsapp_enabled, whatsapp_phone_id, whatsapp_business_id,
       sms_enabled, sms_provider, sms_sender_name,
       email_enabled, email_from_name, email_from_address,
       email_smtp_host, email_smtp_port, email_smtp_username, email_smtp_use_tls,
       appointment_reminder_enabled, appointment_reminder_hours,
       booking_confirmation_enabled
FROM messaging_settings
WHERE hub_id = :hub_id AND is_deleted = 0
LIMIT 1;
