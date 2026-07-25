export const SYSTEM_TABS = ['resources', 'plan', 'updates', 'documents', 'logs'] as const;

export type SystemTab = (typeof SYSTEM_TABS)[number];

/** Resuelve una pestaña vigente. `backups` se retiró: su contenido vive en Ajustes → Datos. */
export function resolveSystemTab(hash: string): SystemTab {
  const candidate = hash.replace(/^#/, '');
  return (SYSTEM_TABS as readonly string[]).includes(candidate)
    ? (candidate as SystemTab)
    : 'resources';
}

export function isLegacyBackupsHash(hash: string): boolean {
  return hash.replace(/^#/, '') === 'backups';
}
