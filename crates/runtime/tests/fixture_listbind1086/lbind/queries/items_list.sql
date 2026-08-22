-- Items of ONE cart. `:cart_id` is the context parameter: the SQL itself references it,
-- so an absent (or null) bind can only mean "bind NULL" → `cart_id = NULL` matches nothing.
-- That is the hub#1086 lie: a page that says total: 0 with real rows behind it.
SELECT i.id AS id, i.cart_id AS cart_id, i.name AS name
FROM lbind_item i
WHERE i.hub_id = :hub_id AND i.cart_id = :cart_id
