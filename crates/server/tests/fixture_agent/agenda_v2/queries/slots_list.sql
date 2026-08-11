SELECT id, starts_at, minutes FROM agenda_slot WHERE hub_id = :hub_id ORDER BY starts_at;
