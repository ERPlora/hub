SELECT id, wa_message_id, body FROM w1076_messages
WHERE hub_id = :hub_id ORDER BY wa_message_id ASC;
