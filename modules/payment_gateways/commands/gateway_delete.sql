-- Soft-delete de pasarela (coherente con el contrato de fila §2.5).
UPDATE payment_gateways_gateway
SET is_deleted = 1, deleted_at = :now, is_active = 0,
    updated_by = :current_user_id, updated_at = :now
WHERE id = :gateway_id AND hub_id = :hub_id;
