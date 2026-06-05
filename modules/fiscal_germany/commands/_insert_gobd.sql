-- Alta de una exportación de auditoría GoBD. Lo invoca el handler WASM (generate_gobd_export)
-- tras validar el rango de fechas y (en el futuro) recorrer las tablas contables.
-- Runtime inyecta :new_id, :hub_id, :current_user_id, :now.
INSERT INTO fiscal_germany_gobd_export
  (id, hub_id, period_start, period_end, generated_at, total_records, audit_zip_path,
   is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :period_start, :period_end, :generated_at, :total_records, :audit_zip_path,
   0, :current_user_id, :current_user_id, :now, :now);
