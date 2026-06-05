-- Una zona por id (scope hub_id). Portado de TableService.get_zone.
SELECT id, name, description, color, sort_order, is_active
FROM tables_zone
WHERE id = :zone_id AND hub_id = :hub_id AND is_deleted = 0;
