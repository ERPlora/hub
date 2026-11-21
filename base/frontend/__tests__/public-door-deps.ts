// What a test of a public page's door opens it with: the SPA's config, a browser whose `fetch` gives one answer and
// whose document may carry base's `public-door` block, and a JSON answer.
import type { SpaConfig } from '@erplora/ui/sdk';
import { vi } from 'vitest';

import type { DoorDeps } from '../lib/public-door';

export const DOOR_CONFIG = {
  csrfCookieName: 'hub_csrftoken',
  csrfHeader: 'X-CSRFToken',
  liveUrl: '/api/live',
  apiBase: '/api',
  lang: 'en',
  deviceIdStorageKey: 'hub.device',
} satisfies SpaConfig;

/** A page's document, with `block` as the JSON base embeds as `public-door` when given. */
export function doorDocument(block?: string): Document {
  const page = document.implementation.createHTMLDocument('public page');
  if (block !== undefined) {
    const script = page.createElement('script');
    script.id = 'public-door';
    script.type = 'application/json';
    script.textContent = block;
    page.body.append(script);
  }
  return page;
}

export function doorDeps(answer: Response, page = doorDocument()): DoorDeps & { fetchImpl: ReturnType<typeof vi.fn> } {
  const store = new Map<string, string>();
  return {
    // A copy each time: a response's body is read once, and a test may call the door more than once.
    fetchImpl: vi.fn(async () => answer.clone()),
    storage: { getItem: (key) => store.get(key) ?? null, setItem: (key, value) => void store.set(key, value) },
    cookies: () => 'hub_csrftoken=tok',
    randomUUID: () => '00000000-0000-4000-8000-000000000000',
    doc: page,
  };
}

export const jsonAnswer = (status: number, body: unknown): Response =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
