-- Inserción de cabecera de oportunidad. Comando interno invocado por el handler WASM
-- create_opportunity tras generar opp_number atómico y resolver la probabilidad por etapa.
-- Runtime inyecta :hub_id, :current_user_id, :now. El handler pasa :new_id, :opp_number,
-- :probability (ya resuelta) y :value (ya validado).
INSERT INTO opportunities_opportunity
  (id, hub_id, opp_number, customer_name, customer_email, value, probability,
   expected_close_date, stage, close_reason, assigned_to_ref, notes,
   is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :opp_number, :customer_name, :customer_email, :value, :probability,
   :expected_close_date, :stage, '', :assigned_to_ref, :notes,
   0, :current_user_id, :current_user_id, :now, :now);
