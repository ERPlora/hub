// Types of base/schemas/system.py for the SDK (`useLive`, `useCommand`, `client.api.call`), written by
// hand: keep them in step with it and with `frontend/generated/operations.json`.

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

declare module '@erplora/ui/sdk' {
  interface Operations {
    'base.system.status': { input: NoInput; output: SystemStatus };
    'base.event.list': { input: NoInput; output: { entries: EventLogEntry[] } };
  }
}
