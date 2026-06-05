-- Comando privado (helper de handler WASM). Marca un parte de horas como facturado y sella
-- invoiced_at. Usado por generate_invoice. Runtime inyecta :current_user_id, :now.
UPDATE project_billing_time_entry
SET is_invoiced = 1,
    invoiced_at = :now,
    updated_by = :current_user_id,
    updated_at = :now
WHERE id = :time_entry_id AND hub_id = :hub_id AND is_deleted = 0;
