CREATE TABLE IF NOT EXISTS ctxp_observation (
    hub_id TEXT NOT NULL,
    id TEXT NOT NULL,
    ctx_timezone TEXT NOT NULL DEFAULT '',
    param_timezone TEXT NOT NULL DEFAULT '',
    caller_lang TEXT NOT NULL DEFAULT '',
    principal TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (hub_id, id)
);
