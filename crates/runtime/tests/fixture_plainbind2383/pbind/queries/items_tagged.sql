-- The other optional idiom: the bind is tested with IS NULL, so absent means "any tag".
SELECT i.id AS id
FROM pbind_item i
WHERE i.hub_id = :hub_id
  AND (CAST(:tag AS text) IS NULL OR i.tag = :tag)
ORDER BY i.id
