/** Navegación secundaria real de Ajustes. `store` se retiró porque duplicaba datos de Hub. */
export const SETTINGS_TABS = ['hub', 'tax', 'communications', 'tickets', 'permissions', 'data'] as const;

export type SettingsTab = (typeof SETTINGS_TABS)[number];

/** Resuelve hashes actuales y degrada enlaces retirados/desconocidos al Hub actual. */
export function resolveSettingsTab(hash: string): SettingsTab {
  const candidate = hash.replace(/^#/, '');
  return (SETTINGS_TABS as readonly string[]).includes(candidate)
    ? (candidate as SettingsTab)
    : 'hub';
}
