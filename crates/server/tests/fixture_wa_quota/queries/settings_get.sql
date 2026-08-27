SELECT hub_id, free_tier_monthly_limit, greeting
FROM whatsapp_inbox_settings
WHERE hub_id = :hub_id AND is_deleted = 0;
