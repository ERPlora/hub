-- Edición de zona (la UI envía el conjunto completo de campos editables, Tier 0).
-- Portado de TableService.update_zone.
UPDATE tables_zone SET
  name = :name,
  description = :description,
  color = :color,
  sort_order = :sort_order,
  is_active = :is_active,
  updated_by = :current_user_id,
  updated_at = :now
WHERE id = :zone_id AND hub_id = :hub_id AND is_deleted = 0;
