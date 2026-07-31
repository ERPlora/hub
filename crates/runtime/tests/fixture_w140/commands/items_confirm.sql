-- Command de TRANSICIÓN (hub#140): un UPDATE ... WHERE que casa 0 filas cuando el ítem no existe
-- o ya está confirmado. Con `min_affected_rows: 1`, ese 0 revierte la tx entera y NO emite
-- `w140.item.confirmed` — exactamente el bug del issue (confirmar una cita inexistente emitía el
-- evento de todos modos).
UPDATE w140_items SET status = 'confirmed', updated_at = :now
WHERE id = :item_id AND hub_id = :hub_id AND status = 'pending';
