-- ONE item by its id: the `appointments.appointments.get` shape of hub#2383. Asked without
-- `:item_id`, the equality binds NULL, matches nothing and answers "there is nothing".
SELECT i.id AS id, i.name AS name
FROM pbind_item i
WHERE i.hub_id = :hub_id AND i.id = :item_id
