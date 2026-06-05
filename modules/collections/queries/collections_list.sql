-- Cobros del hub (con filtros opcionales). Runtime inyecta :hub_id.
-- Portado de CollectionService.list_collections. Los binds :status y :payer_name
-- deben pasarse siempre ('' = sin filtro). El filtro payer_name es por prefijo/contiene.
SELECT id, reference, collection_date, amount, currency,
       payer_name, payer_iban, concept, method, status, notes, created_at
FROM collections_collection
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:status = '' OR status = :status)
  AND (:payer_name = '' OR payer_name LIKE '%' || :payer_name || '%')
ORDER BY collection_date DESC, created_at DESC;
