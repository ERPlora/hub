-- verifactu#70 fixture: a `range` filter over an INSTANT column (`happened_at`) next to one
-- over a bare CALENDAR-DATE column (`logged_on`) — both TEXT, the same shape every module in
-- production stores these in (`verifactu_event.timestamp`, `verifactu_contingency
-- .next_attempt_at`, `verifactu_aeat_record.query_timestamp` are all TEXT ISO-8601; a native
-- TIMESTAMPTZ column does not reproduce the bug at all — `>=`/`<=` against a bare-date bound
-- fail to PREPARE with `42883 operator does not exist`, not the silent empty page the issue
-- describes). Same day, two different STRING shapes — the bug and its regression guard live on
-- the same table on purpose.
CREATE TABLE rangefix_event (
  id TEXT PRIMARY KEY,
  hub_id TEXT NOT NULL,
  happened_at TEXT NOT NULL,
  logged_on TEXT NOT NULL
);
INSERT INTO rangefix_event (id, hub_id, happened_at, logged_on) VALUES
  ('day-before', 'h1', '2026-01-14T23:00:00+00:00', '2026-01-14'),
  ('morning',    'h1', '2026-01-15T08:00:00+00:00', '2026-01-15'),
  ('evening',    'h1', '2026-01-15T23:30:00+00:00', '2026-01-15'),
  ('day-after',  'h1', '2026-01-16T00:30:00+00:00', '2026-01-16');
