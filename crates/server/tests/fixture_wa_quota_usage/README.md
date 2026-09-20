Fixture of `whatsapp_inbox` **after** ERPlora/whatsapp_inbox#155: `_quota.set` declares
`monthly_usage` and the settings singleton has a column to keep it in.

Its twin next door (`fixture_wa_quota`) is the module as **published today**, and the pair is the
point: module versions do not move with hub versions (ADR-0286 §3 — an older module keeps
installing on a newer hub), so the sync has to write the spend on one and stay silent about it on
the other, without ever losing the cap.
