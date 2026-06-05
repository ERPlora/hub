-- Un cobro por id (scope hub_id). Portado de CollectionService.get_collection.
-- Las asignaciones del cobro y los totales (total_allocated / unallocated_amount) se
-- obtienen por separado: las filas vía collections.allocations.list y la aritmética
-- la calcula el SDK/UI (o un handler WASM). Aquí solo la cabecera del cobro.
SELECT id, reference, collection_date, amount, currency,
       payer_name, payer_iban, concept, method, status, notes, created_at
FROM collections_collection
WHERE id = :collection_id AND hub_id = :hub_id AND is_deleted = 0;
