// @vitest-environment node
// flow: ninguno — e2e harness (hub#997)
// A fresh owner on the stack's SaaS, shared by every spec that signs one up (saas-owner.ts): the sign-up and the business
// were copied in five specs. Its POST to the SaaS's API carries the SaaS's own CSRF token, read from the cookie of the
// SaaS's host (never a hub's), and without one it says so at once instead of a 403 later. The specs that sign up an
// owner take it from there and keep no copy of their own.
import { readdirSync, readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import type { BrowserContext } from '@playwright/test';
import { describe, expect, it } from 'vitest';

import { SAAS } from './helpers';
import { saasPost } from './saas-owner';

const HERE = dirname(fileURLToPath(import.meta.url));

/** A browser context with `cookies` on its jar, whose POSTs are recorded instead of sent. */
function contextWith(cookies: { name: string; value: string; domain: string }[]) {
  const posted: { url: string; options: unknown }[] = [];
  const context = {
    cookies: async () => cookies,
    request: {
      post: async (url: string, options: unknown) => {
        posted.push({ url, options });
        return { status: () => 201 };
      },
    },
  } as unknown as BrowserContext;
  return { context, posted };
}

describe('saasPost', () => {
  it("posts to the SaaS's API with the SaaS's own CSRF token", async () => {
    const host = new URL(SAAS).hostname;
    const { context, posted } = contextWith([
      { name: 'csrftoken', value: 'of-a-hub', domain: `a.${host}` },
      { name: 'csrftoken', value: 'of-the-saas', domain: host },
    ]);

    await saasPost(context, '/hubs/businesses', { name: 'Bar', country: 'ES' });

    expect(posted).toEqual([
      {
        url: `${SAAS}/api/hubs/businesses`,
        options: { headers: { 'X-CSRFToken': 'of-the-saas' }, data: { name: 'Bar', country: 'ES' } },
      },
    ]);
  });

  it('says it has no token before posting anything when the account is not signed in there', async () => {
    const { context, posted } = contextWith([]);

    await expect(saasPost(context, '/hubs/businesses', {})).rejects.toThrow(
      'POST /hubs/businesses: no csrftoken of the SaaS (sign in first)',
    );
    expect(posted).toEqual([]);
  });
});

describe('the specs that sign up an owner on the SaaS', () => {
  it('take it from saas-owner.ts and keep no copy of their own', () => {
    const specs = readdirSync(HERE).filter((name) => name.endsWith('.spec.ts'));
    const copies = specs.filter((name) => readFileSync(join(HERE, name), 'utf8').includes('/launch?tab=signup'));

    expect(copies).toEqual([]);
  });
});
