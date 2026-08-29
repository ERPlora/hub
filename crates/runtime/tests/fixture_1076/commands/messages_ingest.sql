-- Idempotent ingestion door (hub#1076): two deliveries with the same `wa_message_id` (an
-- at-least-once webhook redelivery) must leave ONE row. The unique index (hub_id, wa_message_id) +
-- `ON CONFLICT DO NOTHING` absorb the row; what this fixture exercises is that `emit.dedup_key`
-- ALSO absorbs the outbox event, which until hub#1076 was queued once per EXECUTION
-- (min_affected_rows/expect_rows roll back the whole tx and are useless here: the webhook needs a
-- 200 OK for the redelivery, not a 409).
INSERT INTO w1076_messages (id, hub_id, wa_message_id, body, created_at)
VALUES (:new_id, :hub_id, :wa_message_id, :body, :now)
ON CONFLICT (hub_id, wa_message_id) DO NOTHING;
