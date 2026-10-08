-- The shape of every periodic sweep hub#2612 is about (tables.expire_holds,
-- reservations.release_unconfirmed, services.packages.expire_holds): a set-based UPDATE that
-- most passes find NOTHING to do. Zero rows is the normal answer, not an error.
UPDATE w2612_holds SET status = 'released'
WHERE hub_id = :hub_id AND status = 'held';
