-- hub#1680: a command that proves it OVERLAPPED another one, without reading a clock.
--
-- It announces its arrival and waits — polling every 20 ms, for at most 10 s — until it knows it was
-- in flight together with another command, then announces its departure. Two tills let in together
-- meet within milliseconds whatever the load of the machine; two tills queued on a lock never do:
-- the second one only arrives after the first has DEPARTED. Sequences, because
-- rows written inside a transaction are invisible to the other one until commit and `nextval` is not.
WITH RECURSIVE arrived AS MATERIALIZED (
    SELECT nextval('slowtill_arrivals') AS n
),
waiting(i, n, met) AS (
    -- Met on arrival: somebody was already in (my arrival number minus the departures so far).
    SELECT 0, a.n, a.n - COALESCE(pg_sequence_last_value('slowtill_departures'), 0) >= 2
      FROM arrived a
    UNION ALL
    -- Met while waiting: somebody ARRIVED AFTER ME. Queued on a lock that cannot happen — the next
    -- command only arrives once I have departed. `pg_sequence_last_value`, not `SELECT last_value
    -- FROM` the sequence: the SELECT reads with this statement's snapshot and never sees an arrival
    -- made after it started (measured). The pause is LATERAL on purpose: a bare `pg_sleep` in FROM is
    -- evaluated once for the whole loop.
    SELECT w.i + 1, w.n, COALESCE(pg_sequence_last_value('slowtill_arrivals'), 0) > w.n
      FROM waiting w
      CROSS JOIN LATERAL (SELECT pg_sleep(0.02), w.i AS tick) AS pause
     WHERE NOT w.met AND w.i < 500
)
INSERT INTO slowtill_sales (id, hub_id, label, created_by, created_at)
SELECT :new_id, :hub_id,
       -- The departure is taken here, once the wait is over (the aggregate needs the whole loop).
       :label || CASE WHEN bool_or(met) THEN ':met' ELSE ':alone' END
              || CASE WHEN nextval('slowtill_departures') > 0 THEN '' ELSE '' END,
       :current_user_id, :now
  FROM waiting;
