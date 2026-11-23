// What `printing.device.health` answers (schemas/health.py): whether the station of a function answers now. System's
// «Your printer» reads it; the Home's health row reads the same answer through base.
import type { Usage } from '../operations';

export type StationState = 'ok' | 'no_signal' | 'not_configured';

export interface DeviceHealthOut {
  usage: Usage;
  state: StationState;
}

declare module '@erplora/ui/sdk' {
  interface Operations {
    'printing.device.health': { input: { usage: Usage }; output: DeviceHealthOut };
  }
}
