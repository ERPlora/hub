-- Mirrors what the runtime binds for a plain query: the same `:timezone`/`:caller_lang`
-- system params a module's SELECT can rely on (hub#1022/hub#1098).
SELECT :timezone AS timezone, :caller_lang AS caller_lang;
