-- Lotes activos cuya fecha de caducidad cae dentro del horizonte. Runtime inyecta :hub_id.
-- Portado de LotService.check_expiring_lots. El llamador (UI/SDK) calcula :horizon = hoy + within_days
-- (ISO YYYY-MM-DD) y lo pasa como bind. Solo lotes 'active' con expiry_date no nula y <= horizonte
-- (incluye ya-caducados). El cálculo today + within_days lo hace el runtime (capacidad de reloj).
SELECT id, lot_number, product_ref, manufactured_date, expiry_date,
       quantity_initial, quantity_current, status, notes, created_at
FROM lots_serials_lot
WHERE hub_id = :hub_id AND is_deleted = 0
  AND status = 'active'
  AND expiry_date IS NOT NULL
  AND expiry_date <= :horizon
ORDER BY expiry_date ASC;
