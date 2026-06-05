-- Detalle de un lote. Runtime inyecta :hub_id. Portado de LotService.get_lot
-- (la lista de movimientos se obtiene aparte vía lots_serials.movements.list).
SELECT id, lot_number, product_ref, manufactured_date, expiry_date,
       quantity_initial, quantity_current, status, notes, created_at
FROM lots_serials_lot
WHERE id = :lot_id AND hub_id = :hub_id AND is_deleted = 0;
