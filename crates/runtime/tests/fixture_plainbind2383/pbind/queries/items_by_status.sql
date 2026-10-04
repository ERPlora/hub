-- The optional-filter idiom of `appointments.appointments.list`: the module handles the NULL
-- itself (COALESCE on one occurrence), so an absent `:status` means "every status".
SELECT i.id AS id
FROM pbind_item i
WHERE i.hub_id = :hub_id
  AND (COALESCE(CAST(:status AS text), '') = '' OR i.status = :status)
ORDER BY i.id
