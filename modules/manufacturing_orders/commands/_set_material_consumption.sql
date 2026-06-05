-- Fija el consumo real de una línea de material + su estado derivado. Comando interno
-- invocado por el handler WASM (record_consumption) tras validar la cantidad y derivar
-- status (consumed si consumido >= planificado, si no short). Runtime inyecta scope.
UPDATE manufacturing_orders_material
SET quantity_consumed = :quantity_consumed,
    status = :status,
    updated_by = :current_user_id,
    updated_at = :now
WHERE id = :material_consumption_id AND hub_id = :hub_id AND is_deleted = 0;
