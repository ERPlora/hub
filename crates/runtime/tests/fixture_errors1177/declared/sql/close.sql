UPDATE e1177_item SET state = 'closed' WHERE hub_id = :hub_id AND id = :id AND state = 'open';
