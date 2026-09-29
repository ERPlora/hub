-- ONE item by its id. The bind is `:item_id`, not `:id` — the appointments.appointments.get
-- shape of hub#1913: a caller that sends `id` binds NULL here and gets zero rows, no error.
-- `:ghost` is only mentioned in this comment, so it is NOT vocabulary.
SELECT i.id AS id, i.name AS name
FROM pparam_item i
WHERE i.hub_id = :hub_id AND i.id = :item_id
