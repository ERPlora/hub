// Types of base/schemas/reset.py for the SDK (`useLive`, `useCommand`, `client.api.call`), written by
// hand: keep them in step with it and with `frontend/generated/operations.json`.
import type { BlueprintApp, BlueprintPart, Removal } from './blueprints';

export interface ResetSection extends BlueprintApp {
  rows: number;
  datasets: BlueprintPart[];
}

/** `base.HubResetOut`. */
export interface HubReset {
  dry_run: boolean;
  /** What to type to confirm: the business's name. */
  confirm_with: string;
  sections: ResetSection[];
  /** Always empty: the worker empties after copying (`base.hub.dumps` says how it went). */
  apps: Removal[];
  /** `planned`: the plan only (dry run); `copying`: asked, the copy is being made, then the sections are emptied. */
  status: 'planned' | 'copying';
}

declare module '@erplora/ui/sdk' {
  interface Operations {
    'base.hub.reset': {
      input: { apps?: string[]; confirm?: string; dry_run?: boolean };
      output: HubReset;
    };
  }
}
