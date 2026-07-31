-- Command SIN contrato de mutación (legacy, hub#140): ausencia de `min_affected_rows` mantiene el
-- comportamiento de siempre — emite su evento aunque el WHERE case 0 filas. Prueba la
-- compatibilidad hacia atrás: ningún módulo publicado declara el campo nuevo.
UPDATE w140_items SET touched_at = :now
WHERE id = :item_id AND hub_id = :hub_id;
