// Types of base/schemas/api_keys.py for the SDK (`useLive`, `useCommand`, `client.api.call`), written by
// hand: keep them in step with it and with `frontend/generated/operations.json`.

type NoInput = Record<string, never>;

/** What a key may do on an app (`base.api_actions`). */
export type ApiAction = 'read' | 'create' | 'update' | 'delete';
/** Per app (its id), or `'*'` for every app of the business: the actions given there. */
export type ApiKeyScopes = Record<string, readonly ApiAction[]>;

/** `base.ApiKeyOut`: a key of the business (never its whole token). */
export interface ApiKeyRow {
  id: string;
  name: string;
  /** The token's first characters, to tell it apart. */
  prefix: string;
  scopes: ApiKeyScopes;
  rate_per_minute: number;
  created_by: string;
  created_at: string;
  rotated_at: string | null;
  last_used_at: string | null;
  revoked_at: string | null;
}

/** `base.ApiAppOut`: an app this business has that publishes its API, and what it publishes. */
export interface ApiApp {
  id: string;
  name: string;
  actions: ApiAction[];
}

/** `base.ApiKeyListOut`: also the most who asks may give a key. */
export interface ApiKeyList {
  keys: ApiKeyRow[];
  apps: ApiApp[];
  grantable: ApiKeyScopes;
}

export interface ApiKeyInput {
  name: string;
  rate_per_minute: number;
  scopes: ApiKeyScopes;
}

declare module '@erplora/ui/sdk' {
  interface Operations {
    'base.api_key.list': { input: NoInput; output: ApiKeyList };
    'base.api_key.create': { input: ApiKeyInput; output: { key: ApiKeyRow; token: string } };
    'base.api_key.rotate': { input: { id: string }; output: { key: ApiKeyRow; token: string } };
    'base.api_key.revoke': { input: { id: string }; output: { key: ApiKeyRow } };
    'base.api_doc.get': { input: NoInput; output: { document: Record<string, unknown>; apps: ApiApp[] } };
    'base.api_doc.settings': { input: NoInput; output: { docs_enabled: boolean; can_change: boolean } };
    'base.api_doc.settings_update': { input: { docs_enabled: boolean }; output: { docs_enabled: boolean; can_change: boolean } };
  }
}
