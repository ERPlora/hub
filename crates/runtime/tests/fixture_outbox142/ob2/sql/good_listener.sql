INSERT INTO ob2_log (listener, runs)
VALUES ('good', 1)
ON CONFLICT (listener) DO UPDATE SET runs = ob2_log.runs + 1;
