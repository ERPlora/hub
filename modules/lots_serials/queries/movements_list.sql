-- Movimientos de un lote, más reciente primero. Runtime inyecta :hub_id.
-- Portado de la segunda mitad de LotService.get_lot.
SELECT id, lot_id, movement_type, quantity_delta, reference, occurred_at, notes
FROM lots_serials_movement
WHERE lot_id = :lot_id AND hub_id = :hub_id AND is_deleted = 0
ORDER BY occurred_at DESC;
