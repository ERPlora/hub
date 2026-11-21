// Types of base/schemas/system.py and base/schemas/release_notes.py for the SDK (`useLive`, `useCommand`,
// `client.api.call`), written by hand: keep them in step with them and with `frontend/generated/operations.json`.

type NoInput = Record<string, never>;

/** `base.SystemStatusOut`: the release running. */
export interface SystemStatus {
  /** The commit, short; `dev` locally. */
  version: string;
  /** When it was published (ISO 8601), or null: never made up. */
  released_at: string | null;
}

/** `base.EventLogEntryOut`: an event between apps as System › Logs shows it. */
export interface EventLogEntry {
  id: string;
  at: string;
  level: 'info' | 'warning' | 'error';
  name: string;
  app: string;
  app_name: string;
  detail: string;
}

/** `base.ReleaseNoteOut`: one change the business notices, already in the person's language. */
export interface ReleaseNote {
  /** «2026-11-19-allergens-on-products». */
  id: string;
  /** The day the change reached the businesses, `YYYY-MM-DD`. */
  date: string;
  kind: 'new' | 'improved' | 'fixed';
  title: string;
  /** Plain text: shown as it comes, never as markup. */
  body: string;
}

declare module '@erplora/ui/sdk' {
  interface Operations {
    'base.system.status': { input: NoInput; output: SystemStatus };
    'base.event.list': { input: NoInput; output: { entries: EventLogEntry[] } };
    'base.release_note.list': { input: { limit?: number; offset?: number }; output: { items: ReleaseNote[]; total: number } };
  }
}
