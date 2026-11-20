// Types of base/schemas/api_keys.py for the SDK (`useLive`, `useCommand`, `client.api.call`), written by
// hand: keep them in step with it and with `frontend/generated/operations.json`.

type NoInput = Record<string, never>;

/** `base.ApiKeyOut`: a key of the business (never its whole token). */
export type ApiKeyMode = 'full' | 'read' | 'write' | 'per_app';
export type ApiKind = 'read' | 'write';

export interface ApiKeyRow {
  id: string;
  name: string;
  /** The token's first characters, to tell it apart. */
  prefix: string;
  mode: ApiKeyMode;
  scopes: Record<string, ApiKind[]>;
  rate_per_minute: number;
  created_by: string;
  created_at: string;
  rotated_at: string | null;
  last_used_at: string | null;
  revoked_at: string | null;
}

/** `base.ApiAppOut`: an app this business has that publishes its API. */
export interface ApiApp {
  id: string;
  name: string;
  read: boolean;
  write: boolean;
}

/** `base.ApiKeyListOut`. */
export interface ApiKeyList {
  keys: ApiKeyRow[];
  apps: ApiApp[];
}

export interface ApiKeyInput {
  name: string;
  rate_per_minute: number;
  mode: ApiKeyMode;
  scopes: Record<string, ApiKind[]>;
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
