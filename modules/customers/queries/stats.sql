-- Contadores del dashboard: total, activos, VIP, ingresos totales.
SELECT
  COUNT(*)                                                      AS total,
  COALESCE(SUM(CASE WHEN is_active = 1 THEN 1 ELSE 0 END), 0)   AS active,
  COALESCE(SUM(CASE WHEN lifecycle_stage = 'vip' THEN 1 ELSE 0 END), 0) AS vip,
  COALESCE(SUM(total_spent), 0)                                 AS total_revenue
FROM customers_customer
WHERE hub_id = :hub_id AND is_deleted = 0;
