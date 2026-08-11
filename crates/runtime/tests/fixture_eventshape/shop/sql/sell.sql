-- No business effect: this command exists to EMIT. The payload of a declaratively emitted event
-- is the command's bound params (`commands::execute`), which is what makes this fixture a real
-- till closing a real sale as far as `_event_outbox` is concerned.
SELECT 1;
