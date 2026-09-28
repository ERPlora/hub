-- The same rows WITHOUT an `id` column: the engine has nothing to break ties with and must not
-- invent one (a report, an aggregate, a join that projects other keys).
SELECT title, status FROM tiebreak_task WHERE hub_id = :hub_id;
