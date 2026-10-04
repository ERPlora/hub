-- The `tasks.tasks.my` shape: `:due_horizon` is only read when `:apply_horizon` is on, and the
-- query's JSON Schema DECLARES it optional — the screen sends it as null on purpose.
SELECT i.id AS id
FROM pbind_item i
WHERE i.hub_id = :hub_id
  AND (:apply_horizon = 0 OR i.due <= :due_horizon)
ORDER BY i.id
