-- GDPR erasure of what the retired screen kept about one customer: blank it, mark it deleted.
UPDATE _deprecated_set_aside_request
   SET data = NULL, deleted_at = :now
 WHERE hub_id = :hub_id AND customer_id = :customer_id;
