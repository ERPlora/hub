INSERT INTO kfx_log (event, runs) VALUES ('kfx.item.created', 1)
ON CONFLICT (event) DO UPDATE SET runs = kfx_log.runs + 1;
