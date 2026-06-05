-- Una campaña por id (scope hub_id). Portado de EmailMarketingService.get_campaign.
SELECT id, name, subject, sender_name, sender_email, list_id, status,
       scheduled_for, sent_at, html_content, plain_content,
       total_sent, total_opens, total_clicks, total_bounces, created_at
FROM email_marketing_campaign
WHERE id = :campaign_id AND hub_id = :hub_id AND is_deleted = 0;
