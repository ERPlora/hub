-- Puerta de ingesta idempotente (hub#1076): dos entregas con el mismo `wa_message_id` (redelivery
-- de un webhook at-least-once) deben dejar UNA fila. El índice único (hub_id, wa_message_id) +
-- `ON CONFLICT DO NOTHING` absorben la fila; lo que este fixture ejercita es que `emit.dedup_key`
-- absorba TAMBIÉN el evento del outbox, que hasta hub#1076 se encolaba una vez por EJECUCIÓN
-- (min_affected_rows/expect_rows revierten la tx entera y no sirven aquí: el webhook necesita un
-- 200 OK para la redelivery, no un 409).
INSERT INTO w1076_messages (id, hub_id, wa_message_id, body, created_at)
VALUES (:new_id, :hub_id, :wa_message_id, :body, :now)
ON CONFLICT (hub_id, wa_message_id) DO NOTHING;
