-- Carts with an OPTIONAL scope bind, written with the null-tolerant idiom the catalogue
-- modules already use (services#44): `:include_archived` absent = NULL = default scope.
-- The module HANDLED the null itself, in the SQL — the engine must let it through (hub#1086).
SELECT c.id AS id, c.name AS name, c.archived AS archived
FROM lbind_cart c
WHERE c.hub_id = :hub_id
  AND (COALESCE(CAST(:include_archived AS TEXT), '0') IN ('1', 'true') OR c.archived = 0)
