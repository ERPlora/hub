-- hub#1680: how many `sale_create_meeting` commands have ARRIVED (in flight or done). Read outside
-- any snapshot, like the command reads it.
SELECT COALESCE(pg_sequence_last_value('slowtill_arrivals'), 0) AS arrived;
