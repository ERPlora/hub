// Types of base/schemas/devices.py for the SDK (`useLive`, `useCommand`, `client.api.call`), written by
// hand: keep them in step with it and with `frontend/generated/operations.json`.

type NoInput = Record<string, never>;

export type DeviceMode = 'shared' | 'personal';

/** `base.DeviceCurrentOut`: the device in hand. */
export interface DeviceCurrent {
  known: boolean;
  mode: DeviceMode;
  mode_set_by: string;
  mode_set_at: string | null;
}

/** `base.DeviceOut`: a device someone entered this hub on. */
export interface DeviceRow {
  id: string;
  name: string;
  agent: string;
  mode: DeviceMode;
  current: boolean;
  in_use: boolean;
  session_until: string | null;
  last_entry_at: string;
  last_user: string;
  created_at: string;
  unused: boolean;
}

declare module '@erplora/ui/sdk' {
  interface Operations {
    'base.pin.set': { input: { pin: string; current?: string }; output: { set: boolean } };
    'base.device.current': { input: NoInput; output: DeviceCurrent };
    'base.device.mode_set': { input: { mode: DeviceMode }; output: DeviceCurrent };
    'base.device.list': { input: NoInput; output: { devices: DeviceRow[]; unused: number } };
    'base.device.rename': { input: { id: string; name: string }; output: { id: string } };
    'base.device.remove': { input: { id: string }; output: { removed: number; yours: boolean } };
    'base.device.prune': { input: NoInput; output: { removed: number } };
  }
}
