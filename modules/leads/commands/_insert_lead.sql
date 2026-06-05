-- Inserción de un lead. Comando INTERNO invocado por el handler WASM (create_lead)
-- una vez generado el lead_number atómico y validados los campos. Runtime inyecta
-- :new_id, :hub_id, :current_user_id, :now. status arranca en 'new'.
INSERT INTO leads_lead
  (id, hub_id, lead_number, first_name, last_name, email, phone, company, job_title,
   source_id, status, assigned_to_ref, estimated_value, notes,
   contacted_at, qualified_at, converted_at,
   is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :lead_number, :first_name, :last_name, :email, :phone, :company, :job_title,
   :source_id, 'new', :assigned_to, :estimated_value, :notes,
   NULL, NULL, NULL,
   0, :current_user_id, :current_user_id, :now, :now);
