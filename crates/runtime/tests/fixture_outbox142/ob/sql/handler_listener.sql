INSERT INTO ob_log (listener, runs)
VALUES ('handler', 1)
ON CONFLICT (listener) DO UPDATE SET runs = ob_log.runs + 1;
