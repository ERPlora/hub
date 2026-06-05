-- Alta de campaña en estado draft. Runtime inyecta :new_id, :hub_id, :current_user_id, :now.
-- Portado de EmailMarketingService.create_campaign. La validación de existencia de la lista
-- (list_id pertenece al hub) la garantiza el runtime; CRUD plano Tier 0.
INSERT INTO email_marketing_campaign
  (id, hub_id, name, subject, sender_name, sender_email, list_id,
   html_content, plain_content, status, scheduled_for, sent_at,
   total_sent, total_opens, total_clicks, total_bounces,
   is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :name, :subject, :sender_name, :sender_email, :list_id,
   :html_content, :plain_content, 'draft', NULL, NULL,
   0, 0, 0, 0,
   0, :current_user_id, :current_user_id, :now, :now);
