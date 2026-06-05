-- Edición de mesa (campos editables; la UI envía el conjunto completo, Tier 0).
-- Portado de TableService.update_table SIN sus guardas (validación de estado y
-- bloqueo de desactivación con sesión activa viven en WASM — ver WASM-TODO.md).
UPDATE tables_table SET
  number = :number,
  name = :name,
  capacity = :capacity,
  zone_id = :zone_id,
  shape = :shape,
  status = :status,
  is_active = :is_active,
  updated_by = :current_user_id,
  updated_at = :now
WHERE id = :table_id AND hub_id = :hub_id AND is_deleted = 0;
