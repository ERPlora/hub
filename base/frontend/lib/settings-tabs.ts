// The tabs of Settings: which there are, who has each one and the one an address opens. A tab is only for whoever can use
// what it holds, as its screen's operations ask; a link to one the person does not have opens their first.

export type SettingsTab = 'general' | 'business' | 'tickets' | 'data';

export interface SettingsTabEntry {
  id: SettingsTab;
  labelKey: string;
  icon: string;
  /** Whoever holds it has the tab. */
  permission: string;
}

export const SETTINGS_TABS: readonly SettingsTabEntry[] = [
  { id: 'general', labelKey: 'base.settings.tabs.general', icon: 'ion:settings-outline', permission: 'base.view_home' },
  { id: 'business', labelKey: 'base.settings.tabs.business', icon: 'ion:wallet-outline', permission: 'base.view_home' },
  // It only leads to the Printing app's printers (or to Apps, to install it).
  { id: 'tickets', labelKey: 'base.settings.tabs.tickets', icon: 'lucide:receipt', permission: 'printing.manage_settings' },
  { id: 'data', labelKey: 'base.settings.tabs.data', icon: 'ion:swap-vertical-outline', permission: 'base.administer_hub' },
];

/** Old addresses still linked: `#hub` was General; published versions of VeriFactu open `#tax`, the business's tab. */
const ALIASES: Readonly<Record<string, SettingsTab>> = { hub: 'general', tax: 'business' };

/** The tabs of whoever `can` answers for, in their order. */
export function settingsTabsOf(can: (permission: string) => boolean): SettingsTabEntry[] {
  return SETTINGS_TABS.filter((tab) => can(tab.permission));
}

/** The tab a hash opens (`#data`) among the person's `open` ones; any other hash opens the first of them. */
export function settingsTab(hash: string, open: readonly SettingsTab[]): SettingsTab | undefined {
  const wanted = hash.replace(/^#/, '');
  const named = SETTINGS_TABS.find((tab) => tab.id === wanted)?.id ?? ALIASES[wanted];
  return named && open.includes(named) ? named : open[0];
}
