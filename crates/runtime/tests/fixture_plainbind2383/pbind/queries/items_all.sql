-- Only kernel context (`:hub_id`) and the engine's paging bind: nothing for the caller to send.
SELECT i.id AS id
FROM pbind_item i
WHERE i.hub_id = :hub_id
ORDER BY i.id
LIMIT :limit
