// What a key may do: read, create, update and delete per app, or on every app ('*').
import type { ApiAction, ApiKeyScopes } from '../operations/api_keys';

export type GeneralMode = 'full' | 'read' | 'write';

export const EVERY_APP = '*';
export const ACTIONS: readonly ApiAction[] = ['read', 'create', 'update', 'delete'];
const WRITING: readonly ApiAction[] = ['create', 'update', 'delete'];
const OF_A_MODE: Readonly<Record<GeneralMode, readonly ApiAction[]>> = {
  full: ['read', ...WRITING],
  read: ['read'],
  write: WRITING,
};

/** What a new key asks for: what is ticked on every app, or on each chosen one, of what who asks may give there. */
export function askedScopes(ticked: ApiKeyScopes, grantable: ApiKeyScopes, everyApp: boolean): ApiKeyScopes {
  const asked: Record<string, ApiAction[]> = {};
  for (const [app, actions] of Object.entries(ticked)) {
    const given = actions.filter((action) => grantable[app]?.includes(action));
    if ((app === EVERY_APP) === everyApp && given.length > 0) asked[app] = given;
  }
  return asked;
}

/** The general mode a key's permissions read as, or `null` when they are not one. */
export function modeOf(scopes: ApiKeyScopes): GeneralMode | null {
  const apps = Object.keys(scopes);
  if (apps.length !== 1 || apps[0] !== EVERY_APP) return null;
  const given = [...scopes[EVERY_APP]].sort().join();
  const modes = Object.keys(OF_A_MODE) as GeneralMode[];
  return modes.find((mode) => [...OF_A_MODE[mode]].sort().join() === given) ?? null;
}
