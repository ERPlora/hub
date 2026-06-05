-- Entradas de cadena (TraceChain) de un chain_id "<entity_type>:<entity_ref>". Scope hub_id.
-- Las usa el handler WASM recall_impact como datos de entrada para recorrer el grafo
-- (parent_event_id → event_id). El runtime las lee y se las pasa al WASM; el WASM no toca la BD.
SELECT id, chain_id, parent_event_id, event_id
FROM traceability_chain
WHERE hub_id = :hub_id AND is_deleted = 0
  AND chain_id = :chain_id;
