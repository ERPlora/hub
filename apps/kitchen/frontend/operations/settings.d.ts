// Types of apps/kitchen/schemas/settings.py for the SDK; what they follow, in ./fields.d.ts.
import type { NoInput, OrderType, SoundTone } from './fields';

export interface SettingsOut {
  show_timer: boolean;
  warning_minutes: number;
  critical_minutes: number;
  color_coding: boolean;
  sound_enabled: boolean;
  sound_volume: number;
  sound_tone: SoundTone;
  print_pass: boolean;
  works_from_screen: boolean;
  default_order_type: OrderType;
  timezone: string;
}

export type SettingsPatchIn = Partial<Omit<SettingsOut, 'timezone'>>;

declare module '@erplora/ui/sdk' {
  interface Operations {
    'kitchen.settings.get': { input: NoInput; output: SettingsOut };
    'kitchen.settings.update': { input: SettingsPatchIn; output: SettingsOut };
  }
}
