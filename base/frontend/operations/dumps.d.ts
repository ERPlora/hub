// Types of base/schemas/dumps.py for the SDK (`useLive`, `useCommand`, `client.api.call`), written by
// hand: keep them in step with it and with `frontend/generated/operations.json`.
import type { BlueprintApp, Removal } from './blueprints';

type NoInput = Record<string, never>;

/** How the last reset went (`base.ResetStateOut`). */
export type ResetState = 'copying' | 'emptying' | 'done' | 'failed';

export interface ResetProgress {
  state: ResetState;
  sections: BlueprintApp[];
  requested_by: string;
  /** Why it failed: `dumps_unavailable`, `dump_failed`, `emptying_failed` or `hub_not_ready`; empty otherwise. */
  error: string;
  removed: Removal[];
  finished_at: string | null;
}

/** A copy of the business's data (`base.HubDumpOut`): before a reset, or when the business was deleted. */
export interface HubDump {
  id: string;
  kind: 'reset' | 'offboarding';
  created_at: string;
  bytes: number;
}

/** `base.HubDumpsOut`: the copies (newest first) and the last reset. */
export interface HubDumps {
  reset: ResetProgress | null;
  dumps: HubDump[];
}

declare module '@erplora/ui/sdk' {
  interface Operations {
    'base.hub.dumps': { input: NoInput; output: HubDumps };
    // 503 `base.dumps_unavailable` when the copy cannot be linked now; 404 when it is no longer kept.
    'base.hub.dump_link': { input: { id: string }; output: { url: string; expires_at: string } };
  }
}
