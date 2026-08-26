-- The GUARDED statement: the booking itself. `:window_ok` = 0 models "the WHERE did not
-- match" (outside the booking window, settings missing): INSERT ... SELECT over an empty
-- set affects 0 rows and the booking silently never exists.
INSERT INTO gate_booking (id, hub_id, ref)
SELECT :new_id, :hub_id, :ref
WHERE :window_ok = 1
