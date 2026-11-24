// What a key may do, between the screen's choices (a general mode, or «Read» and «Write» per app) and the key's
// permissions: read, create, update and delete per app, or on every app ('*').
import type { ApiAction, ApiKeyScopes } from '../operations/api_keys';

export type GeneralMode = 'full' | 'read' | 'write';
export type ApiKind = 'read' | 'write';

const EVERY_APP = '*';
const WRITING: readonly ApiAction[] = ['create', 'update', 'delete'];
const OF_A_MODE: Readonly<Record<GeneralMode, readonly ApiAction[]>> = {
  full: ['read', ...WRITING],
  read: ['read'],
  write: WRITING,
};

/** A general mode: its actions on every app. */
export function scopesOfMode(mode: GeneralMode): ApiKeyScopes {
  return { [EVERY_APP]: [...OF_A_MODE[mode]] };
}

function actionsOfKind(kind: ApiKind, given: readonly ApiAction[]): ApiAction[] {
  return given.filter((action) => (kind === 'read' ? action === 'read' : WRITING.includes(action)));
}

/** Per app, «Read» and «Write»: «Write» is the creating, changing and deleting who asks may give there. */
export function scopesOfApps(perApp: Readonly<Record<string, readonly ApiKind[]>>, grantable: ApiKeyScopes): ApiKeyScopes {
  const scopes: Record<string, ApiAction[]> = {};
  for (const [app, kinds] of Object.entries(perApp)) {
    const actions = kinds.flatMap((kind) => actionsOfKind(kind, grantable[app] ?? []));
    if (actions.length > 0) scopes[app] = actions;
  }
  return scopes;
}

/** Whether who asks may tick «Read» or «Write» on `app`. */
export function mayTick(grantable: ApiKeyScopes, app: string, kind: ApiKind): boolean {
  return actionsOfKind(kind, grantable[app] ?? []).length > 0;
}

/** The general mode a key's permissions read as, or `null` when they are not one. */
export function modeOf(scopes: ApiKeyScopes): GeneralMode | null {
  const apps = Object.keys(scopes);
  if (apps.length !== 1 || apps[0] !== EVERY_APP) return null;
  const given = [...scopes[EVERY_APP]].sort().join();
  const modes = Object.keys(OF_A_MODE) as GeneralMode[];
  return modes.find((mode) => [...OF_A_MODE[mode]].sort().join() === given) ?? null;
}
