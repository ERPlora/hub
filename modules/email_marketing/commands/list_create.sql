-- Alta de lista de destinatarios. Runtime inyecta :new_id, :hub_id, :current_user_id, :now.
-- Portado de EmailMarketingService.create_list. CRUD plano Tier 0; sin contador inicial (0).
INSERT INTO email_marketing_list
  (id, hub_id, name, description, is_active, total_subscribers,
   is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :name, :description, 1, 0,
   0, :current_user_id, :current_user_id, :now, :now);
