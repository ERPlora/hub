-- Ajustes manuales del hub con filtro opcional por tipo. Runtime inyecta :hub_id.
-- Portado de routes.adjustment_list. :adjustment_type ('' = todos), :staff_id ('' = todos).
SELECT id, staff_id, staff_name, adjustment_type, amount, reason,
       payout_id, adjustment_date
FROM commissions_adjustment
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:adjustment_type = '' OR adjustment_type = :adjustment_type)
  AND (:staff_id        = '' OR staff_id        = :staff_id)
ORDER BY adjustment_date DESC, created_at DESC
LIMIT :limit;
