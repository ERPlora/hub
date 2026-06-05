-- Alta de plantilla de email. Portado de TemplateService.create_template.
-- Runtime inyecta :new_id, :hub_id, :current_user_id, :now. :variables es JSON (TEXT).
INSERT INTO communications_email_template
  (id, hub_id, name, subject, body_html, body_text, variables, is_active,
   is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :name, :subject, :body_html, :body_text, :variables, 1,
   0, :current_user_id, :current_user_id, :now, :now);
