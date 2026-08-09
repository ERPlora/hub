SELECT id, customer, starts_at, minutes FROM agenda_booking WHERE hub_id = :hub_id ORDER BY starts_at;
