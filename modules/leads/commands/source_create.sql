-- Alta de origen de lead. Runtime inyecta :new_id, :hub_id, :current_user_id, :now.
-- Portado de LeadService.create_source (code único por hub — lo garantiza el índice
-- uq_leads_source_hub_code).
INSERT INTO leads_source
  (id, hub_id, code, name, is_active,
   is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :code, :name, 1,
   0, :current_user_id, :current_user_id, :now, :now);
