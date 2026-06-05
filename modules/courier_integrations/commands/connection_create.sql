-- Alta de conexión a la API de un transportista. Runtime inyecta :new_id, :hub_id,
-- :current_user_id, :now. Portado de CourierService.create_connection.
-- La validación de courier_code/environment (enum) la hace el JSON Schema; la unicidad
-- (hub_id, courier_code) la garantiza el índice uq_courier_conn_hub_code.
INSERT INTO courier_integrations_connection
  (id, hub_id, courier_code, name, api_endpoint, account_number,
   api_credentials_hash, environment, is_active, last_call_at, last_call_status,
   is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :courier_code, :name, :api_endpoint, :account_number,
   '', :environment, 1, NULL, '',
   0, :current_user_id, :current_user_id, :now, :now);
